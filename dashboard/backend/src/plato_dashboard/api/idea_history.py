"""Iter-23 — historical idea-run listing endpoint.

The IdeaSidePanel "Run history" view used to ship hardcoded mock entries
("12m ago / gpt-5 / 11m 04s" — see iter-22 cleanup). The real data is
already on disk: every ``Plato.get_idea_*`` invocation writes a
``RunManifest`` to ``<project_dir>/runs/<run_id>/manifest.json`` (see
:mod:`plato.state.manifest`). This router walks that directory tree
filtered to idea workflows and returns a flat list the frontend can
render directly.

Response shape per entry::

    {
      "run_id": "abc123def456",
      "workflow": "get_idea_fast",
      "started_at": "2026-04-29T10:00:00+00:00",
      "ended_at": "2026-04-29T10:11:30+00:00",
      "status": "success",
      "models": {"idea_maker": "gpt-5", "idea_hater": "o3-mini"},
      "cost_usd": 0.42,
      "tokens_in": 18521,
      "tokens_out": 4102,
      "duration_seconds": 690.0
    }

Sorted descending by ``started_at`` so the freshest run is first.

Tenant scoping mirrors the manifest router: cross-tenant reads are 403
when ``PLATO_DASHBOARD_AUTH_REQUIRED=1`` is set, transparent otherwise.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..settings import Settings, get_settings


router = APIRouter()


class IdeaRunHistoryEntry(BaseModel):
    """One row in the idea-run history list."""

    run_id: str
    workflow: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    status: str = "unknown"
    models: dict[str, str] = Field(default_factory=dict)
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    duration_seconds: float | None = None


class IdeaHistoryResponse(BaseModel):
    entries: list[IdeaRunHistoryEntry] = Field(default_factory=list)


def _user_id(req: Request) -> str | None:
    """Mirror manifests.py — single source for the auth header read."""
    from ..auth import extract_user_id

    return extract_user_id(req)


def _project_dir_for(
    project_root: Path, pid: str, user_id: str | None
) -> Path | None:
    """Resolve the on-disk project directory for ``pid`` honouring tenancy.

    Search order matches ``ProjectStore``'s effective layout under
    multi-tenant deploys:

    1. ``<project_root>/users/<user_id>/<pid>/`` (per-user namespace).
    2. ``<project_root>/<pid>/`` (legacy single-tenant flat layout) —
       only when no user header is supplied or the per-user candidate
       doesn't exist; the manifest's own ``user_id`` field still gates
       per-run visibility.
    """
    if user_id:
        scoped = project_root / "users" / user_id / pid
        if scoped.is_dir():
            return scoped
    direct = project_root / pid
    if direct.is_dir():
        return direct
    return None


def _is_idea_workflow(workflow: str) -> bool:
    """True when the manifest belongs to an idea-generation workflow.

    Plato writes manifests with ``workflow`` set to ``get_idea_fast`` /
    ``get_idea_cmagent`` / etc. Anything starting with ``"get_idea"``
    (case-insensitive) belongs in this view.
    """
    return workflow.lower().startswith("get_idea")


def _safe_iso_to_dt(value: Any) -> datetime | None:
    """Tolerant ISO-8601 parser. Returns None on any failure."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _entry_from_manifest(
    run_id: str, manifest: dict[str, Any]
) -> IdeaRunHistoryEntry | None:
    """Coerce a raw manifest dict into the response shape.

    Returns ``None`` when the manifest doesn't look like an idea run.
    Defensive across schema drift — every field is optional on the
    manifest side and falls back to a safe default here.
    """
    workflow = str(manifest.get("workflow") or "")
    if not workflow or not _is_idea_workflow(workflow):
        return None

    started = _safe_iso_to_dt(manifest.get("started_at"))
    ended = _safe_iso_to_dt(manifest.get("ended_at"))
    duration: float | None = None
    if started is not None and ended is not None:
        duration = max(0.0, (ended - started).total_seconds())

    raw_models = manifest.get("models") or {}
    if isinstance(raw_models, dict):
        models = {str(k): str(v) for k, v in raw_models.items() if v is not None}
    else:
        models = {}

    def _coerce_int(name: str) -> int:
        v = manifest.get(name)
        try:
            return int(v) if v is not None else 0
        except (TypeError, ValueError):
            return 0

    def _coerce_float(name: str) -> float:
        v = manifest.get(name)
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    return IdeaRunHistoryEntry(
        run_id=run_id,
        workflow=workflow,
        started_at=started,
        ended_at=ended,
        status=str(manifest.get("status") or "unknown"),
        models=models,
        cost_usd=_coerce_float("cost_usd"),
        tokens_in=_coerce_int("tokens_in"),
        tokens_out=_coerce_int("tokens_out"),
        duration_seconds=duration,
    )


def _enforce_tenant(manifest: dict[str, Any], requester: str | None) -> bool:
    """True iff this manifest is visible to ``requester``.

    Mirrors :func:`manifests._enforce_tenant` semantics but doesn't raise —
    we just skip non-visible runs when listing, so a multi-tenant project
    directory doesn't leak the existence of other tenants' runs.
    """
    from ..auth import auth_required as _auth_required

    required = _auth_required()
    owner = manifest.get("user_id")

    if requester is None and not required:
        return True
    if not isinstance(owner, str):
        # Pre-multi-tenant runs visible only when auth isn't required.
        return not required
    if requester is None:
        return False
    return owner == requester


@router.get(
    "/projects/{pid}/idea_history",
    response_model=IdeaHistoryResponse,
)
def list_idea_history(
    pid: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> IdeaHistoryResponse:
    """Return past idea-generation runs for ``pid``, newest first."""
    requester = _user_id(request)
    project_dir = _project_dir_for(settings.project_root, pid, requester)
    if project_dir is None:
        # Treat missing project as "no history" rather than 404 — the
        # frontend renders the empty state regardless and a 404 here
        # would force every dashboard to special-case it.
        return IdeaHistoryResponse(entries=[])

    runs_dir = project_dir / "runs"
    if not runs_dir.is_dir():
        return IdeaHistoryResponse(entries=[])
    entries: list[IdeaRunHistoryEntry] = []

    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except (json.JSONDecodeError, OSError):
            # Skip corrupt manifests rather than 500 the whole list.
            continue
        if not isinstance(manifest, dict):
            continue
        if not _enforce_tenant(manifest, requester):
            continue
        entry = _entry_from_manifest(run_dir.name, manifest)
        if entry is not None:
            entries.append(entry)

    # Sort by started_at desc; runs missing started_at sink to the bottom.
    entries.sort(
        key=lambda e: (e.started_at or datetime.min),
        reverse=True,
    )

    return IdeaHistoryResponse(entries=entries)


__all__ = ["router", "IdeaRunHistoryEntry", "IdeaHistoryResponse"]
