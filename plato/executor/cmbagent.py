"""
``CmbagentExecutor`` — the default backend.

Wraps :class:`plato.experiment.Experiment` so the existing
``cmbagent.planning_and_control_context_carryover`` flow keeps working
unchanged behind the new :class:`~plato.executor.Executor` Protocol.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from . import ExecutorResult, register_executor

__all__ = ["CmbagentExecutor"]


class CmbagentExecutor:
    """Executor that delegates to the existing :class:`~plato.experiment.Experiment` wrapper."""

    name = "cmbagent"

    async def run(
        self,
        *,
        research_idea: str,
        methodology: str,
        data_description: str,
        project_dir: str | Path,
        keys: Any,
        **kwargs: Any,
    ) -> ExecutorResult:
        # Late import so this module is cheap to import even if cmbagent
        # isn't usable in the current environment (e.g. CI without LLM keys).
        # Surface a clear install hint matching modal/e2b — bare ImportError
        # from cmbagent's transitive graph is too noisy to be actionable.
        try:
            from ..experiment import Experiment
        except ImportError as exc:
            raise ImportError(
                "CmbagentExecutor requires cmbagent. "
                "Install it with: pip install 'plato[cmbagent]' "
                "or pip install cmbagent"
            ) from exc

        # Iter-4 path-traversal parity with sibling backends. cmbagent
        # writes scratch artefacts and plots under work_dir, so reject
        # paths outside the allowed roots before construction.
        from . import _safe_project_dir
        project_dir = _safe_project_dir(project_dir)

        experiment = Experiment(
            research_idea=research_idea,
            methodology=methodology,
            keys=keys,
            work_dir=str(project_dir),
            involved_agents=kwargs.get("involved_agents", ["engineer", "researcher"]),
            engineer_model=kwargs.get("engineer_model", "gpt-4.1"),
            researcher_model=kwargs.get("researcher_model", "o3-mini-2025-01-31"),
            planner_model=kwargs.get("planner_model", "gpt-4o"),
            plan_reviewer_model=kwargs.get("plan_reviewer_model", "o3-mini"),
            restart_at_step=kwargs.get("restart_at_step", -1),
            hardware_constraints=kwargs.get("hardware_constraints"),
            max_n_attempts=kwargs.get("max_n_attempts", 10),
            max_n_steps=kwargs.get("max_n_steps", 6),
            orchestration_model=kwargs.get("orchestration_model", "gpt-4.1"),
            formatter_model=kwargs.get("formatter_model", "o3-mini"),
        )

        # ``run_experiment`` is synchronous and may take a long time; off-load
        # it to a worker thread so callers can ``await`` without blocking the
        # event loop.
        await asyncio.to_thread(experiment.run_experiment, data_description)

        return ExecutorResult(
            results=experiment.results,
            plot_paths=list(experiment.plot_paths),
            artifacts={
                "executor": "cmbagent",
                # cmbagent flow runs as one logical unit, not per-cell.
                # Surface a `cells_executed` of 1 so dashboard consumers
                # that read this field don't KeyError on cmbagent runs.
                "cells_executed": 1,
                "had_error": False,
            },
        )


register_executor(CmbagentExecutor(), overwrite=True)
