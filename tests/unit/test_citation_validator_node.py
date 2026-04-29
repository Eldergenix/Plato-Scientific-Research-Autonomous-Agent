"""Phase 2 — R3: tests for the citation_validator_node LangGraph wrapper.

The node is exercised end-to-end with a *mocked* ``CitationValidator`` so
the suite never reaches the network. Each test confirms the node:
- Builds a Source list from heterogeneous reference shapes.
- Aggregates a validation_rate and writes ``validation_report.json``.
- Returns a ``validation_report`` state update keyed by ``run_id``.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from plato.paper_agents import citation_validator_node as node_module
from plato.state.models import Source, ValidationResult


def _state(tmp_path: Path, references=None, sources=None, paper_refs: str | None = None) -> dict:
    paper = {"References": paper_refs or ""}
    state: dict = {
        "files": {"Folder": str(tmp_path)},
        "paper": paper,
        "run_id": "run-test-001",
    }
    if references is not None:
        state["references"] = references
    if sources is not None:
        state["sources"] = sources
    return state


def _vr(source_id: str, *, doi_resolved=False, arxiv_resolved=False, error=None) -> ValidationResult:
    return ValidationResult(
        source_id=source_id,
        doi_resolved=doi_resolved,
        arxiv_resolved=arxiv_resolved,
        retracted=False,
        error=error,
        checked_at=datetime.now(timezone.utc),
    )


def _patch_validator(results: list[ValidationResult]):
    """Patch CitationValidator so __aenter__/__aexit__ work and validate_batch returns ``results``."""
    mock = AsyncMock()
    mock.__aenter__.return_value = mock
    mock.__aexit__.return_value = None
    mock.validate_batch = AsyncMock(return_value=results)
    return patch.object(node_module, "CitationValidator", return_value=mock)


def test_three_refs_two_pass_one_fails(tmp_path):
    """1 valid DOI + 1 hallucinated + 1 valid arxiv → validation_rate ≈ 2/3."""
    refs = [
        {"id": "r1", "doi": "10.1000/real", "title": "Real DOI paper"},
        {"id": "r2", "doi": "10.9999/fake", "title": "Hallucinated DOI"},
        {"id": "r3", "arxiv_id": "2401.12345", "title": "Real arxiv paper"},
    ]
    state = _state(tmp_path, references=refs)
    results = [
        _vr("r1", doi_resolved=True),
        _vr("r2", doi_resolved=False, error="404"),
        _vr("r3", arxiv_resolved=True),
    ]

    with _patch_validator(results):
        out = asyncio.run(node_module.citation_validator_node(state))

    report = out["validation_report"]
    assert report["total"] == 3
    assert report["passed"] == 2
    assert abs(report["validation_rate"] - (2 / 3)) < 1e-9
    assert len(report["failures"]) == 1
    assert report["failures"][0]["source_id"] == "r2"
    assert report["failures"][0]["error"] == "404"

    # validation_report.json on disk
    report_path = tmp_path / "runs" / "run-test-001" / "validation_report.json"
    assert report_path.exists()
    persisted = json.loads(report_path.read_text())
    assert persisted["total"] == 3
    assert persisted["passed"] == 2

    # state update is also keyed
    assert out["run_id"] == "run-test-001"


def test_empty_references_writes_empty_report_no_crash(tmp_path):
    state = _state(tmp_path)

    # No CitationValidator should even be constructed for empty input.
    with patch.object(node_module, "CitationValidator") as ctor:
        out = asyncio.run(node_module.citation_validator_node(state))

    ctor.assert_not_called()

    report = out["validation_report"]
    assert report["total"] == 0
    assert report["passed"] == 0
    assert report["validation_rate"] == 0.0
    assert report["failures"] == []

    report_path = tmp_path / "runs" / "run-test-001" / "validation_report.json"
    assert report_path.exists()
    persisted = json.loads(report_path.read_text())
    assert persisted["total"] == 0


def test_state_validation_report_set_after_run(tmp_path):
    refs = [{"id": "r1", "doi": "10.1/x"}]
    state = _state(tmp_path, references=refs)
    results = [_vr("r1", doi_resolved=True)]

    with _patch_validator(results):
        out = asyncio.run(node_module.citation_validator_node(state))

    assert "validation_report" in out
    assert out["validation_report"]["total"] == 1
    assert out["validation_report"]["passed"] == 1


def test_falls_back_to_bibtex_blob(tmp_path):
    """When neither ``sources`` nor ``references`` is set, parse the BibTeX blob."""
    bibtex = """\
@article{Smith2024,
  title = {Real paper},
  doi = {10.1000/real},
}

@misc{Jones2024,
  title = {Arxiv paper},
  eprint = {2401.12345},
}
"""
    state = _state(tmp_path, paper_refs=bibtex)
    results = [
        _vr("Smith2024", doi_resolved=True),
        _vr("Jones2024", arxiv_resolved=True),
    ]

    with _patch_validator(results):
        out = asyncio.run(node_module.citation_validator_node(state))

    report = out["validation_report"]
    assert report["total"] == 2
    assert report["passed"] == 2
    assert report["validation_rate"] == 1.0


def test_source_objects_passed_directly(tmp_path):
    """If ``state['sources']`` already contains Source objects, use them directly."""
    src = Source(
        id="s1",
        doi="10.1/x",
        title="Real",
        retrieved_via="crossref",
        fetched_at=datetime.now(timezone.utc),
    )
    state = _state(tmp_path, sources=[src])
    results = [_vr("s1", doi_resolved=True)]

    with _patch_validator(results):
        out = asyncio.run(node_module.citation_validator_node(state))

    assert out["validation_report"]["passed"] == 1
    assert out["validation_report"]["total"] == 1


def test_persists_to_store_when_present(tmp_path):
    """A wired Store should receive every ValidationResult."""
    from unittest.mock import MagicMock

    refs = [{"id": "r1", "doi": "10.1/x"}, {"id": "r2", "doi": "10.2/y"}]
    state = _state(tmp_path, references=refs)
    results = [_vr("r1", doi_resolved=True), _vr("r2", doi_resolved=False)]

    fake_store = MagicMock()
    state["store"] = fake_store

    with _patch_validator(results):
        asyncio.run(node_module.citation_validator_node(state))

    assert fake_store.add_validation.call_count == 2


def test_run_id_generated_when_missing(tmp_path):
    state = _state(tmp_path)
    state.pop("run_id", None)

    with patch.object(node_module, "CitationValidator"):
        out = asyncio.run(node_module.citation_validator_node(state))

    assert out["run_id"]
    assert isinstance(out["run_id"], str)
    assert len(out["run_id"]) >= 8
