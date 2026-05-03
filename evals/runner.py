"""
Phase 3 — R7: Eval harness runner.

``EvalRunner`` ties ``GoldenTask`` → Plato run → ``Metrics`` → JSON sidecar.

Per task we drive the Plato pipeline (``set_data_description`` →
``get_idea`` → ``get_method``) inside an isolated ``project_dir``,
catching any exception so a single failing task can't take down the
panel. Heavy stages (``get_results``, ``get_paper``) are skipped — they
require cmbagent / LaTeX and aren't wired into the harness yet.

Metrics are aggregated from the per-run manifests Plato drops at
``project_dir/runs/<run_id>/manifest.json``, plus any
``validation_report.json`` / ``evidence_matrix.jsonl`` artifacts the
Stream A pipeline writes alongside.

The runner can be invoked via ``python -m evals.runner`` or
``python -m evals`` for the nightly CI workflow.
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from evals.judge import LLMJudge
from evals.metrics import Metrics
from evals.tasks import GoldenTask, discover_tasks


# Default 3-model panel. Anti-self-judging is enforced inside LLMJudge,
# so as long as the drafting model isn't in this list the judge runs.
# Override per-instance via ``EvalRunner(..., judge_models=[...])``.
DEFAULT_JUDGE_MODELS = ("gpt-4o", "claude-sonnet-4-5", "gemini-2.5-pro")


# ``Plato`` is intentionally untyped here so the eval harness can be
# imported without pulling in the full Plato dependency graph (langchain,
# google-generativeai, etc.). The factory just needs to be a callable
# returning an instance with ``set_data_description``/``get_idea``/``get_method``.
PlatoFactory = Callable[[GoldenTask, Path], Any]


class EvalRunner:
    """Runs a panel of golden tasks and emits JSON metrics sidecars."""

    def __init__(
        self,
        tasks: list[GoldenTask],
        *,
        output_dir: str | Path = "evals/results",
        max_cost_usd: float = 20.0,
        idea_mode: str = "fast",
        method_mode: str = "fast",
        judge_models: list[str] | None = None,
        drafting_model: str = "gpt-4.1",
    ) -> None:
        self.tasks = list(tasks)
        self.output_dir = Path(output_dir)
        self.max_cost_usd = float(max_cost_usd)
        self.idea_mode = idea_mode
        self.method_mode = method_mode
        # Anti-self-judging guard inside LLMJudge will raise if
        # ``drafting_model`` is in the panel — keep the default list
        # disjoint from the default ``drafting_model``.
        self.judge_models = list(judge_models or DEFAULT_JUDGE_MODELS)
        self.drafting_model = drafting_model

    async def run(
        self,
        plato_factory: PlatoFactory,
    ) -> dict[str, Metrics]:
        """Run every task and return ``{task_id: Metrics}``.

        For each task we:

        1. Carve out ``<output_dir>/<task_id>/project`` for Plato's outputs.
        2. Build a Plato instance via ``plato_factory(task, project_dir)``.
        3. Drive ``set_data_description`` → ``get_idea`` → ``get_method``.
        4. Aggregate metrics from manifests + validation/evidence artifacts.
        5. Write ``metrics.json`` and stop early if running cost exceeds
           ``max_cost_usd``.

        Per-task failures are caught and recorded as ``Metrics`` with
        ``tool_call_error_rate=1.0`` so the panel keeps moving.

        Finally we emit ``<output_dir>/summary.json`` with mean / p50 /
        p95 of every numeric metric across the tasks that ran.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        results: dict[str, Metrics] = {}
        running_cost = 0.0

        for task in self.tasks:
            if running_cost >= self.max_cost_usd:
                break

            start = time.perf_counter()
            # Pass the panel-level remaining budget so the per-task
            # run can stop between pipeline stages instead of running
            # to completion before the next inter-task check fires.
            remaining = max(self.max_cost_usd - running_cost, 0.0)
            metrics = await asyncio.to_thread(
                self._run_task, task, plato_factory, remaining_budget_usd=remaining
            )
            wall = time.perf_counter() - start
            # Prefer manifest-derived latency when present; fall back to wall clock.
            if metrics.latency_seconds == 0.0:
                metrics.latency_seconds = wall
            running_cost += metrics.cost_usd

            task_dir = self.output_dir / task.id
            task_dir.mkdir(parents=True, exist_ok=True)

            # Score the drafted paper with the LLM judge panel + the
            # task's expected keywords / gold sources. Failures don't
            # abort the panel — populate what we can and keep going.
            await self._score_against_task(metrics, task, task_dir / "project")

            (task_dir / "metrics.json").write_text(
                json.dumps(metrics.model_dump(mode="json"), indent=2, sort_keys=True)
            )
            results[task.id] = metrics

        summary = _summarize(results)
        (self.output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True)
        )
        return results

    def _run_task(
        self,
        task: GoldenTask,
        plato_factory: PlatoFactory,
        *,
        remaining_budget_usd: float | None = None,
    ) -> Metrics:
        """Drive the real Plato pipeline for a single golden task.

        Tests inject a mock factory that writes synthetic manifests; in
        production this calls into ``plato.plato.Plato``. Any exception
        from the Plato run is caught and surfaced as an error Metrics
        record so the panel keeps moving.

        ``remaining_budget_usd`` is checked between pipeline stages
        (after each ``get_idea`` / ``get_method``) so a single
        expensive task can't silently exceed the panel-level cap. The
        check happens by inspecting freshly-written manifest files
        rather than instrumenting Plato directly — keeps the runner
        free of provider-specific cost-tracking knowledge.
        """
        project_dir = self.output_dir / task.id / "project"
        project_dir.mkdir(parents=True, exist_ok=True)

        try:
            plato = plato_factory(task, project_dir)
        except Exception:  # pragma: no cover - factory failures are rare
            return _error_metrics()

        def _budget_blown() -> bool:
            if remaining_budget_usd is None:
                return False
            spent = sum(
                float(m.get("cost_usd", 0) or 0)
                for m in _read_manifests(project_dir / "runs")
            )
            return spent >= remaining_budget_usd

        try:
            plato.set_data_description(task.data_description)
            plato.get_idea(mode=self.idea_mode)
            if _budget_blown():
                # Stop after idea — the next stage would push us over.
                return self._aggregate_metrics(project_dir)
            plato.get_method(mode=self.method_mode)
            # get_results / get_paper are intentionally skipped: they
            # require cmbagent + LaTeX and produce too much variance for
            # the harness today. Stream B/C wires them in once they're
            # stable.
        except Exception:
            # Aggregate whatever manifests/artifacts the run did write
            # before crashing, then mark the run as a tool error.
            # ``tool_call_error_rate=1.0`` is the sole failure signal;
            # we deliberately do *not* mutate ``unsupported_claim_rate``
            # here — that field's "0.0" is a legitimate value for a run
            # that simply hasn't drafted any claims yet (success or
            # failure), and conflating "I crashed" with "I have nothing
            # to support" double-counts the failure.
            metrics = self._aggregate_metrics(project_dir)
            metrics.tool_call_error_rate = 1.0
            return metrics

        return self._aggregate_metrics(project_dir)

    async def _score_against_task(
        self,
        metrics: Metrics,
        task: GoldenTask,
        project_dir: Path,
    ) -> None:
        """Run the LLM judge + keyword/gold-source scoring on a finished task.

        Mutates ``metrics`` in place. Any failure in the judge call or
        keyword recall is logged into ``metrics.tool_call_error_rate``
        rather than crashing the panel — the harness must always
        produce a metrics row per task.
        """
        # 1. Pull the drafted artifacts from the project_dir.
        idea_text = _read_artifact(project_dir, "input_files/idea.md")
        method_text = _read_artifact(project_dir, "input_files/methods.md")
        paper_text = _read_artifact(project_dir, "paper/paper_v1.tex") or (idea_text or "") + "\n" + (method_text or "")

        # 2. Compute keyword recall against task.expected_idea_keywords.
        if task.expected_idea_keywords and (idea_text or method_text):
            haystack = ((idea_text or "") + " " + (method_text or "")).lower()
            hits = sum(
                1
                for kw in task.expected_idea_keywords
                if kw.lower() in haystack
            )
            metrics.keyword_recall = hits / len(task.expected_idea_keywords)

        # 3. Compute gold-source recall against task.gold_sources.
        if task.gold_sources:
            hits = 0
            sources_text = paper_text.lower()
            for gold in task.gold_sources:
                # Match on either DOI substring or arxiv id substring —
                # whichever the gold ref provides.
                doi = (gold.get("doi") or "").lower().strip()
                arxiv = (gold.get("arxiv_id") or "").lower().strip()
                if (doi and doi in sources_text) or (arxiv and arxiv in sources_text):
                    hits += 1
            metrics.gold_source_recall = hits / len(task.gold_sources)

        # 4. LLM judge panel — only run when we have some paper text.
        if paper_text.strip() and self.drafting_model not in self.judge_models:
            try:
                judge = LLMJudge(self.judge_models)
                result = await judge.judge(
                    paper_text=paper_text,
                    drafting_model=self.drafting_model,
                )
                # Map the 0..5 axis scores into the existing metrics
                # fields. paper_coherence == coherence; we average
                # rigor + grounding into novelty_consistency as a
                # stand-in until a dedicated novelty signal lands.
                metrics.paper_coherence = float(result.coherence)
                metrics.referee_severity_max = max(
                    0.0, 5.0 - float(result.rigor)
                )
                metrics.novelty_consistency = float(result.novelty)
            except Exception:  # noqa: BLE001
                # Surface as a tool error but don't kill the panel.
                metrics.tool_call_error_rate = max(
                    metrics.tool_call_error_rate or 0.0, 0.5
                )

    def _aggregate_metrics(self, project_dir: Path) -> Metrics:
        """Compute Metrics from manifests + Stream A artifacts under project_dir."""
        runs_dir = project_dir / "runs"
        manifests = _read_manifests(runs_dir)

        tokens_in = sum(int(m.get("tokens_in", 0) or 0) for m in manifests)
        tokens_out = sum(int(m.get("tokens_out", 0) or 0) for m in manifests)
        cost_usd = float(sum(float(m.get("cost_usd", 0) or 0) for m in manifests))
        latency_seconds = _sum_latency(manifests)

        validation_rate = _validation_rate_from_artifacts(project_dir)
        unsupported_rate = _unsupported_rate_from_artifacts(project_dir)

        return Metrics(
            citation_validation_rate=validation_rate,
            unsupported_claim_rate=unsupported_rate,
            novelty_consistency=None,
            referee_severity_max=None,
            paper_coherence=None,
            cost_usd=cost_usd,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_seconds=latency_seconds,
            tool_call_error_rate=None,
        )


def _read_artifact(project_dir: Path, rel_path: str) -> str:
    """Read a project-dir artifact, returning ``""`` on any failure."""
    path = project_dir / rel_path
    if not path.is_file():
        return ""
    try:
        return path.read_text()
    except OSError:
        return ""


def _error_metrics() -> Metrics:
    """Metrics record for a task that couldn't even start."""
    return Metrics(
        citation_validation_rate=0.0,
        unsupported_claim_rate=1.0,
        novelty_consistency=None,
        referee_severity_max=None,
        paper_coherence=None,
        cost_usd=0.0,
        tokens_in=0,
        tokens_out=0,
        latency_seconds=0.0,
        tool_call_error_rate=1.0,
    )


def _read_manifests(runs_dir: Path) -> list[dict[str, Any]]:
    """Load every ``manifest.json`` under ``runs_dir``. Skips malformed files."""
    if not runs_dir.exists() or not runs_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for manifest_path in sorted(runs_dir.glob("*/manifest.json")):
        try:
            out.append(json.loads(manifest_path.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def _sum_latency(manifests: list[dict[str, Any]]) -> float:
    """Sum (ended_at - started_at) per finished manifest, in seconds."""
    from datetime import datetime

    total = 0.0
    for m in manifests:
        start_str = m.get("started_at")
        end_str = m.get("ended_at")
        if not start_str or not end_str:
            continue
        try:
            start = datetime.fromisoformat(start_str)
            end = datetime.fromisoformat(end_str)
        except (TypeError, ValueError):
            continue
        delta = (end - start).total_seconds()
        if delta > 0:
            total += delta
    return total


def _validation_rate_from_artifacts(project_dir: Path) -> float:
    """Read every ``validation_report.json`` and compute the validation rate.

    Stream A writes these as a list of ``ValidationResult``-shaped dicts
    or as a single ``{"results": [...]}`` envelope. Empty inputs → 0.0.
    """
    rows: list[dict[str, Any]] = []
    for path in sorted(project_dir.rglob("validation_report.json")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, list):
            rows.extend(p for p in payload if isinstance(p, dict))
        elif isinstance(payload, dict):
            inner = payload.get("results") or payload.get("validations") or []
            if isinstance(inner, list):
                rows.extend(p for p in inner if isinstance(p, dict))
    if not rows:
        return 0.0
    valid = sum(
        1
        for r in rows
        if (r.get("doi_resolved") or r.get("arxiv_resolved"))
        and not r.get("retracted")
    )
    return valid / len(rows)


def _unsupported_rate_from_artifacts(project_dir: Path) -> float:
    """Read ``evidence_matrix.jsonl`` and compute unsupported claim rate.

    The matrix is one JSON object per line; each row is either a Claim
    or an EvidenceLink, identified by the keys present. Empty input → 0.0.
    """
    claims: list[str] = []
    supported: set[str] = set()
    for path in sorted(project_dir.rglob("evidence_matrix.jsonl")):
        try:
            text = path.read_text()
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            if "text" in row and "id" in row:  # Claim-shaped
                claims.append(str(row["id"]))
            elif row.get("support") == "supports" and "claim_id" in row:
                supported.add(str(row["claim_id"]))
    if not claims:
        return 0.0
    unsupported = sum(1 for cid in claims if cid not in supported)
    return unsupported / len(claims)


def _summarize(results: dict[str, Metrics]) -> dict[str, Any]:
    """Compute mean / p50 / p95 of every numeric metric across tasks."""
    summary: dict[str, Any] = {
        "task_count": len(results),
        "task_ids": sorted(results.keys()),
        "metrics": {},
    }
    if not results:
        return summary

    fields = [
        "citation_validation_rate",
        "unsupported_claim_rate",
        "novelty_consistency",
        "referee_severity_max",
        "paper_coherence",
        "cost_usd",
        "tokens_in",
        "tokens_out",
        "latency_seconds",
        "tool_call_error_rate",
        "keyword_recall",
        "gold_source_recall",
    ]
    for field in fields:
        values = [
            getattr(m, field)
            for m in results.values()
            if getattr(m, field) is not None
        ]
        if not values:
            summary["metrics"][field] = {"count": 0}
            continue
        floats = [float(v) for v in values]
        summary["metrics"][field] = {
            "count": len(floats),
            "mean": statistics.fmean(floats),
            "p50": _percentile(floats, 50),
            "p95": _percentile(floats, 95),
        }
    return summary


def _percentile(values: list[float], pct: float) -> float:
    """Inclusive linear-interpolation percentile (0 ≤ pct ≤ 100)."""
    if not values:
        raise ValueError("percentile requires at least one value")
    if len(values) == 1:
        return values[0]
    sorted_vals = sorted(values)
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = rank - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _default_plato_factory(task: GoldenTask, project_dir: Path) -> Any:
    """Build a real ``Plato`` instance for the nightly CI workflow.

    Imports ``Plato`` lazily so ``python -m evals.runner --help`` still
    works in environments without the heavy LLM stack installed.
    """
    from plato.plato import Plato  # local import keeps eval imports light

    return Plato(project_dir=str(project_dir), clear_project_dir=True)


def main() -> None:
    """CLI entry point for ``python -m evals[.runner]`` (used by nightly CI)."""
    tasks = discover_tasks("evals/golden")
    max_usd = float(os.environ.get("PLATO_EVAL_MAX_USD", "20"))
    runner = EvalRunner(tasks, max_cost_usd=max_usd)
    asyncio.run(runner.run(_default_plato_factory))


if __name__ == "__main__":
    main()


__all__ = ["EvalRunner", "PlatoFactory"]
