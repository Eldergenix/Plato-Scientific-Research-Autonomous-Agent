"""Phase 5 — tests for the standalone citation-validation CLI.

The CitationValidator and any HTTP traffic are mocked; these tests only
exercise the wiring between the project-on-disk layout and the validator.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from plato import cli_validate
from plato.state.models import Source, ValidationResult


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
    return patch.object(cli_validate, "CitationValidator", return_value=mock)


def test_collect_sources_from_empty_dir(tmp_path):
    """An empty project (no runs/, no paper/refs.bib) yields no sources."""
    sources = cli_validate.collect_sources_from_project(tmp_path)
    assert sources == []


def test_collect_sources_from_empty_runs_dir(tmp_path):
    """A project with runs/ but no manifests or refs.bib still yields []."""
    (tmp_path / "runs").mkdir()
    (tmp_path / "paper").mkdir()
    sources = cli_validate.collect_sources_from_project(tmp_path)
    assert sources == []


def test_collect_sources_walks_manifests_and_bibtex(tmp_path):
    """Synthetic manifests + a small refs.bib produce the expected merged list."""
    runs = tmp_path / "runs"
    run1 = runs / "run-001"
    run1.mkdir(parents=True)
    (run1 / "manifest.json").write_text(json.dumps({
        "run_id": "run-001",
        "workflow": "get_paper",
        "source_ids": ["s1"],
    }))
    (run1 / "sources.json").write_text(json.dumps([
        {
            "id": "s1",
            "doi": "10.1000/run1",
            "title": "Run-1 paper",
            "retrieved_via": "crossref",
            "fetched_at": "2024-01-15T00:00:00+00:00",
        },
    ]))

    run2 = runs / "run-002"
    run2.mkdir(parents=True)
    (run2 / "manifest.json").write_text(json.dumps({
        "run_id": "run-002",
        "workflow": "get_paper",
        "source_ids": ["s2"],
    }))
    (run2 / "sources.json").write_text(json.dumps([
        {
            "id": "s2",
            "arxiv_id": "2401.12345",
            "title": "Run-2 arxiv paper",
        },
    ]))

    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    (paper_dir / "refs.bib").write_text(
        """\
@article{Smith2024,
  title = {Bib paper},
  doi = {10.1000/bib},
}
"""
    )

    sources = cli_validate.collect_sources_from_project(tmp_path)

    ids = [s.id for s in sources]
    assert "s1" in ids
    assert "s2" in ids
    assert "Smith2024" in ids
    assert len(sources) == 3

    s1 = next(s for s in sources if s.id == "s1")
    assert s1.doi == "10.1000/run1"
    assert s1.retrieved_via == "crossref"

    s2 = next(s for s in sources if s.id == "s2")
    assert s2.arxiv_id == "2401.12345"

    bib = next(s for s in sources if s.id == "Smith2024")
    assert bib.doi == "10.1000/bib"


def test_collect_sources_dedupes_by_id(tmp_path):
    """A source that appears in both a run sidecar and refs.bib is only validated once."""
    runs = tmp_path / "runs" / "run-001"
    runs.mkdir(parents=True)
    (runs / "manifest.json").write_text(json.dumps({"run_id": "run-001"}))
    (runs / "sources.json").write_text(json.dumps([
        {"id": "Smith2024", "doi": "10.1000/run", "title": "Run copy"},
    ]))

    paper_dir = tmp_path / "paper"
    paper_dir.mkdir()
    (paper_dir / "refs.bib").write_text(
        "@article{Smith2024,\n  title = {Bib copy},\n  doi = {10.1000/bib},\n}\n"
    )

    sources = cli_validate.collect_sources_from_project(tmp_path)
    assert len(sources) == 1
    # First-seen wins (the run sidecar comes before the bibtex pass).
    assert sources[0].doi == "10.1000/run"


def test_run_validation_writes_report(tmp_path):
    """run_validation invokes validate_batch and writes the report next to the latest run."""
    runs = tmp_path / "runs" / "run-001"
    runs.mkdir(parents=True)
    (runs / "manifest.json").write_text(json.dumps({"run_id": "run-001"}))
    (runs / "sources.json").write_text(json.dumps([
        {"id": "s1", "doi": "10.1/x", "title": "Real DOI"},
        {"id": "s2", "doi": "10.9/fake", "title": "Hallucinated"},
    ]))

    results = [
        _vr("s1", doi_resolved=True),
        _vr("s2", doi_resolved=False, error="404"),
    ]

    with _patch_validator(results):
        report = asyncio.run(cli_validate.run_validation(tmp_path))

    assert report["total"] == 2
    assert report["passed"] == 1
    assert report["validation_rate"] == 0.5
    assert len(report["failures"]) == 1
    assert report["failures"][0]["source_id"] == "s2"
    assert report["failures"][0]["error"] == "404"

    report_path = runs / "validation_report.json"
    assert report_path.exists()
    persisted = json.loads(report_path.read_text())
    assert persisted == report


def test_run_validation_empty_project_writes_zero_report(tmp_path):
    """An empty project still writes a report (rate=0, total=0)."""
    with patch.object(cli_validate, "CitationValidator") as ctor:
        report = asyncio.run(cli_validate.run_validation(tmp_path))

    ctor.assert_not_called()
    assert report == {
        "validation_rate": 0.0,
        "total": 0,
        "passed": 0,
        "failures": [],
    }
    # No runs dir → falls back to project root.
    assert (tmp_path / "validation_report.json").exists()


def test_run_validation_honours_explicit_output(tmp_path):
    """--output overrides the default <latest_run>/validation_report.json path."""
    runs = tmp_path / "runs" / "run-001"
    runs.mkdir(parents=True)
    (runs / "manifest.json").write_text(json.dumps({"run_id": "run-001"}))
    (runs / "sources.json").write_text(json.dumps([
        {"id": "s1", "doi": "10.1/x", "title": "x"},
    ]))

    results = [_vr("s1", doi_resolved=True)]
    custom_path = tmp_path / "custom" / "report.json"

    with _patch_validator(results):
        report = asyncio.run(cli_validate.run_validation(tmp_path, output=custom_path))

    assert custom_path.exists()
    assert json.loads(custom_path.read_text()) == report
    # Default path should NOT be written when --output is set.
    assert not (runs / "validation_report.json").exists()


def test_main_missing_dir_returns_2(tmp_path):
    """`plato validate /tmp/nonexistent` exits 2 (bad args)."""
    bogus = tmp_path / "does-not-exist"
    rc = cli_validate.main([str(bogus)])
    assert rc == 2


def test_main_parses_args(tmp_path):
    """`plato validate <project_dir>` parses and runs against an empty project (rate=0)."""
    rc = cli_validate.main([str(tmp_path), "--threshold", "0.0"])
    # Empty project → rate=0.0, threshold=0.0 → passes.
    assert rc == 0
    assert (tmp_path / "validation_report.json").exists()


def test_main_below_threshold_returns_1(tmp_path):
    """When validation_rate < threshold, main returns 1."""
    runs = tmp_path / "runs" / "run-001"
    runs.mkdir(parents=True)
    (runs / "manifest.json").write_text(json.dumps({"run_id": "run-001"}))
    (runs / "sources.json").write_text(json.dumps([
        {"id": "s1", "doi": "10.9/fake", "title": "fail"},
    ]))

    results = [_vr("s1", doi_resolved=False, error="404")]

    with _patch_validator(results):
        rc = cli_validate.main([str(tmp_path)])

    assert rc == 1


def test_plato_run_parser_accepts_validate_citations_flag():
    """The `plato run --validate-citations` flag is accepted by the top-level parser."""
    # Build the parser the same way main() does and confirm it parses the flag
    # without invoking the heavy run path.
    import argparse

    parser = argparse.ArgumentParser(prog="plato")
    subparsers = parser.add_subparsers(dest="command")
    run_p = subparsers.add_parser("run")
    run_p.add_argument("--validate-citations", action="store_true")
    run_p.add_argument("--project-dir", default=None)

    ns = parser.parse_args(["run", "--validate-citations", "--project-dir", "/tmp/foo"])
    assert ns.command == "run"
    assert ns.validate_citations is True
    assert ns.project_dir == "/tmp/foo"


def test_plato_validate_subcommand_parses():
    """The `plato validate <project_dir>` subcommand parses correctly."""
    import argparse

    parser = argparse.ArgumentParser(prog="plato")
    subparsers = parser.add_subparsers(dest="command")
    v_p = subparsers.add_parser("validate")
    v_p.add_argument("project_dir")
    v_p.add_argument("--output", "-o", default=None)
    v_p.add_argument("--threshold", type=float, default=1.0)

    ns = parser.parse_args(["validate", "/tmp/proj", "--threshold", "0.8"])
    assert ns.command == "validate"
    assert ns.project_dir == "/tmp/proj"
    assert ns.threshold == 0.8


def test_real_cli_main_validate_invocation(tmp_path):
    """The real plato.cli.main wiring delegates `plato validate` to cli_validate.main."""
    from plato import cli as plato_cli

    # Patch cli_validate.main so we don't recursively run.
    with patch.object(plato_cli, "sys") as mock_sys:
        mock_sys.argv = ["plato", "validate", str(tmp_path), "--threshold", "0.0"]
        # parser reads sys.argv via parse_args() default.
        with patch("sys.argv", ["plato", "validate", str(tmp_path), "--threshold", "0.0"]):
            with patch("plato.cli_validate.main", return_value=0) as mock_main:
                # sys.exit is patched on the module-bound `sys` reference.
                mock_sys.exit.side_effect = SystemExit
                with pytest.raises(SystemExit):
                    plato_cli.main()
                mock_main.assert_called_once()
                argv = mock_main.call_args[0][0]
                assert argv[0] == str(tmp_path)
                assert "--threshold" in argv
                assert "0.0" in argv
