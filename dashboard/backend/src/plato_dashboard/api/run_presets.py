"""Per-user run-config presets.

A preset bundles the knobs that govern a paper-writing run — idea
iterations, max revision iters, journal, domain, executor, etc — under
a user-chosen name so the operator can pick "literature review (lite)"
or "full astro pipeline" instead of re-typing every field on the start
form.

Storage layout mirrors ``executor_preferences.py`` and
``user_preferences.py``: ``<project_root>/users/<user_id>/run_presets.json``
when authed, ``<project_root>/run_presets.json`` for legacy single-user
installs. The on-disk shape is ``{"presets": [RunPreset, ...]}`` so the
file is readable as one JSON document and we don't have to walk a
directory of preset-per-file blobs.

The ``config`` payload is intentionally a free-form ``dict`` — it lines
up with the ``StageRunRequest``-like body the start endpoint accepts,
and validating every key here would mean re-encoding plato's run-config
schema in two places. Callers (the run-start UI) merge this dict over
their own defaults at submit time.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..auth import auth_required, extract_user_id
from ..settings import Settings, get_settings

router = APIRouter()

_PRESETS_FILENAME = "run_presets.json"
# Preset names show up in dropdowns and in the on-disk JSON, so keep
# them human-readable but constrained enough that they survive a JSON
# round-trip and don't smuggle control characters into logs.
_NAME_RE = re.compile(r"^[A-Za-z0-9 _.\-()]{1,64}$")


class RunPreset(BaseModel):
    id: str
    name: str
    created_at: str
    config: dict[str, Any] = Field(default_factory=dict)


class RunPresetCreate(BaseModel):
    name: str
    config: dict[str, Any] = Field(default_factory=dict)


class RunPresetUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None


def _resolve_user_id(request: Request) -> str | None:
    """Return the requester's user id, raising 401 in required-mode."""
    user_id = extract_user_id(request)
    if user_id is None and auth_required():
        raise HTTPException(
            status_code=401,
            detail={
                "code": "auth_required",
                "message": "Missing required header 'X-Plato-User'.",
            },
        )
    return user_id


def _presets_path(settings: Settings, user_id: str | None) -> Path:
    """Resolve the presets file location for ``user_id`` (or legacy)."""
    if user_id is None:
        return settings.project_root / _PRESETS_FILENAME
    return settings.project_root / "users" / user_id / _PRESETS_FILENAME


def _load_presets(path: Path) -> list[RunPreset]:
    """Read the on-disk preset list. Treats a missing or corrupt file as empty."""
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    raw = payload.get("presets")
    if not isinstance(raw, list):
        return []
    out: list[RunPreset] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            out.append(RunPreset(**item))
        except (TypeError, ValueError):
            # Skip malformed entries rather than 500 on the listing
            # endpoint — the operator can re-create anything that got
            # corrupted via the UI.
            continue
    return out


def _save_presets(path: Path, presets: list[RunPreset]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"presets": [p.model_dump() for p in presets]}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _validate_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned or not _NAME_RE.match(cleaned):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_name",
                "message": (
                    "Preset name must be 1-64 chars and match "
                    "[A-Za-z0-9 _.\\-()]."
                ),
            },
        )
    return cleaned


def _ensure_unique_name(presets: list[RunPreset], name: str, *, exclude_id: str | None = None) -> None:
    lower = name.lower()
    for p in presets:
        if exclude_id is not None and p.id == exclude_id:
            continue
        if p.name.lower() == lower:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "duplicate_name",
                    "message": f"A preset named {name!r} already exists.",
                },
            )


@router.get("/run-presets", response_model=list[RunPreset])
def list_run_presets(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> list[RunPreset]:
    user_id = _resolve_user_id(request)
    return _load_presets(_presets_path(settings, user_id))


@router.get("/run-presets/{preset_id}", response_model=RunPreset)
def get_run_preset(
    preset_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RunPreset:
    user_id = _resolve_user_id(request)
    presets = _load_presets(_presets_path(settings, user_id))
    target = next((p for p in presets if p.id == preset_id), None)
    if target is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "preset_not_found", "message": "Unknown preset id."},
        )
    return target


@router.post("/run-presets", response_model=RunPreset, status_code=201)
def create_run_preset(
    body: RunPresetCreate,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RunPreset:
    user_id = _resolve_user_id(request)
    name = _validate_name(body.name)
    path = _presets_path(settings, user_id)
    presets = _load_presets(path)
    _ensure_unique_name(presets, name)

    preset = RunPreset(
        id=uuid.uuid4().hex,
        name=name,
        created_at=datetime.now(timezone.utc).isoformat(),
        config=body.config or {},
    )
    presets.append(preset)
    _save_presets(path, presets)
    return preset


@router.put("/run-presets/{preset_id}", response_model=RunPreset)
def update_run_preset(
    preset_id: str,
    body: RunPresetUpdate,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RunPreset:
    user_id = _resolve_user_id(request)
    path = _presets_path(settings, user_id)
    presets = _load_presets(path)
    target_idx = next((i for i, p in enumerate(presets) if p.id == preset_id), None)
    if target_idx is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "preset_not_found", "message": "Unknown preset id."},
        )
    if body.name is None and body.config is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "empty_update",
                "message": "Provide name or config.",
            },
        )

    current = presets[target_idx]
    new_name = current.name
    if body.name is not None:
        new_name = _validate_name(body.name)
        _ensure_unique_name(presets, new_name, exclude_id=preset_id)

    new_config = current.config if body.config is None else body.config
    updated = RunPreset(
        id=current.id,
        name=new_name,
        created_at=current.created_at,
        config=new_config,
    )
    presets[target_idx] = updated
    _save_presets(path, presets)
    return updated


@router.delete("/run-presets/{preset_id}", status_code=204)
def delete_run_preset(
    preset_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    user_id = _resolve_user_id(request)
    path = _presets_path(settings, user_id)
    presets = _load_presets(path)
    remaining = [p for p in presets if p.id != preset_id]
    if len(remaining) == len(presets):
        raise HTTPException(
            status_code=404,
            detail={"code": "preset_not_found", "message": "Unknown preset id."},
        )
    _save_presets(path, remaining)


__all__ = [
    "router",
    "RunPreset",
    "RunPresetCreate",
    "RunPresetUpdate",
]
