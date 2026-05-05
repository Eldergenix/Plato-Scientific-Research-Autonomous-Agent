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
    """

    answers: list[str] = Field(max_length=50)


router = APIRouter()


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


def _user_id(request: Request) -> str | None:
    """Caller id via the canonical ``auth.extract_user_id`` helper.

    Iter-4: previously this fell through to a "local" sentinel and to a
    non-canonical "X-User-Id" header. That made the check bypassable
    (no header → anyone can pose as "local" → unconditional access). We
    now use the same allowlist-validated extractor every other router
    uses, so the tenant chain is consistent.
    """
    from ..auth import extract_user_id

    return extract_user_id(request)


def _find_run_dir(run_id: str, settings: Settings, user_id: str | None) -> Path | None:
    """Locate ``<project_root>/<users/<uid>>/<pid>/runs/<run_id>/``.

    Iter-4: previously walked the legacy flat ``project_root.iterdir()``
    layout, which (a) misses the per-user namespace deploys actually
    use and (b) lets a search resolve another tenant's run before the
    tenant check fires. Scoping the search to the caller's user root
    fixes both.
    """
    root = settings.project_root
    if user_id:
        # Tenant-aware deploy: per-user roots live under <root>/users/<uid>/.
        root = root / "users" / user_id
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

    Iter-4: prior implementation read ``meta.json#owner`` — a field
    that *no producer ever writes* in the codebase. Runs persist
    ownership in ``manifest.json#user_id`` (server.py:_load_run_manifest_user).
    We now read that file and compare against the canonical caller id.
    """
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        # No manifest yet — treat as legacy / un-bound, no tenant data
        # to compare against. Defer to outer auth gate.
        return
    try:
        with manifest_path.open() as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    owner = manifest.get("user_id") if isinstance(manifest, dict) else None
    caller = _user_id(request)
    if owner and caller and owner != caller:
        # 404 not 403 to avoid existence-leak (matches manifests.py).
        raise HTTPException(
            404, detail={"code": "run_not_found", "run_id": run_dir.name}
        )


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
@router.get("/runs/{run_id}/clarifications", response_model=JsonObjectResponse)
def get_clarifications(
    run_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    run_dir = _find_run_dir(run_id, settings, _user_id(request))
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


@router.post("/runs/{run_id}/clarifications")
def post_clarifications(
    run_id: str,
    body: ClarificationsAnswerRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    run_dir = _find_run_dir(run_id, settings, _user_id(request))
    if run_dir is None:
        raise HTTPException(404, detail={"code": "run_not_found"})

    _check_tenant(run_dir, request)

    answers = body.answers
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
