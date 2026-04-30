"""Per-user dashboard preferences (selected domain, executor) backed by JSON files.

Persisted at ``<settings.project_root>/users/<user_id>/preferences.json``
so they survive restarts and travel with the project root the rest of the
dashboard uses. When ``PLATO_AUTH=enabled`` (required mode), an
``X-Plato-User`` header is mandatory; otherwise we fall back to a global
``__anon__`` profile so single-user local installs Just Work.

The ``default_executor`` field is the contract surface for Stream 7 — it's
read/persisted here but written as ``None`` until that stream lands.
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

router = APIRouter()

_ANON_USER = "__anon__"
# Conservative slug — matches the alphabet ProjectStore already uses for IDs
# so a malicious header can't traverse outside the per-user directory.
_USER_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class PreferencesResponse(BaseModel):
    default_domain: str | None = None
    default_executor: str | None = None


class PreferencesUpdate(BaseModel):
    default_domain: str = Field(min_length=1)


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


@router.get("/api/v1/user/preferences", response_model=PreferencesResponse)
def get_preferences(
    settings: Settings = Depends(get_settings),
    x_plato_user: str | None = Header(default=None, alias="X-Plato-User"),
) -> PreferencesResponse:
    user_id = _resolve_user_id(settings, x_plato_user)
    data = _load(_prefs_path(settings, user_id))
    return PreferencesResponse(
        default_domain=data.get("default_domain"),
        default_executor=data.get("default_executor"),
    )


@router.put("/api/v1/user/preferences", response_model=PreferencesResponse)
def put_preferences(
    body: PreferencesUpdate,
    settings: Settings = Depends(get_settings),
    x_plato_user: str | None = Header(default=None, alias="X-Plato-User"),
) -> PreferencesResponse:
    user_id = _resolve_user_id(settings, x_plato_user)

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

    path = _prefs_path(settings, user_id)
    data = _load(path)
    data["default_domain"] = body.default_domain
    # Stream 7 owns this field — preserve any value already on disk, otherwise
    # surface ``None`` rather than fabricating an executor here.
    data.setdefault("default_executor", None)
    _save(path, data)

    return PreferencesResponse(
        default_domain=data["default_domain"],
        default_executor=data.get("default_executor"),
    )
