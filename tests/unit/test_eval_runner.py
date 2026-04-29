"""Phase 3 — R7: tests for the evaluation harness (no real LLM/network)."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from evals import EvalRunner, GoldenTask, LLMJudge, Metrics
from evals.judge import JudgeResult
from evals.metrics import citation_validation_rate, unsupported_claim_rate
from evals.tasks import discover_tasks, load_task
from plato.state.models import Claim, EvidenceLink, ValidationResult


REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "evals" / "golden"


def test_golden_task_validates_harmonic_oscillator_fixture():
    """The shipped harmonic_oscillator.json must validate cleanly."""
    payload = json.loads((GOLDEN_DIR / "harmonic_oscillator.json").read_text())
    task = GoldenTask.model_validate(payload)
    assert task.id == "harmonic_oscillator"
    assert "harmonic" in task.expected_idea_keywords
    assert task.domain == "astro"


def test_load_task_returns_golden_task(tmp_path: Path):
    """load_task reads a JSON file and returns a GoldenTask."""
    payload = {
        "id": "demo",
        "data_description": "demo task",
        "expected_idea_keywords": ["demo"],
        "expected_method_signals": ["demo"],
        "gold_sources": [],
        "domain": "astro",
    }
    p = tmp_path / "demo.json"
    p.write_text(json.dumps(payload))
    task = load_task(p)
    assert task.id == "demo"
    assert task.domain == "astro"


def test_discover_tasks_finds_harmonic_oscillator_json():
    """discover_tasks() picks up the harmonic_oscillator fixture."""
    tasks = discover_tasks(GOLDEN_DIR)
    ids = [t.id for t in tasks]
    assert "harmonic_oscillator" in ids


def test_discover_tasks_returns_empty_for_missing_dir(tmp_path: Path):
    assert discover_tasks(tmp_path / "nope") == []


def _vresult(*, doi_resolved: bool = False, arxiv_resolved: bool = False, retracted: bool = False) -> ValidationResult:
    return ValidationResult(
        source_id="x",
        doi_resolved=doi_resolved,
        arxiv_resolved=arxiv_resolved,
        retracted=retracted,
        checked_at=datetime.now(timezone.utc),
    )


def test_citation_validation_rate_three_valid_one_invalid():
    """3 valid + 1 invalid → 0.75."""
    validations = [
        _vresult(doi_resolved=True),
        _vresult(arxiv_resolved=True),
        _vresult(doi_resolved=True),
        _vresult(),  # neither resolved
    ]
    assert citation_validation_rate(validations) == pytest.approx(0.75)


def test_citation_validation_rate_empty_returns_zero():
    assert citation_validation_rate([]) == 0.0


def test_citation_validation_rate_excludes_retracted():
    """Even a resolved-DOI source does not count if it was retracted."""
    validations = [_vresult(doi_resolved=True, retracted=True)]
    assert citation_validation_rate(validations) == 0.0


def test_unsupported_claim_rate_four_claims_two_supported():
    """4 claims, 2 supported → 0.5."""
    claims = [Claim(id=str(i), text=f"claim {i}") for i in range(4)]
    links = [
        EvidenceLink(claim_id="0", source_id="s1", support="supports", strength="moderate"),
        EvidenceLink(claim_id="1", source_id="s2", support="supports", strength="strong"),
        # Other links exist but only 'supports' counts.
        EvidenceLink(claim_id="2", source_id="s3", support="refutes", strength="weak"),
    ]
    assert unsupported_claim_rate(claims, links) == pytest.approx(0.5)


def test_unsupported_claim_rate_empty_claims_returns_zero():
    assert unsupported_claim_rate([], []) == 0.0


def test_llm_judge_rejects_drafting_model_in_panel():
    """ValueError if drafting model is in the judge list (plan §7.3)."""
    judge = LLMJudge(judges=["gpt-4o", "claude-sonnet-4", "gemini-1.5-pro"])
    with pytest.raises(ValueError, match="never grade its own output"):
        asyncio.run(judge.judge(paper_text="hi", drafting_model="gpt-4o"))


def test_llm_judge_aggregates_three_mocked_calls_via_median():
    """3 mocked judges → per-axis median (statistics.median_low)."""
    judge = LLMJudge(judges=["A", "B", "C"])

    fake_results = [
        JudgeResult(coherence=5, grounding=4, novelty=3, rigor=2, rationale="A says"),
        JudgeResult(coherence=4, grounding=3, novelty=4, rigor=3, rationale="B says"),
        JudgeResult(coherence=3, grounding=5, novelty=5, rigor=4, rationale="C says"),
    ]
    judge._call_judge = AsyncMock(side_effect=fake_results)

    result = asyncio.run(
        judge.judge(paper_text="some paper", drafting_model="DRAFTER-not-in-panel")
    )
    # Medians: coherence sorted = [3,4,5] → 4; grounding [3,4,5] → 4;
    # novelty [3,4,5] → 4; rigor [2,3,4] → 3.
    assert result.coherence == 4
    assert result.grounding == 4
    assert result.novelty == 4
    assert result.rigor == 3
    assert "A says" in result.rationale
    assert "B says" in result.rationale
    assert "C says" in result.rationale


def test_eval_runner_run_writes_summary_json(tmp_path: Path):
    """Mock plato_factory; runner emits per-task metrics + summary.json."""
    tasks = [
        GoldenTask(
            id="t1",
            data_description="d",
            expected_idea_keywords=[],
            expected_method_signals=[],
            gold_sources=[],
        ),
        GoldenTask(
            id="t2",
            data_description="d",
            expected_idea_keywords=[],
            expected_method_signals=[],
            gold_sources=[],
        ),
    ]
    runner = EvalRunner(tasks, output_dir=tmp_path / "results", max_cost_usd=1.0)
    factory_calls: list[str] = []

    def factory(task: GoldenTask):
        factory_calls.append(task.id)
        return None

    results = asyncio.run(runner.run(factory))

    assert set(results.keys()) == {"t1", "t2"}
    assert factory_calls == ["t1", "t2"]
    # Per-task metrics.json exists for each.
    for tid in ("t1", "t2"):
        path = tmp_path / "results" / tid / "metrics.json"
        assert path.exists()
        loaded = Metrics.model_validate(json.loads(path.read_text()))
        assert loaded.cost_usd == 0.0
    # Summary.json aggregates.
    summary_path = tmp_path / "results" / "summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text())
    assert summary["task_count"] == 2
    assert summary["task_ids"] == ["t1", "t2"]
    assert "citation_validation_rate" in summary["metrics"]
