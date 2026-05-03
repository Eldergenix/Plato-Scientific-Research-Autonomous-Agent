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


router = APIRouter()


_DEFAULT_SUMMARY_PATH = Path("evals/results/summary.json")


@router.get("/evals/summary", response_model=JsonObjectResponse)
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


__all__ = ["router"]
