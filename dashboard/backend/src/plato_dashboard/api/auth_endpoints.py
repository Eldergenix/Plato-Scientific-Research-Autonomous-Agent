"""Auth endpoints for the dashboard's tenant-id login flow.

Phase-5 multi-tenant work expects an ``X-Plato-User`` header on every
request — but until this stream there was no in-dashboard way to set it.
These endpoints give the frontend a place to (a) tell the server "this is
the user id I want to use", (b) clear that choice on logout, and (c) ask
"who am I?" on page load.

The cookie (``plato_user``) is the source of truth on the server. The
header (``X-Plato-User``) remains supported so external integrations and
the existing ``extract_user_id`` helper in ``plato_dashboard.auth`` keep
working unchanged.

Integration note: the eventual ``plato_dashboard.auth`` module is expected
to expose two helpers we read here lazily:

* ``extract_user_id(request)`` — pulls the user id from the header.
  ``extract_user_id`` should be extended to also read the cookie; until
  that's done, the dashboard sends the header explicitly via fetch's
  ``credentials: 'include'`` in same-origin requests, which makes the
  cookie available to any handler that imports it directly.
* ``auth_required()`` — boolean: is the server configured to require
  auth? We fall back to ``Settings.is_auth_required`` when the helper
  is not yet present.

The lazy import means this file does not blow up at import time on a
worktree where ``auth.py`` has not landed yet.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..settings import get_settings

router = APIRouter()

_COOKIE_NAME = "plato_user"
# 30-day cookie. Keeps the user signed in across browser restarts without
# being so long-lived that a stale tenant id sticks around forever.
_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30


def _read_user_id(request: Request) -> str | None:
    """Resolve the active user id from header or cookie, in that order.

    Header beats cookie so external callers (CI, scripts, the existing
    ``extract_user_id`` helper) can override the browser session without
    having to clear the cookie first.
    """
    header = request.headers.get("X-Plato-User")
    if header and header.strip():
        return header.strip()
    cookie = request.cookies.get(_COOKIE_NAME)
    if cookie and cookie.strip():
        return cookie.strip()
    return None


def _auth_required() -> bool:
    """Whether the server is configured to require auth.

    Prefer the canonical helper from ``plato_dashboard.auth`` if it has
    landed; fall back to ``Settings.is_auth_required`` so this module
    works on a fresh worktree.
    """
    try:
        from .. import auth  # type: ignore[attr-defined]

        helper = getattr(auth, "auth_required", None)
        if callable(helper):
            return bool(helper())
    except Exception:
        pass
    return get_settings().is_auth_required


class LoginRequest(BaseModel):
    """Body for ``POST /auth/login``.

    The 128-char cap blocks pathological values that would also fail
    silently when written to the ``plato_user`` httponly cookie (most
    browsers cap cookie values around 4 KiB).
    """

    user_id: str = Field(min_length=1, max_length=128)


def _cookie_secure() -> bool:
    """``Secure`` cookie flag — on except for local dev.

    Browsers refuse to send Secure cookies over HTTP. We default to True
    (production-safe) and only opt out when ``PLATO_INSECURE_COOKIES=1``
    is set, which is the explicit local-dev escape hatch the dev server
    uses on http://127.0.0.1.
    """
    import os

    return os.environ.get("PLATO_INSECURE_COOKIES", "").lower() not in {
        "1", "true", "yes", "on",
    }


@router.post("/auth/login")
def login(response: Response, body: LoginRequest) -> dict[str, Any]:
    """Set the ``plato_user`` cookie and echo the chosen user id back."""
    user_id = body.user_id.strip()
    if not user_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_user_id", "message": "user_id must be a non-empty string"},
        )
    # Iter-9: validate against the canonical user-id regex BEFORE writing
    # the cookie. Previously the only validation was Pydantic's
    # max_length=128 + a strip() — values like ``../admin`` or ``a/b``
    # passed and were stored in the cookie. ``extract_user_id`` then
    # rejected them on read, but the cookie itself contained the unsafe
    # value (and any direct cookie consumer in this module would see
    # the raw string).
    from ..auth import _is_safe_user_id

    if not _is_safe_user_id(user_id):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_user_id",
                "message": (
                    "user_id must match [A-Za-z0-9_-]{1,64}; reserved "
                    "characters (slash, dot, whitespace) are rejected."
                ),
            },
        )
    response.set_cookie(
        key=_COOKIE_NAME,
        value=user_id,
        max_age=_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        # No domain — scope to the current host. Avoids accidentally
        # leaking the cookie to a sibling subdomain in shared deploys.
        path="/",
    )
    return {"user_id": user_id, "ok": True}


@router.post("/auth/logout")
def logout(response: Response) -> dict[str, Any]:
    """Clear the ``plato_user`` cookie."""
    # Iter-9: mirror every attribute from login so strict browsers
    # (Safari ITP, Chrome SameSite=Lax) actually expire the cookie.
    # Mismatched attribute sets cause Set-Cookie deletes to no-op
    # silently in modern browsers.
    response.delete_cookie(
        key=_COOKIE_NAME,
        path="/",
        secure=_cookie_secure(),
        httponly=True,
        samesite="lax",
    )
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request) -> dict[str, Any]:
    """Resolve the current user id (header or cookie) and the auth flag."""
    return {
        "user_id": _read_user_id(request),
        "auth_required": _auth_required(),
    }
