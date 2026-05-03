"""Eval-harness summary view.

Surfaces the JSON artifact produced by ``python -m evals.runner`` so
the dashboard's ``/evals`` page can render trend tables without
shipping a custom static-file server. The path is resolved relative
to the repo root (``cwd``) since the eval runner writes its output
under ``evals/results/`` by convention.

When the file doesn't exist (no nightly has run yet, or the runner
crashed) we return ``404`` with a structured ``code`` so the
frontend can render an empty-state card pointing the user at the
nightly workflow.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..domain.models import JsonObjectResponse


router = APIRouter(tags=["evals"])


_DEFAULT_SUMMARY_PATH = Path("evals/results/summary.json")


_EVAL_SUMMARY_RESPONSES: dict[int | str, dict] = {
    404: {"description": "No `evals/results/summary.json` on disk yet."},
    500: {"description": "The summary file exists but is not valid JSON."},
}


@router.get(
    "/evals/summary",
    response_model=JsonObjectResponse,
    summary="Latest eval-harness summary",
    responses=_EVAL_SUMMARY_RESPONSES,
)
def get_eval_summary() -> dict:
    """Return the most recent ``summary.json`` produced by EvalRunner."""
    path = _DEFAULT_SUMMARY_PATH
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail={
                "code": "eval_summary_not_found",
                "message": (
                    "No evals/results/summary.json on disk yet. Run the "
                    "nightly workflow or `python -m evals.runner` to "
                    "generate one."
                ),
            },
        )
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "eval_summary_corrupt", "message": str(exc)},
        ) from exc


# Match a task id from a path segment. Same charset rule as the
# X-Plato-User regex from iter 4 — keeps a crafted id from escaping
# evals/results/ via path traversal.
import re

_TASK_ID_RE = re.compile(r"\A[A-Za-z0-9._-]{1,128}\Z")


@router.get(
    "/evals/tasks/{task_id}/metrics",
    response_model=JsonObjectResponse,
    summary="Per-task eval metrics",
    responses={
        400: {"description": "`task_id` does not match `[A-Za-z0-9._-]{1,128}`."},
        404: {"description": "No metrics on disk for this task."},
        500: {"description": "The metrics file exists but is not valid JSON."},
    },
)
def get_eval_task_metrics(task_id: str) -> dict:
    """Return ``evals/results/<task_id>/metrics.json`` for the drill-down view."""
    if not _TASK_ID_RE.match(task_id):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_task_id"},
        )
    path = Path("evals/results") / task_id / "metrics.json"
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail={"code": "eval_task_metrics_not_found", "task_id": task_id},
        )
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "eval_task_metrics_corrupt", "message": str(exc)},
        ) from exc


__all__ = ["router"]
