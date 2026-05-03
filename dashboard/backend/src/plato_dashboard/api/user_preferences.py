"""Per-user dashboard preferences (selected domain, executor, per-stage models).

Persisted at ``<settings.project_root>/users/<user_id>/preferences.json``
so they survive restarts and travel with the project root the rest of the
dashboard uses. When ``PLATO_AUTH=enabled`` (required mode), an
``X-Plato-User`` header is mandatory; otherwise we fall back to a global
``__anon__`` profile so single-user local installs Just Work.

The ``default_executor`` field is the contract surface for Stream 7 — it's
read/persisted here but written as ``None`` until that stream lands.

The ``default_models`` field is a stage-id -> model-id map populated by
the LLM-providers settings page. Empty dict by default; PUT accepts a
partial map and merges into the existing record so the UI can save one
stage at a time without clobbering the rest.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from plato.domain import list_domains

from ..settings import Settings, get_settings

router = APIRouter(tags=["preferences"])

_ANON_USER = "__anon__"
# Conservative slug — matches the alphabet ProjectStore already uses for IDs
# so a malicious header can't traverse outside the per-user directory.
_USER_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
# Stage ids that the dashboard exposes a model picker for. Mirrors
# RECOMMENDED_BY_STAGE on the frontend; kept in sync manually since the
# canonical list lives in plato/llm.py and we don't want to import it
# into the API layer just for a validation set.
_VALID_STAGE_IDS = frozenset(
    {"idea", "literature", "method", "results", "paper", "referee"}
)


class PreferencesResponse(BaseModel):
    default_domain: str | None = None
    default_executor: str | None = None
    default_models: dict[str, str] = Field(default_factory=dict)


class PreferencesUpdate(BaseModel):
    default_domain: str | None = Field(default=None, min_length=1)
    # Partial map: only the stages present are updated; keys not in
    # _VALID_STAGE_IDS are rejected at validation time.
    default_models: dict[str, str] | None = None


def _resolve_user_id(
    settings: Settings,
    x_plato_user: str | None,
) -> str:
    """Pick a user identifier and reject malformed / missing values.

    In required-mode (``PLATO_AUTH=enabled``) the header MUST be present
    and well-formed; otherwise we return the shared anon profile.
    """
    if settings.is_auth_required:
        if not x_plato_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "user_required",
                    "message": "X-Plato-User header is required when auth is enabled.",
                },
            )
        if not _USER_ID_RE.match(x_plato_user):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "user_invalid",
                    "message": "X-Plato-User must be 1-64 chars [A-Za-z0-9_.-].",
                },
            )
        return x_plato_user
    if x_plato_user and _USER_ID_RE.match(x_plato_user):
        return x_plato_user
    return _ANON_USER


def _prefs_path(settings: Settings, user_id: str) -> Path:
    return settings.project_root / "users" / user_id / "preferences.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # Treat a corrupt file as "no preferences yet" — the next write
        # will overwrite cleanly. Better than 500-ing on the read path.
        return {}


def _save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _coerce_default_models(raw: Any) -> dict[str, str]:
    """Defensive read for the on-disk ``default_models`` field.

    Older preference files predate this field and won't carry it; a
    malformed value (non-dict, non-string members) shouldn't crash GET.
    """
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        if isinstance(k, str) and isinstance(v, str) and k in _VALID_STAGE_IDS:
            out[k] = v
    return out


@router.get(
    "/user/preferences",
    response_model=PreferencesResponse,
    summary="Read per-user dashboard preferences",
    responses={
        401: {"description": "Auth required and `X-Plato-User` header is missing or invalid."},
    },
)
def get_preferences(
    settings: Settings = Depends(get_settings),
    x_plato_user: str | None = Header(default=None, alias="X-Plato-User"),
) -> PreferencesResponse:
    """Return default domain, executor, and per-stage model picks."""
    user_id = _resolve_user_id(settings, x_plato_user)
    data = _load(_prefs_path(settings, user_id))
    return PreferencesResponse(
        default_domain=data.get("default_domain"),
        default_executor=data.get("default_executor"),
        default_models=_coerce_default_models(data.get("default_models")),
    )


@router.put(
    "/user/preferences",
    response_model=PreferencesResponse,
    summary="Update per-user dashboard preferences",
    responses={
        400: {"description": "Empty update, unknown domain, or unknown stage id."},
        401: {"description": "Auth required and `X-Plato-User` header is missing or invalid."},
    },
)
def put_preferences(
    body: PreferencesUpdate,
    settings: Settings = Depends(get_settings),
    x_plato_user: str | None = Header(default=None, alias="X-Plato-User"),
) -> PreferencesResponse:
    """Patch the user's preferences (`default_domain` and/or `default_models`)."""
    user_id = _resolve_user_id(settings, x_plato_user)

    if body.default_domain is None and body.default_models is None:
        # No-op PUTs would silently succeed — better to fail loudly so
        # callers don't think they wrote something they didn't.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "empty_update",
                "message": "Provide default_domain or default_models.",
            },
        )

    if body.default_domain is not None:
        registered = list_domains()
        if body.default_domain not in registered:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "unknown_domain",
                    "message": (
                        f"Unknown domain {body.default_domain!r}. "
                        f"Registered: {registered}"
                    ),
                },
            )

    if body.default_models is not None:
        bad = [k for k in body.default_models if k not in _VALID_STAGE_IDS]
        if bad:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "unknown_stage",
                    "message": (
                        f"Unknown stage ids: {bad!r}. "
                        f"Expected subset of {sorted(_VALID_STAGE_IDS)}."
                    ),
                },
            )

    path = _prefs_path(settings, user_id)
    data = _load(path)
    if body.default_domain is not None:
        data["default_domain"] = body.default_domain
    # Stream 7 owns this field — preserve any value already on disk, otherwise
    # surface ``None`` rather than fabricating an executor here.
    data.setdefault("default_executor", None)
    if body.default_models is not None:
        existing = _coerce_default_models(data.get("default_models"))
        existing.update(body.default_models)
        data["default_models"] = existing
    _save(path, data)

    return PreferencesResponse(
        default_domain=data.get("default_domain"),
        default_executor=data.get("default_executor"),
        default_models=_coerce_default_models(data.get("default_models")),
    )
