"""Phase 4 — R10: ResearchLoop + AcceptanceScore tests.

These tests exercise the loop without ever instantiating real ``Plato``;
they use a mock ``plato_factory`` and a deterministic ``score_fn``.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Iterator

import pytest

from plato.loop import AcceptanceScore, ResearchLoop
from plato.loop import research_loop as research_loop_mod


# ---------------------------------------------------------------- AcceptanceScore


def test_composite_basic_formula():
    """composite = cvr - ucr - 0.1*severity - 0.001*loc_delta."""
    s = AcceptanceScore(
        citation_validation_rate=0.9,
        unsupported_claim_rate=0.1,
        referee_severity_max=2,
        simplicity_delta=100.0,
    )
    expected = 0.9 - 0.1 - 0.1 * 2 - 0.001 * 100.0
    assert s.composite() == pytest.approx(expected)


def test_composite_severity_none_treated_as_zero():
    s = AcceptanceScore(
        citation_validation_rate=0.8,
        unsupported_claim_rate=0.2,
        referee_severity_max=None,
    )
    assert s.composite() == pytest.approx(0.6)


def test_composite_simplicity_default_zero():
    s = AcceptanceScore(citation_validation_rate=1.0, unsupported_claim_rate=0.0)
    assert s.composite() == pytest.approx(1.0)


def test_composite_higher_is_better_under_simplicity():
    """Larger LOC delta lightly *lowers* composite even when other terms tie."""
    a = AcceptanceScore(
        citation_validation_rate=0.5,
        unsupported_claim_rate=0.1,
        simplicity_delta=10.0,
    )
    b = AcceptanceScore(
        citation_validation_rate=0.5,
        unsupported_claim_rate=0.1,
        simplicity_delta=1000.0,
    )
    assert a.composite() > b.composite()


# ---------------------------------------------------------------- run


def _make_score_iter(values: list[float]) -> Iterator[AcceptanceScore]:
    for v in values:
        yield AcceptanceScore(citation_validation_rate=v, unsupported_claim_rate=0.0)


def _disable_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the loop to skip git operations (simulates no git available)."""
    monkeypatch.setattr(research_loop_mod.shutil, "which", lambda _name: None)


def test_run_keeps_improvements_and_discards_regressions(tmp_path: Path, monkeypatch):
    """Sequence [0.5, 0.7, 0.6] → keep, keep, discard."""
    _disable_git(monkeypatch)
    scores = _make_score_iter([0.5, 0.7, 0.6])

    def _factory():
        return object()

    def _score_fn(_plato):
        return next(scores)

    loop = ResearchLoop(
        project_dir=tmp_path,
        max_iters=3,
        time_budget_hours=1.0,
        max_cost_usd=1_000.0,
    )
    summary = asyncio.run(loop.run(_factory, _score_fn))

    assert summary["iterations"] == 3
    assert summary["kept"] == 2
    assert summary["discarded"] == 1
    assert summary["best_composite"] == pytest.approx(0.7)

    rows = (tmp_path / "runs.tsv").read_text().splitlines()
    assert rows[0] == "iter\ttimestamp\tcomposite\tstatus\tdescription"
    statuses = [line.split("\t")[3] for line in rows[1:]]
    assert statuses == ["keep", "keep", "discard"]


def test_max_iters_honored(tmp_path: Path, monkeypatch):
    """Loop stops after max_iters even with infinite improvement."""
    _disable_git(monkeypatch)
    counter = {"i": 0}

    def _factory():
        return object()

    def _score_fn(_plato):
        counter["i"] += 1
        return AcceptanceScore(
            citation_validation_rate=counter["i"] / 10.0,
            unsupported_claim_rate=0.0,
        )

    loop = ResearchLoop(
        project_dir=tmp_path,
        max_iters=2,
        time_budget_hours=1.0,
        max_cost_usd=1_000.0,
    )
    summary = asyncio.run(loop.run(_factory, _score_fn))
    assert summary["iterations"] == 2
    assert counter["i"] == 2


def test_max_cost_usd_honored(tmp_path: Path, monkeypatch):
    """When a manifest pushes cumulative cost past the cap, the next iter stops."""
    _disable_git(monkeypatch)

    runs_dir = tmp_path / "runs" / "first"
    runs_dir.mkdir(parents=True)
    # Initial manifest below cap.
    (runs_dir / "manifest.json").write_text(json.dumps({"cost_usd": 1.0}))

    triggered = {"big_manifest_written": False}

    def _factory():
        # On the second iteration, drop a big manifest that exceeds the cap.
        if triggered["big_manifest_written"]:
            return object()
        d = tmp_path / "runs" / "expensive"
        d.mkdir(parents=True, exist_ok=True)
        (d / "manifest.json").write_text(json.dumps({"cost_usd": 999.0}))
        triggered["big_manifest_written"] = True
        return object()

    def _score_fn(_plato):
        return AcceptanceScore(citation_validation_rate=0.5, unsupported_claim_rate=0.0)

    loop = ResearchLoop(
        project_dir=tmp_path,
        max_iters=10,
        time_budget_hours=1.0,
        max_cost_usd=10.0,  # cap = 10 USD
    )
    summary = asyncio.run(loop.run(_factory, _score_fn))
    # First iter ran (pre-existing 1.0 USD < 10.0); second iter dropped the
    # 999.0-USD manifest; the *next* should-stop check halts the loop.
    assert summary["iterations"] >= 1
    assert summary["iterations"] < 10


def test_handle_interrupt_writes_clean_row(tmp_path: Path, monkeypatch):
    """Calling _handle_interrupt mid-loop leaves a complete TSV with the interrupted row."""
    _disable_git(monkeypatch)

    loop = ResearchLoop(
        project_dir=tmp_path,
        max_iters=5,
        time_budget_hours=1.0,
        max_cost_usd=1_000.0,
    )
    loop._open_tsv()
    loop._iter = 1
    loop._write_row(composite=0.5, status="keep", description="iter 1")

    with pytest.raises(KeyboardInterrupt):
        loop._handle_interrupt()

    # TSV is closed and ends with an interrupted row.
    rows = (tmp_path / "runs.tsv").read_text().splitlines()
    assert rows[0] == "iter\ttimestamp\tcomposite\tstatus\tdescription"
    assert any(line.split("\t")[3] == "interrupted" for line in rows[1:])
    # Handle is closed.
    assert loop._tsv_handle is None


def test_run_without_git_warns_once_and_continues(tmp_path: Path, monkeypatch, caplog):
    """When `git` isn't on PATH, the loop logs a warning and runs normally."""
    monkeypatch.setattr(research_loop_mod.shutil, "which", lambda _name: None)

    scores = _make_score_iter([0.4, 0.6])

    def _factory():
        return object()

    def _score_fn(_plato):
        return next(scores)

    with caplog.at_level("WARNING", logger="plato.loop.research_loop"):
        loop = ResearchLoop(
            project_dir=tmp_path,
            max_iters=2,
            time_budget_hours=1.0,
            max_cost_usd=1_000.0,
        )
        summary = asyncio.run(loop.run(_factory, _score_fn))

    assert summary["iterations"] == 2
    git_warnings = [
        r for r in caplog.records if "git checkpoint disabled" in r.getMessage()
    ]
    assert len(git_warnings) == 1, (
        "Expected exactly one git-unavailable warning, got "
        f"{[r.getMessage() for r in git_warnings]}"
    )


def test_run_subprocess_failure_warns_once(tmp_path: Path, monkeypatch, caplog):
    """If subprocess raises (simulates a broken git install), the loop still completes."""

    def _boom(*_args, **_kw):
        raise FileNotFoundError("git not installed")

    monkeypatch.setattr(research_loop_mod.subprocess, "check_output", _boom)
    monkeypatch.setattr(research_loop_mod.subprocess, "run", _boom)
    # shutil.which() may still find `git`, so we can exercise the run() path.

    scores = _make_score_iter([0.3])

    def _factory():
        return object()

    def _score_fn(_plato):
        return next(scores)

    with caplog.at_level("WARNING", logger="plato.loop.research_loop"):
        loop = ResearchLoop(
            project_dir=tmp_path,
            max_iters=1,
            time_budget_hours=1.0,
            max_cost_usd=1_000.0,
        )
        summary = asyncio.run(loop.run(_factory, _score_fn))

    assert summary["iterations"] == 1
    git_warnings = [
        r for r in caplog.records if "git checkpoint disabled" in r.getMessage()
    ]
    assert len(git_warnings) == 1


def test_summary_contains_tsv_path(tmp_path: Path, monkeypatch):
    _disable_git(monkeypatch)

    def _factory():
        return object()

    def _score_fn(_plato):
        return AcceptanceScore(citation_validation_rate=0.5, unsupported_claim_rate=0.0)

    loop = ResearchLoop(
        project_dir=tmp_path,
        max_iters=1,
        time_budget_hours=1.0,
        max_cost_usd=1_000.0,
    )
    summary = asyncio.run(loop.run(_factory, _score_fn))
    assert summary["tsv_path"] == str(tmp_path / "runs.tsv")
    assert Path(summary["tsv_path"]).exists()


# ---------------------------------------------------------------- CLI smoke


def test_cli_loop_subcommand_registered(capsys, monkeypatch):
    """`plato --help` lists the new `loop` subcommand alongside the existing ones."""
    from plato import cli as plato_cli

    monkeypatch.setattr(sys, "argv", ["plato", "--help"])
    with pytest.raises(SystemExit) as excinfo:
        plato_cli.main()
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    out = captured.out
    assert "loop" in out
    # Existing subcommands preserved.
    assert "run" in out
    assert "dashboard" in out


def test_cli_loop_subcommand_accepts_required_args(monkeypatch):
    """`plato loop --project-dir <dir>` parses without complaint and dispatches."""
    from plato import cli as plato_cli

    captured: dict = {}

    def _fake_run_loop(args):
        captured["project_dir"] = args.project_dir
        captured["hours"] = args.hours
        captured["max_iters"] = args.max_iters
        captured["max_cost_usd"] = args.max_cost_usd

    monkeypatch.setattr(plato_cli, "_run_loop", _fake_run_loop)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "plato",
            "loop",
            "--project-dir",
            "/tmp/plato-fake",
            "--hours",
            "2.5",
            "--max-iters",
            "4",
            "--max-cost-usd",
            "12.5",
        ],
    )
    plato_cli.main()
    assert captured == {
        "project_dir": "/tmp/plato-fake",
        "hours": 2.5,
        "max_iters": 4,
        "max_cost_usd": 12.5,
    }
