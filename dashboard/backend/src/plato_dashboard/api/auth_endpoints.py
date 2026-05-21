"""Auth endpoints for the dashboard's tenant-id login flow.

Phase-5 multi-tenant work expects an ``X-Plato-User`` header on every
request — but until this stream there was no in-dashboard way to set it.
These endpoints give the frontend a place to (a) tell the server "this is
the user id I want to use", (b) clear that choice on logout, and (c) ask
"who am I?" on page load.

The canonical ``plato_dashboard.auth.extract_user_id`` helper owns the
header/cookie precedence and optional trusted-proxy guard so ``/auth/me``
cannot drift from the rest of the backend.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..auth import USER_COOKIE, _is_safe_user_id, auth_required, extract_user_id
from ..settings import get_settings

router = APIRouter()

# 30-day cookie. Keeps the user signed in across browser restarts without
# being so long-lived that a stale tenant id sticks around forever.
_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30


def _auth_required() -> bool:
    """Whether the server is configured to require auth."""
    return auth_required() or get_settings().is_auth_required


def _request_is_https(request: Request) -> bool:
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",", 1)[0]
    proto = forwarded_proto.strip().lower() or request.url.scheme
    return proto == "https"


class LoginRequest(BaseModel):
    """Body for ``POST /auth/login``.

    The 64-char cap blocks pathological values that would also fail
    silently when written to the ``plato_user`` httponly cookie (most
    browsers cap cookie values around 4 KiB).
    """

    user_id: str | None = Field(default=None, max_length=64)


@router.post("/auth/login")
def login(request: Request, response: Response, body: LoginRequest) -> dict[str, Any]:
    """Set the ``plato_user`` cookie and echo the chosen user id back."""
    user_id = body.user_id.strip() if isinstance(body.user_id, str) else ""
    if not user_id or not _is_safe_user_id(user_id):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_user_id",
                "message": "user_id must match [A-Za-z0-9._-] and be safe as a path segment",
            },
        )
    response.set_cookie(
        key=USER_COOKIE,
        value=user_id,
        max_age=_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=_request_is_https(request),
        # No domain — scope to the current host. Avoids accidentally
        # leaking the cookie to a sibling subdomain in shared deploys.
        path="/",
    )
    return {"user_id": user_id, "ok": True}


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict[str, Any]:
    """Clear the ``plato_user`` cookie."""
    response.delete_cookie(
        key=USER_COOKIE,
        path="/",
        secure=_request_is_https(request),
    )
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request) -> dict[str, Any]:
    """Resolve the current user id (header or cookie) and the auth flag."""
    return {
        "user_id": extract_user_id(request),
        "auth_required": _auth_required(),
    }
