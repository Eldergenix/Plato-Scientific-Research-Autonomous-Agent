"""
Phase 3 — R7: Eval harness runner.

``EvalRunner`` is the entry point that ties ``GoldenTask`` → Plato run →
``Metrics`` → JSON sidecar. Phase 1 of the harness is intentionally a
skeleton: ``run`` accepts a ``plato_factory`` callable, executes a stub
workflow per task, and emits per-task and aggregate JSON. The full
pipeline integration (real ``Plato.get_paper`` calls, judge wiring) is
Phase 3+ and lives downstream of this PR.

The runner can be invoked directly via ``python -m evals.runner`` for
the nightly CI workflow.
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from evals.metrics import Metrics
from evals.tasks import GoldenTask, discover_tasks


# ``Plato`` is intentionally untyped here so the eval harness can be
# imported without pulling in the full Plato dependency graph (langchain,
# google-generativeai, etc.). The factory just needs to be a callable
# returning *something* the workflow can use.
PlatoFactory = Callable[[GoldenTask], Any]


class EvalRunner:
    """Runs a panel of golden tasks and emits JSON metrics sidecars."""

    def __init__(
        self,
        tasks: list[GoldenTask],
        *,
        output_dir: str | Path = "evals/results",
        max_cost_usd: float = 20.0,
    ) -> None:
        self.tasks = list(tasks)
        self.output_dir = Path(output_dir)
        self.max_cost_usd = float(max_cost_usd)

    async def run(
        self,
        plato_factory: PlatoFactory,
    ) -> dict[str, Metrics]:
        """Run every task and return ``{task_id: Metrics}``.

        For each task we:

        1. Call ``plato_factory(task)`` to build a (stub) Plato instance.
        2. Execute the workflow — for now a noop returning mock metrics.
        3. Write ``<output_dir>/<task_id>/metrics.json``.
        4. Bail out early if the running cost exceeds ``max_cost_usd``.

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
            plato_instance = plato_factory(task)
            metrics = await _run_task(task, plato_instance)
            metrics.latency_seconds = time.perf_counter() - start
            running_cost += metrics.cost_usd

            task_dir = self.output_dir / task.id
            task_dir.mkdir(parents=True, exist_ok=True)
            (task_dir / "metrics.json").write_text(
                json.dumps(metrics.model_dump(mode="json"), indent=2, sort_keys=True)
            )
            results[task.id] = metrics

        summary = _summarize(results)
        (self.output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True)
        )
        return results


async def _run_task(task: GoldenTask, plato_instance: Any) -> Metrics:
    """Stub workflow used by Phase 1 of the eval harness.

    Real wiring (calling ``plato_instance.get_paper`` and computing
    metrics from the resulting Sources/Claims/EvidenceLinks/manifest)
    lands in Phase 3+. Until then we return zeroed metrics so the rest
    of the harness — task discovery, JSON layout, summary aggregation,
    CI integration — can ship and be tested independently.

    The ``plato_instance`` argument is accepted so the contract matches
    the eventual real implementation; it may be ``None`` in tests.
    """
    # Touch the args so linters know we use them; it also makes the
    # behaviour obvious if a future change forgets to.
    _ = task
    _ = plato_instance

    # Allow the event loop to switch — keeps the function genuinely
    # async even though there is no I/O yet.
    await asyncio.sleep(0)

    return Metrics(
        citation_validation_rate=0.0,
        unsupported_claim_rate=0.0,
        novelty_consistency=None,
        referee_severity_max=None,
        paper_coherence=None,
        cost_usd=0.0,
        tokens_in=0,
        tokens_out=0,
        latency_seconds=0.0,
        tool_call_error_rate=None,
    )


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


def _default_plato_factory(_: GoldenTask) -> Any:
    """No-op factory used by ``python -m evals.runner`` in CI.

    The CI workflow passes ``PLATO_EVAL_MAX_USD`` to cap cost; with the
    Phase 1 stub workflow this is moot but keeps the contract honest.
    """
    return None


def main() -> None:
    """CLI entry point for ``python -m evals.runner`` (used by nightly CI)."""
    tasks = discover_tasks("evals/golden")
    max_usd = float(os.environ.get("PLATO_EVAL_MAX_USD", "20"))
    runner = EvalRunner(tasks, max_cost_usd=max_usd)
    asyncio.run(runner.run(_default_plato_factory))


if __name__ == "__main__":
    main()


__all__ = ["EvalRunner", "PlatoFactory"]
