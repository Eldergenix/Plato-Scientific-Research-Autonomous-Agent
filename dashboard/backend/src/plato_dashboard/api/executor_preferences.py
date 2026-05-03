"""Per-user default-executor preference.

Single field — ``default_executor`` — persisted at
``<project_root>/users/<user_id>/executor_prefs.json``. We deliberately
keep this in its own file (not the broader ``user_preferences.json``
Stream 6 owns) so the two streams can land independently and the
integration commit can fold them together later.

In legacy single-user mode (``X-Plato-User`` absent and auth not
required) the file lives at ``<project_root>/executor_prefs.json``.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth import auth_required, extract_user_id
from ..settings import Settings, get_settings

router = APIRouter(tags=["preferences"])

_PREFS_FILENAME = "executor_prefs.json"

_AUTH_REQUIRED_RESPONSE: dict[int | str, dict] = {
    401: {"description": "Auth required and `X-Plato-User` header is missing."},
}


class ExecutorPreference(BaseModel):
    default_executor: str | None = None


class ExecutorPreferenceUpdate(BaseModel):
    default_executor: str


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


def _prefs_path(settings: Settings, user_id: str | None) -> Path:
    """Resolve the prefs file location for ``user_id`` (or legacy).

    Co-locates with ``user_preferences.py``: both nest under
    ``<project_root>/users/<user_id>/`` so a future merge can fold
    them into a single file. (The previous ``project_root.parent``
    path put executor prefs one directory above domain prefs and
    blocked any such merge.)
    """
    if user_id is None:
        return settings.project_root / _PREFS_FILENAME
    return settings.project_root / "users" / user_id / _PREFS_FILENAME


def _read_prefs(path: Path) -> ExecutorPreference:
    if not path.is_file():
        return ExecutorPreference(default_executor=None)
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        # Treat a corrupt prefs file as "unset" rather than 500ing the
        # settings page — the user can re-pick a default and we'll
        # rewrite the file from scratch.
        return ExecutorPreference(default_executor=None)
    if not isinstance(payload, dict):
        return ExecutorPreference(default_executor=None)
    raw = payload.get("default_executor")
    return ExecutorPreference(
        default_executor=raw if isinstance(raw, str) and raw else None
    )


def _write_prefs(path: Path, prefs: ExecutorPreference) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prefs.model_dump(), indent=2))


@router.get(
    "/user/executor_preferences",
    response_model=ExecutorPreference,
    summary="Read default-executor preference",
    responses=_AUTH_REQUIRED_RESPONSE,
)
def get_executor_preference(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> ExecutorPreference:
    """Resolve the default executor for the calling user (or anon)."""
    user_id = _resolve_user_id(request)
    return _read_prefs(_prefs_path(settings, user_id))


@router.put(
    "/user/executor_preferences",
    response_model=ExecutorPreference,
    summary="Set default executor",
    responses={
        **_AUTH_REQUIRED_RESPONSE,
        400: {"description": "`default_executor` is not one of the registered backends."},
    },
)
def set_executor_preference(
    body: ExecutorPreferenceUpdate,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> ExecutorPreference:
    """Validate against the registered executor names, then persist."""
    from plato.executor import list_executors

    user_id = _resolve_user_id(request)
    registered = set(list_executors())
    if body.default_executor not in registered:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "unknown_executor",
                "message": (
                    f"Unknown executor {body.default_executor!r}. "
                    f"Expected one of: {sorted(registered)}"
                ),
            },
        )
    prefs = ExecutorPreference(default_executor=body.default_executor)
    _write_prefs(_prefs_path(settings, user_id), prefs)
    return prefs


__all__ = ["router", "ExecutorPreference", "ExecutorPreferenceUpdate"]
