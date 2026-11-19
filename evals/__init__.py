"""
Phase 3 — R7: evaluation harness.

Public surface re-exported for convenience:

- ``GoldenTask`` — Pydantic schema for an individual eval task.
- ``Metrics`` — per-task / per-run result schema.
- ``EvalRunner`` — orchestrates tasks → metrics → JSON sidecars.
- ``LLMJudge`` — multi-model judge with anti-self-grading safeguards.
"""

from __future__ import annotations

from evals.judge import JudgeResult, LLMJudge
from evals.metrics import (
    Metrics,
    citation_validation_rate,
    unsupported_claim_rate,
)
from evals.runner import EvalRunner
from evals.tasks import GoldenTask, discover_tasks, load_task

__all__ = [
    "EvalRunner",
    "GoldenTask",
    "JudgeResult",
    "LLMJudge",
    "Metrics",
    "citation_validation_rate",
    "discover_tasks",
    "load_task",
    "unsupported_claim_rate",
]
