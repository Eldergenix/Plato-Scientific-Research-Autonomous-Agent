"""Phase 3 — R7: tests for the evaluation harness (no real LLM/network)."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
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


class _FakePlato:
    """Mock Plato that drops a synthetic manifest per pipeline stage.

    Mirrors the real ``Plato`` surface enough for ``EvalRunner._run_task``
    to drive an end-to-end run without touching LLMs, the network, or
    cmbagent. Each call writes a manifest.json under ``runs/<uuid>/``
    matching ``RunManifest``'s schema (only the fields the runner reads).
    """

    def __init__(
        self,
        project_dir: Path,
        *,
        tokens_per_call: int = 100,
        cost_per_call: float = 0.01,
        latency_per_call: float = 0.5,
        crash_at: str | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.tokens_per_call = tokens_per_call
        self.cost_per_call = cost_per_call
        self.latency_per_call = latency_per_call
        self.crash_at = crash_at
        self.calls: list[str] = []

    def _emit_manifest(self, workflow: str) -> None:
        run_id = uuid.uuid4().hex[:12]
        run_dir = self.project_dir / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        started = datetime.now(timezone.utc)
        ended = started + timedelta(seconds=self.latency_per_call)
        payload = {
            "run_id": run_id,
            "workflow": workflow,
            "started_at": started.isoformat(),
            "ended_at": ended.isoformat(),
            "status": "success",
            "tokens_in": self.tokens_per_call,
            "tokens_out": self.tokens_per_call // 2,
            "cost_usd": self.cost_per_call,
            "domain": "astro",
        }
        (run_dir / "manifest.json").write_text(json.dumps(payload, indent=2, sort_keys=True))

    def set_data_description(self, data_description: str) -> None:
        self.calls.append("set_data_description")
        if self.crash_at == "set_data_description":
            raise RuntimeError("boom")
        # Real Plato only emits manifests on workflow methods; do the same.

    def get_idea(self, mode: str = "fast") -> None:
        self.calls.append(f"get_idea:{mode}")
        if self.crash_at == "get_idea":
            raise RuntimeError("boom")
        self._emit_manifest("get_idea_fast")

    def get_method(self, mode: str = "fast") -> None:
        self.calls.append(f"get_method:{mode}")
        if self.crash_at == "get_method":
            raise RuntimeError("boom")
        self._emit_manifest("get_method_fast")


def _basic_tasks() -> list[GoldenTask]:
    return [
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


def test_eval_runner_run_writes_summary_json(tmp_path: Path):
    """Mock plato_factory; runner emits per-task metrics + summary.json."""
    runner = EvalRunner(_basic_tasks(), output_dir=tmp_path / "results", max_cost_usd=1.0)
    factory_calls: list[str] = []

    def factory(task: GoldenTask, project_dir: Path):
        factory_calls.append(task.id)
        # Cheap mock: zero tokens/cost, no manifests written.
        return _FakePlato(project_dir, tokens_per_call=0, cost_per_call=0.0)

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


def test_eval_runner_aggregates_tokens_from_mock_plato(tmp_path: Path):
    """Mock Plato writes manifests; runner sums tokens/cost across stages."""
    tasks = [
        GoldenTask(
            id="osc",
            data_description="describe an oscillator",
            expected_idea_keywords=[],
            expected_method_signals=[],
            gold_sources=[],
        )
    ]
    runner = EvalRunner(tasks, output_dir=tmp_path / "results", max_cost_usd=10.0)

    def factory(task: GoldenTask, project_dir: Path):
        return _FakePlato(
            project_dir,
            tokens_per_call=100,
            cost_per_call=0.05,
            latency_per_call=0.25,
        )

    results = asyncio.run(runner.run(factory))

    metrics = results["osc"]
    # get_idea + get_method each emit a manifest with 100 in / 50 out.
    assert metrics.tokens_in == 200
    assert metrics.tokens_out == 100
    assert metrics.cost_usd == pytest.approx(0.10)
    # Latency from manifests (≈0.5s) preferred over wall clock.
    assert metrics.latency_seconds >= 0.5
    assert metrics.tool_call_error_rate is None

    # summary.json exposes the aggregate.
    summary = json.loads((tmp_path / "results" / "summary.json").read_text())
    assert summary["task_count"] == 1
    assert summary["task_ids"] == ["osc"]
    assert summary["metrics"]["tokens_in"]["mean"] == pytest.approx(200)


def test_eval_runner_records_failure_when_plato_raises(tmp_path: Path):
    """A crashing Plato run produces tool_call_error_rate=1.0 and keeps moving."""
    tasks = [
        GoldenTask(
            id="boom",
            data_description="d",
            expected_idea_keywords=[],
            expected_method_signals=[],
            gold_sources=[],
        )
    ]
    runner = EvalRunner(tasks, output_dir=tmp_path / "results", max_cost_usd=10.0)

    def factory(task: GoldenTask, project_dir: Path):
        return _FakePlato(project_dir, crash_at="get_idea")

    results = asyncio.run(runner.run(factory))

    metrics = results["boom"]
    assert metrics.tool_call_error_rate == 1.0
    # No manifests were written before the crash → zero tokens/cost.
    assert metrics.tokens_in == 0
    assert metrics.tokens_out == 0
    # And vacuously-zero unsupported rate gets bumped to 1.0 on failure.
    assert metrics.unsupported_claim_rate == 1.0


def test_aggregate_metrics_reads_validation_and_evidence_artifacts(tmp_path: Path):
    """Stream A artifacts (validation_report.json + evidence_matrix.jsonl) feed metrics."""
    project = tmp_path / "task" / "project"
    runs_dir = project / "runs" / "abc123"
    runs_dir.mkdir(parents=True)
    started = datetime.now(timezone.utc)
    (runs_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "abc123",
                "workflow": "get_idea_fast",
                "started_at": started.isoformat(),
                "ended_at": (started + timedelta(seconds=2)).isoformat(),
                "status": "success",
                "tokens_in": 50,
                "tokens_out": 25,
                "cost_usd": 0.02,
            }
        )
    )
    # 4 validations: 3 valid, 1 unresolved → 0.75.
    (project / "validation_report.json").write_text(
        json.dumps(
            [
                {"source_id": "a", "doi_resolved": True, "retracted": False, "checked_at": started.isoformat()},
                {"source_id": "b", "arxiv_resolved": True, "retracted": False, "checked_at": started.isoformat()},
                {"source_id": "c", "doi_resolved": True, "retracted": False, "checked_at": started.isoformat()},
                {"source_id": "d", "doi_resolved": False, "arxiv_resolved": False, "checked_at": started.isoformat()},
            ]
        )
    )
    # 4 claims, 2 supported → unsupported_rate = 0.5.
    matrix = "\n".join(
        json.dumps(row)
        for row in [
            {"id": "c1", "text": "claim 1"},
            {"id": "c2", "text": "claim 2"},
            {"id": "c3", "text": "claim 3"},
            {"id": "c4", "text": "claim 4"},
            {"claim_id": "c1", "source_id": "a", "support": "supports", "strength": "moderate"},
            {"claim_id": "c2", "source_id": "b", "support": "supports", "strength": "strong"},
            {"claim_id": "c3", "source_id": "c", "support": "refutes", "strength": "weak"},
        ]
    )
    (project / "evidence_matrix.jsonl").write_text(matrix)

    runner = EvalRunner([], output_dir=tmp_path)
    metrics = runner._aggregate_metrics(project)

    assert metrics.citation_validation_rate == pytest.approx(0.75)
    assert metrics.unsupported_claim_rate == pytest.approx(0.5)
    assert metrics.tokens_in == 50
    assert metrics.tokens_out == 25
    assert metrics.cost_usd == pytest.approx(0.02)
    assert metrics.latency_seconds == pytest.approx(2.0)


def test_discover_tasks_picks_up_gw231123_followup():
    tasks = discover_tasks(GOLDEN_DIR)
    by_id = {t.id: t for t in tasks}
    assert "gw231123_followup" in by_id
    task = by_id["gw231123_followup"]
    assert "GW231123" in task.expected_idea_keywords
    assert task.gold_sources == ["10.3847/2041-8213/ad5ce4"]


def test_discover_tasks_picks_up_cmb_lensing_residuals():
    tasks = discover_tasks(GOLDEN_DIR)
    by_id = {t.id: t for t in tasks}
    assert "cmb_lensing_residuals" in by_id
    task = by_id["cmb_lensing_residuals"]
    assert "quadratic estimator" in task.expected_method_signals
    assert task.domain == "astro"
