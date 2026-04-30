"""Phase 5 / Workflow #18 — paper metadata.json sidecar.

The sidecar lands at ``<project_dir>/paper/metadata.json`` and gives
downstream tools a structured view of what's in the generated paper
without having to parse LaTeX. We pin:

* output is valid JSON,
* the sections / figures / references / validation surface match the
  caller's input (excerpts, DOI/arxiv passthrough, validation summary),
* ``write_paper_metadata`` is atomic — a crash mid-write must never
  leave a half-written sidecar visible — and idempotent.
"""
from __future__ import annotations

import json
from pathlib import Path

from plato.paper_agents.metadata_sidecar import write_paper_metadata


def test_writes_valid_json_at_expected_path(tmp_path: Path) -> None:
    out = write_paper_metadata(tmp_path, paper_state={"abstract": "hello"})
    assert out == tmp_path / "paper" / "metadata.json"
    assert out.exists()
    payload = json.loads(out.read_text())
    assert payload["schema_version"] == 1
    assert payload["sections"]["abstract"] == "hello"


def test_section_excerpts_cover_canonical_aliases(tmp_path: Path) -> None:
    state = {
        "abstract": "abs body",
        "introduction": "intro body",  # alias of 'intro'
        "method": "method body",  # alias of 'methods'
        "results": "results body",
        "conclusion": "conc body",  # alias of 'conclusions'
    }
    out = write_paper_metadata(tmp_path, paper_state=state)
    payload = json.loads(out.read_text())
    assert payload["sections"] == {
        "abstract": "abs body",
        "intro": "intro body",
        "methods": "method body",
        "results": "results body",
        "conclusions": "conc body",
    }


def test_long_sections_are_excerpted(tmp_path: Path) -> None:
    """Section bodies > 4 KB get truncated with an ellipsis sentinel."""
    big = "x" * 10_000
    out = write_paper_metadata(tmp_path, paper_state={"abstract": big})
    payload = json.loads(out.read_text())
    excerpt = payload["sections"]["abstract"]
    assert len(excerpt) <= 4097  # 4096 chars + the ellipsis
    assert excerpt.endswith("…")


def test_figure_paths_passthrough(tmp_path: Path) -> None:
    state = {"plot_paths": ["/tmp/plots/fig1.png", "/tmp/plots/fig2.png"]}
    out = write_paper_metadata(tmp_path, paper_state=state)
    payload = json.loads(out.read_text())
    assert payload["figures"] == [
        "/tmp/plots/fig1.png",
        "/tmp/plots/fig2.png",
    ]


def test_references_normalize_doi_and_arxiv(tmp_path: Path) -> None:
    refs = [
        {"doi": "10.1000/abc", "title": "A paper"},
        {"arxiv_id": "2401.12345", "title": "An arxiv preprint"},
        "Loose title-only string",
    ]
    out = write_paper_metadata(tmp_path, paper_state={}, references=refs)
    payload = json.loads(out.read_text())
    refs_out = payload["references"]
    assert {"doi": "10.1000/abc", "title": "A paper"} in refs_out
    assert {"arxiv_id": "2401.12345", "title": "An arxiv preprint"} in refs_out
    assert {"title": "Loose title-only string"} in refs_out


def test_validation_summary_passes_through(tmp_path: Path) -> None:
    report = {
        "claims_total": 10,
        "claims_supported": 8,
        "claims_unsupported": 2,
        "score": 0.8,
        "passed": True,
    }
    out = write_paper_metadata(tmp_path, paper_state={}, validation_report=report)
    payload = json.loads(out.read_text())
    summary = payload["validation"]
    assert summary["claims_total"] == 10
    assert summary["claims_supported"] == 8
    assert summary["score"] == 0.8
    assert summary["passed"] is True
    assert summary["raw"] == report


def test_validation_omitted_when_no_report(tmp_path: Path) -> None:
    out = write_paper_metadata(tmp_path, paper_state={"abstract": "x"})
    payload = json.loads(out.read_text())
    assert payload["validation"] is None


def test_idempotent_overwrite(tmp_path: Path) -> None:
    """Calling twice leaves a single, valid file (last write wins)."""
    write_paper_metadata(tmp_path, paper_state={"abstract": "first"})
    out = write_paper_metadata(tmp_path, paper_state={"abstract": "second"})
    payload = json.loads(out.read_text())
    assert payload["sections"]["abstract"] == "second"
    # No leftover .tmp file from the atomic rename.
    assert not (tmp_path / "paper" / "metadata.json.tmp").exists()


def test_atomic_no_temp_left_behind(tmp_path: Path) -> None:
    """The temp file used for the atomic write is renamed away."""
    write_paper_metadata(tmp_path, paper_state={"abstract": "abc"})
    # Only metadata.json should exist in paper/.
    paper_dir = tmp_path / "paper"
    files = sorted(p.name for p in paper_dir.iterdir())
    assert files == ["metadata.json"]


def test_creates_paper_dir_if_missing(tmp_path: Path) -> None:
    """``project_dir/paper/`` is created on demand."""
    assert not (tmp_path / "paper").exists()
    out = write_paper_metadata(tmp_path, paper_state={})
    assert out.parent.is_dir()


def test_accepts_string_project_dir(tmp_path: Path) -> None:
    out = write_paper_metadata(str(tmp_path), paper_state={"abstract": "hi"})
    assert out == tmp_path / "paper" / "metadata.json"
    assert json.loads(out.read_text())["sections"]["abstract"] == "hi"
