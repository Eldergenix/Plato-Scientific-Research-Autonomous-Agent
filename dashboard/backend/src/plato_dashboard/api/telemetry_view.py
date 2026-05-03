"""Telemetry preferences and last-N summary for the Settings panel.

The toggle persists alongside the rest of ``user_preferences.json`` so a
user's opt-in/out follows them across the dashboard's tenant boundaries.
The summary is read from the on-disk ``telemetry.jsonl`` produced by
``plato.state.telemetry`` — this view never writes to that file, only
reads it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from plato.state.telemetry import read_recent

from ..settings import Settings, get_settings
from .user_preferences import _resolve_user_id

router = APIRouter(tags=["telemetry"])


class TelemetrySummary(BaseModel):
    """Aggregate over the last N summaries returned to the dashboard."""

    total_runs: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost_usd: float = 0.0


class TelemetryPreferencesResponse(BaseModel):
    telemetry_enabled: bool = True
    last_n_summary: list[dict[str, Any]] = Field(default_factory=list)
    aggregates: TelemetrySummary = Field(default_factory=TelemetrySummary)


class TelemetryPreferencesUpdate(BaseModel):
    telemetry_enabled: bool


def _prefs_path(settings: Settings, user_id: str) -> Path:
    return settings.project_root / "users" / user_id / "preferences.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _aggregate(entries: list[dict[str, Any]]) -> TelemetrySummary:
    total_in = 0
    total_out = 0
    total_cost = 0.0
    for e in entries:
        ti = e.get("tokens_in") or 0
        to = e.get("tokens_out") or 0
        cu = e.get("cost_usd") or 0.0
        if isinstance(ti, (int, float)):
            total_in += int(ti)
        if isinstance(to, (int, float)):
            total_out += int(to)
        if isinstance(cu, (int, float)):
            total_cost += float(cu)
    return TelemetrySummary(
        total_runs=len(entries),
        total_tokens_in=total_in,
        total_tokens_out=total_out,
        total_cost_usd=round(total_cost, 6),
    )


@router.get(
    "/telemetry/preferences",
    response_model=TelemetryPreferencesResponse,
    summary="Read telemetry opt-in + last-N summary",
    responses={
        401: {"description": "Auth required and `X-Plato-User` header is missing/invalid."},
    },
)
def get_telemetry_preferences(
    settings: Settings = Depends(get_settings),
    x_plato_user: str | None = Header(default=None, alias="X-Plato-User"),
) -> TelemetryPreferencesResponse:
    """Return the user's telemetry preference and the last 30 run summaries."""
    user_id = _resolve_user_id(settings, x_plato_user)
    data = _load(_prefs_path(settings, user_id))
    enabled = bool(data.get("telemetry_enabled", True))
    last = read_recent(n=30)
    return TelemetryPreferencesResponse(
        telemetry_enabled=enabled,
        last_n_summary=last,
        aggregates=_aggregate(last),
    )


@router.put(
    "/telemetry/preferences",
    response_model=TelemetryPreferencesResponse,
    summary="Update telemetry opt-in flag",
    responses={
        400: {"description": "`telemetry_enabled` is not a boolean."},
        401: {"description": "Auth required and `X-Plato-User` header is missing/invalid."},
    },
)
def put_telemetry_preferences(
    body: TelemetryPreferencesUpdate,
    settings: Settings = Depends(get_settings),
    x_plato_user: str | None = Header(default=None, alias="X-Plato-User"),
) -> TelemetryPreferencesResponse:
    """Persist the user's telemetry opt-in/out and return the refreshed payload."""
    if not isinstance(body.telemetry_enabled, bool):  # pydantic guards but be explicit
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_payload", "message": "telemetry_enabled must be bool."},
        )
    user_id = _resolve_user_id(settings, x_plato_user)
    path = _prefs_path(settings, user_id)
    data = _load(path)
    data["telemetry_enabled"] = bool(body.telemetry_enabled)
    _save(path, data)
    last = read_recent(n=30)
    return TelemetryPreferencesResponse(
        telemetry_enabled=data["telemetry_enabled"],
        last_n_summary=last,
        aggregates=_aggregate(last),
    )
