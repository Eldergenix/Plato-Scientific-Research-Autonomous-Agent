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

When ``api/manifests.py`` lands (Stream 1 / F1), the helpers below can
be moved there and re-exported. Keeping them local for now means this
module ships independently.
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


class ClarificationsAnswerRequest(BaseModel):
    """Body for ``POST /runs/{run_id}/clarifications``.

    The 50-answer cap blocks pathological payloads; per-answer length
    is capped at 4 KiB so a runaway client can't fill the project_dir
    with megabytes of free-form text before any LLM call has happened.

    We accept ``list[Any]`` rather than ``list[str]`` so a non-string
    element returns the handler's 400 ``invalid_answers`` instead of a
    Pydantic 422. The element-type check happens inline in the handler.
    """

    answers: list[Any] = Field(max_length=50)


router = APIRouter(tags=["clarifications"])

_RUN_NOT_FOUND: dict[int | str, dict] = {
    404: {"description": "No project owns the given run id."},
}


# --------------------------------------------------------------------------- #
# Helpers (mirror the planned manifests.py shape so they can be relocated.)
# --------------------------------------------------------------------------- #
def _read_json(path: Path) -> dict[str, Any] | None:
    """Read JSON from ``path`` or return ``None`` if missing/unreadable."""
    if not path.is_file():
        return None
    try:
        with path.open() as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _user_id(request: Request) -> str:
    """Best-effort caller id for tenant scoping.

    Auth is currently disabled (single-tenant local mode). When auth
    flips on, the middleware sets ``request.state.user_id``; if not, we
    fall back to the ``X-User-Id`` header (used by tests) and finally
    to a stable ``"local"`` sentinel.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return str(user_id)
    header = request.headers.get("x-user-id")
    if header:
        return header
    return "local"


def _find_run_dir(run_id: str, settings: Settings) -> Path | None:
    """Locate ``<project_root>/<pid>/runs/<run_id>/``.

    The dashboard's filesystem layout puts every run under the project
    that owns it. We don't carry the project id on the URL, so we walk
    the project root looking for a matching ``runs/<run_id>`` dir.

    Returns ``None`` if no project owns ``run_id``.
    """
    root = settings.project_root
    if not root.exists():
        return None
    for project in root.iterdir():
        if not project.is_dir():
            continue
        candidate = project / "runs" / run_id
        if candidate.is_dir():
            return candidate
    return None


def _check_tenant(run_dir: Path, request: Request) -> None:
    """Raise 403 when the run was created by a different tenant.

    A run carries its owner in ``meta.json#owner`` (when auth is
    enabled). Local mode has no owner and this check is a no-op.
    """
    meta = _read_json(run_dir / "meta.json") or {}
    owner = meta.get("owner")
    if not owner:
        return
    caller = _user_id(request)
    if owner != caller:
        raise HTTPException(403, detail={"code": "cross_tenant_forbidden"})


def _load_clarifications(run_dir: Path) -> tuple[list[str], bool]:
    """Resolve (questions, needs_clarification) from disk.

    Tries ``clarifications.json`` first, then ``manifest.json``'s
    ``extra`` block. Empty / unreadable files yield ``([], False)``.
    """
    explicit = _read_json(run_dir / "clarifications.json")
    if explicit is not None:
        questions = explicit.get("questions") or []
        needs = bool(explicit.get("needs_clarification", bool(questions)))
        if isinstance(questions, list):
            return [str(q) for q in questions], needs
        return [], needs

    manifest = _read_json(run_dir / "manifest.json")
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
@router.get(
    "/runs/{run_id}/clarifications",
    response_model=JsonObjectResponse,
    summary="Read clarifying questions for a run",
    responses={
        **_RUN_NOT_FOUND,
        403: {"description": "Run belongs to a different tenant."},
    },
)
def get_clarifications(
    run_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return the clarifier's questions and whether the run is waiting on answers."""
    run_dir = _find_run_dir(run_id, settings)
    if run_dir is None:
        raise HTTPException(404, detail={"code": "run_not_found"})

    _check_tenant(run_dir, request)

    questions, needs = _load_clarifications(run_dir)
    answers_submitted = (run_dir / "clarifications_answers.json").is_file()
    return {
        "questions": questions,
        "needs_clarification": needs,
        "answers_submitted": answers_submitted,
    }


@router.post(
    "/runs/{run_id}/clarifications",
    summary="Submit clarifier answers",
    responses={
        **_RUN_NOT_FOUND,
        400: {"description": "Answer count mismatch, non-string answer, or answer over 4 KiB."},
        403: {"description": "Run belongs to a different tenant."},
    },
)
def post_clarifications(
    run_id: str,
    body: ClarificationsAnswerRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Persist user answers to the clarifier's questions so the run can resume."""
    run_dir = _find_run_dir(run_id, settings)
    if run_dir is None:
        raise HTTPException(404, detail={"code": "run_not_found"})

    _check_tenant(run_dir, request)

    answers = body.answers
    # Element-type and per-answer length checks happen inline so we can
    # return a domain-specific 400 instead of Pydantic's 422.
    for a in answers:
        if not isinstance(a, str):
            raise HTTPException(
                400,
                detail={
                    "code": "invalid_answers",
                    "message": "each answer must be a string",
                },
            )
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
