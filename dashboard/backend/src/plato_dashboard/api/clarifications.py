"""Clarifying-questions endpoints (Stream 3 / F2).

The Workflow #1 clarifier writes ``clarifying_questions`` and
``needs_clarification`` into the LangGraph state. When the run is
flushed, the manifest's ``extra`` block carries those fields too. This
router gives the frontend a way to fetch the questions and post answers
back so the run can resume.

The clarifier output is read from two locations, in priority order:

1. ``<run_dir>/clarifications.json`` - explicit, written by the
   clarifier node when it finishes.
2. ``<run_dir>/manifest.json`` - manifest fallback; we look in
   ``extra.clarifying_questions`` and ``extra.needs_clarification``.

Answers are written to ``<run_dir>/clarifications_answers.json`` with
a wall-clock ISO-8601 timestamp.

"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..domain.models import JsonObjectResponse
from ..settings import Settings, get_settings
from .manifests import _enforce_tenant, _find_run_dir, _read_json, _user_id


class ClarificationsAnswerRequest(BaseModel):
    """Body for ``POST /runs/{run_id}/clarifications``.

    The 50-answer cap blocks pathological payloads; per-answer length
    is capped at 4 KiB so a runaway client can't fill the project_dir
    with megabytes of free-form text before any LLM call has happened.
    """

    answers: list[Any] = Field(max_length=50)


router = APIRouter()


def _read_optional_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = _read_json(path)
    except HTTPException:
        return None
    return data if isinstance(data, dict) else None


def _check_tenant(run_dir: Path, run_id: str, request: Request) -> None:
    _enforce_tenant(run_dir, run_id, _user_id(request))


def _load_clarifications(run_dir: Path) -> tuple[list[str], bool]:
    """Resolve (questions, needs_clarification) from disk.

    Tries ``clarifications.json`` first, then ``manifest.json``'s
    ``extra`` block. Empty / unreadable files yield ``([], False)``.
    """
    explicit = _read_optional_object(run_dir / "clarifications.json")
    if explicit is not None:
        questions = explicit.get("questions") or []
        needs = bool(explicit.get("needs_clarification", bool(questions)))
        if isinstance(questions, list):
            return [str(q) for q in questions], needs
        return [], needs

    manifest = _read_optional_object(run_dir / "manifest.json")
    if manifest:
        extra = manifest.get("extra") or {}
        questions = extra.get("clarifying_questions") or []
        needs = bool(extra.get("needs_clarification", bool(questions)))
        if isinstance(questions, list):
            return [str(q) for q in questions], needs
    return [], False


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@router.get("/runs/{run_id}/clarifications", response_model=JsonObjectResponse)
def get_clarifications(
    run_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    run_dir = _find_run_dir(settings.project_root, run_id)
    if run_dir is None:
        raise HTTPException(404, detail={"code": "run_not_found"})

    _check_tenant(run_dir, run_id, request)

    questions, needs = _load_clarifications(run_dir)
    answers_submitted = (run_dir / "clarifications_answers.json").is_file()
    return {
        "questions": questions,
        "needs_clarification": needs,
        "answers_submitted": answers_submitted,
    }


@router.post("/runs/{run_id}/clarifications")
def post_clarifications(
    run_id: str,
    body: ClarificationsAnswerRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    run_dir = _find_run_dir(settings.project_root, run_id)
    if run_dir is None:
        raise HTTPException(404, detail={"code": "run_not_found"})

    _check_tenant(run_dir, run_id, request)

    answers_raw = body.answers
    if not all(isinstance(answer, str) for answer in answers_raw):
        raise HTTPException(
            400,
            detail={
                "code": "invalid_answers",
                "message": "answers must be a list of strings",
            },
        )
    answers = list(answers_raw)
    # Per-answer length cap (4 KiB) — Pydantic doesn't enforce this on
    # list elements, so we check inline.
    for a in answers:
        if len(a) > 4096:
            raise HTTPException(
                400,
                detail={
                    "code": "answer_too_long",
                    "message": "each answer must be at most 4096 characters",
                },
            )

    questions, _ = _load_clarifications(run_dir)
    if len(answers) != len(questions):
        raise HTTPException(
            400,
            detail={
                "code": "answer_count_mismatch",
                "message": f"expected {len(questions)} answers, got {len(answers)}",
                "expected": len(questions),
                "received": len(answers),
            },
        )

    payload = {
        "answers": answers,
        "submitted_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    out_path = run_dir / "clarifications_answers.json"
    with out_path.open("w") as f:
        json.dump(payload, f, indent=2)

    return {"ok": True, "answers_count": len(answers)}
