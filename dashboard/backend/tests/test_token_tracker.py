"""Unit tests for token aggregation + cost estimation."""

from __future__ import annotations

from pathlib import Path

import pytest

from plato_dashboard.worker.token_tracker import (
    aggregate_project_usage,
    clear_run_ledger,
    estimate_cost_cents,
    get_run_usage,
    parse_llm_calls_file,
    record_tokens_delta,
    reconcile_run,
)


def test_estimate_cost_cents_gpt5() -> None:
    """gpt-5: 4000 prompt + 1000 completion → $0.10 = 10 cents."""
    assert estimate_cost_cents("gpt-5", 4000, 1000) == 10


def test_estimate_cost_cents_unknown_model_returns_zero() -> None:
    assert estimate_cost_cents("unknown-xyz", 1000, 1000) == 0


def test_parse_llm_calls_file_skips_malformed_lines(tmp_path: Path) -> None:
    f = tmp_path / "LLM_calls.txt"
    f.write_text(
        "\n".join(
            [
                "# header comment",
                "input_tokens=100 output_tokens=50 model=gpt-5",
                "garbage with no key=value",
                "",
                "input_tokens=0 output_tokens=0 model=gpt-5",  # zero-tok → skipped
                "input_tokens=200 output_tokens=100 model=gpt-4o",
            ]
        )
        + "\n"
    )
    records = parse_llm_calls_file(f)
    # Header / blank / zero-tok / no-kv lines are dropped — two real records.
    assert len(records) == 2
    assert records[0].model == "gpt-5"
    assert records[0].input_tokens == 100
    assert records[0].output_tokens == 50
    assert records[1].model == "gpt-4o"
    assert records[1].input_tokens == 200


def test_aggregate_project_usage_sums_across_stages(tmp_path: Path) -> None:
    proj = tmp_path / "prj_demo"
    (proj / "idea_generation_output").mkdir(parents=True)
    (proj / "idea_generation_output" / "LLM_calls.txt").write_text(
        "input_tokens=4000 output_tokens=1000 model=gpt-5\n"
    )
    (proj / "method_generation_output").mkdir(parents=True)
    (proj / "method_generation_output" / "LLM_calls.txt").write_text(
        "input_tokens=2000 output_tokens=500 model=gpt-5\n"
    )

    usage = aggregate_project_usage(proj)
    assert usage.total_input == 6000
    assert usage.total_output == 1500
    # 4k+1k of gpt-5 = 10c; 2k+0.5k of gpt-5 = (2*0.0125 + 0.5*0.05) = 0.05 = 5c
    assert usage.total_cost_cents == 15
    assert "idea" in usage.by_stage
    assert "method" in usage.by_stage
    assert usage.by_stage["idea"].input_tokens == 4000
    assert usage.by_stage["method"].input_tokens == 2000


def test_record_tokens_delta_updates_live_ledger() -> None:
    clear_run_ledger()
    record_tokens_delta("run_a", "gpt-5", 1000, 200)
    record_tokens_delta("run_a", "gpt-5", 3000, 800)

    snap = get_run_usage("run_a")
    assert snap.input_tokens == 4000
    assert snap.output_tokens == 1000
    assert snap.cost_cents == 10
    assert snap.model == "gpt-5"


def test_reconcile_run_replaces_with_canonical(tmp_path: Path) -> None:
    clear_run_ledger()

    # Live ledger picks up some streaming updates...
    record_tokens_delta("run_b", "gpt-5", 999, 999)
    assert get_run_usage("run_b").input_tokens == 999

    # ...then the on-disk file reveals the canonical totals.
    proj = tmp_path / "prj_x"
    idea_dir = proj / "idea_generation_output"
    idea_dir.mkdir(parents=True)
    (idea_dir / "LLM_calls.txt").write_text(
        "input_tokens=4000 output_tokens=1000 model=gpt-5\n"
    )

    canonical = reconcile_run("run_b", proj, "idea")
    assert canonical.input_tokens == 4000
    assert canonical.output_tokens == 1000
    # And the ledger entry was replaced (not merged).
    assert get_run_usage("run_b").input_tokens == 4000
