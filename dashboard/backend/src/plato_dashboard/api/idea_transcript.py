"""Iter-6 — read the structured idea-debate transcript for a project.

Plato's ``langgraph_agents.idea`` nodes (``idea_maker`` / ``idea_hater``)
each append a JSON line to ``<project>/idea_generation_output/idea_transcript.jsonl``
after every turn, capturing ``{agent, text, ts, iteration}``. This
router reads that file and returns the turns to the dashboard's
IdeaStage TranscriptPane.

Why a sidecar (and not ``idea.log``): the streaming log is concatenated
LLM tokens with no separator — fine for tailing but useless for rendering
turn-by-turn cards. The JSONL keeps a structured boundary per turn so the
frontend can show maker/hater debate cards side-by-side without reparsing
the streaming text.

Tenant scoping mirrors ``idea_history``: per-user namespace first, legacy
flat layout as fallback. Missing/torn lines are skipped silently — the
frontend renders an empty state when zero turns come back.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..settings import Settings, get_settings


router = APIRouter()


class IdeaTranscriptTurn(BaseModel):
    agent: str
    text: str
    ts: str | None = None
    iteration: int | None = None


class IdeaTranscriptResponse(BaseModel):
    turns: list[IdeaTranscriptTurn] = Field(default_factory=list)


def _user_id(req: Request) -> str | None:
    from ..auth import extract_user_id

    return extract_user_id(req)


def _project_dir_for(
    project_root: Path, pid: str, user_id: str | None
) -> Path | None:
    """Resolve the on-disk project directory for ``pid`` honouring tenancy.

    Mirrors :func:`idea_history._project_dir_for`. Returns ``None`` when
    no candidate directory exists.
    """
    if user_id:
        scoped = project_root / "users" / user_id / pid
        if scoped.is_dir():
            return scoped
    direct = project_root / pid
    if direct.is_dir():
        return direct
    return None


def _coerce_turn(raw: Any) -> IdeaTranscriptTurn | None:
    """Defensive coercion. Returns ``None`` for any malformed line.

    The pipeline writes well-formed records, but a partial flush during
    a sigterm could leave a truncated tail line. We tolerate that — the
    next run will append over it; readers just skip the bad line.
    """
    if not isinstance(raw, dict):
        return None
    agent = raw.get("agent")
    text = raw.get("text")
    if not isinstance(agent, str) or not isinstance(text, str):
        return None
    if agent not in {"idea_maker", "idea_hater"}:
        return None
    ts = raw.get("ts") if isinstance(raw.get("ts"), str) else None
    iteration_raw = raw.get("iteration")
    try:
        iteration = (
            int(iteration_raw) if iteration_raw is not None else None
        )
    except (TypeError, ValueError):
        iteration = None
    return IdeaTranscriptTurn(
        agent=agent, text=text, ts=ts, iteration=iteration
    )


@router.get(
    "/projects/{pid}/idea_transcript",
    response_model=IdeaTranscriptResponse,
)
def get_idea_transcript(
    pid: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> IdeaTranscriptResponse:
    """Return the structured maker/hater debate transcript for ``pid``."""
    requester = _user_id(request)
    project_dir = _project_dir_for(settings.project_root, pid, requester)
    if project_dir is None:
        return IdeaTranscriptResponse(turns=[])

    log_path = project_dir / "idea_generation_output" / "idea_transcript.jsonl"
    if not log_path.is_file():
        return IdeaTranscriptResponse(turns=[])

    turns: list[IdeaTranscriptTurn] = []
    try:
        for raw_line in log_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            turn = _coerce_turn(obj)
            if turn is not None:
                turns.append(turn)
    except OSError:
        return IdeaTranscriptResponse(turns=[])

    return IdeaTranscriptResponse(turns=turns)


__all__ = ["router", "IdeaTranscriptTurn", "IdeaTranscriptResponse"]
