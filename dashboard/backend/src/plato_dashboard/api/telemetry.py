"""Telemetry replay endpoints — recent run summaries and collector status.

The companion ``telemetry_view`` module owns the GET/PUT preferences
toggle that the Settings panel writes. This module owns the read-only
replay paths that surface the on-disk JSONL to the dashboard:

* ``GET /api/v1/telemetry/recent`` — newest-first list of summaries.
* ``GET /api/v1/telemetry/status``  — opt-in flag + record count, used
  by the Settings panel to show "N records collected" without paging
  the full list.

In multi-tenant mode (``PLATO_DASHBOARD_AUTH_REQUIRED=1``), the response
is filtered so a user only sees rows whose ``user_id`` matches their
``X-Plato-User`` header. Single-user mode returns everything because
the legacy on-disk layout has no tenant boundary to enforce. We also
honour ``project_id`` as a query filter so the dashboard's per-project
view can ask for one project's history.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from plato.state.telemetry import is_enabled as collector_is_enabled
from plato.state.telemetry_collector import TelemetryCollector

from ..auth import auth_required, require_user_id
from ..settings import Settings, get_settings

router = APIRouter(tags=["telemetry"])

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 500


class TelemetryRecentResponse(BaseModel):
    """Newest-first slice of the local telemetry log."""

    items: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    enabled: bool = True


class TelemetryStatusResponse(BaseModel):
    """Lightweight collector state for the Settings panel badge."""

    enabled: bool = True
    record_count: int = 0
    storage_path: str = ""


def _filter_for_tenant(
    items: list[dict[str, Any]],
    *,
    user_id: str,
    project_id: str | None,
) -> list[dict[str, Any]]:
    """Restrict entries to the requester's namespace.

    ``user_id`` is the authoritative filter when auth is enabled — a
    row without ``user_id`` predates multi-tenant mode and is dropped
    rather than leaked to whoever asks. When auth is off we accept
    every row because there's no boundary to enforce. ``project_id``
    is optional and applies in either mode.
    """
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if user_id:
            if item.get("user_id") != user_id:
                continue
        if project_id is not None:
            if item.get("project_id") != project_id:
                continue
        out.append(item)
    return out


def _collector_for(_settings: Settings) -> TelemetryCollector:
    """Resolve a collector. Hook point for tests to inject a tmp path.

    The ``Settings`` parameter is unused today but is wired through so
    a future deployment-config change (e.g. moving the JSONL out of
    ``~/.plato``) doesn't require touching every call site.
    """
    return TelemetryCollector()


@router.get(
    "/telemetry/recent",
    response_model=TelemetryRecentResponse,
    summary="Newest-first slice of the telemetry log",
    responses={
        401: {"description": "Auth required and `X-Plato-User` header is missing."},
    },
)
def get_telemetry_recent(
    request: Request,
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    project_id: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> TelemetryRecentResponse:
    """Return the latest telemetry rows scoped to the caller's tenant + project."""
    user_id = require_user_id(request) if auth_required() else ""
    collector = _collector_for(settings)
    # Read enough headroom that filtering still leaves ``limit`` rows
    # in the common case where most rows belong to the requester.
    raw = collector.read_recent(limit=_MAX_LIMIT)
    filtered = _filter_for_tenant(raw, user_id=user_id, project_id=project_id)
    return TelemetryRecentResponse(
        items=filtered[:limit],
        total=len(filtered),
        enabled=collector_is_enabled(),
    )


@router.get(
    "/telemetry/status",
    response_model=TelemetryStatusResponse,
    summary="Telemetry collector state",
    responses={
        401: {"description": "Auth required and `X-Plato-User` header is missing."},
    },
)
def get_telemetry_status(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> TelemetryStatusResponse:
    """Return the collector's enable flag, record count, and storage path."""
    user_id = require_user_id(request) if auth_required() else ""
    collector = _collector_for(settings)
    raw = collector.read_recent(limit=_MAX_LIMIT)
    filtered = _filter_for_tenant(raw, user_id=user_id, project_id=None)
    return TelemetryStatusResponse(
        enabled=collector_is_enabled(),
        record_count=len(filtered),
        storage_path=str(collector.storage_path),
    )


__all__ = ["router"]
