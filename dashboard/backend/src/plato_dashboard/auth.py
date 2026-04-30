"""Multi-tenant auth for the dashboard.

The dashboard ships single-user by default — a no-op auth shim until you
flip ``PLATO_DASHBOARD_AUTH_REQUIRED=1``. In required-mode every request
must carry an ``X-Plato-User`` header; the value scopes the project
directory and the run-manifest tenant id.

We deliberately avoid any signed-token plumbing here: the dashboard does
not own identity. The header is meant to be set by the upstream proxy
(Cloudflare Access, oauth2-proxy, ...) after it has authenticated the
user against the real IdP. In dev or single-user setups, the header is
simply absent and we fall through to the legacy un-namespaced layout.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request, status

USER_HEADER = "X-Plato-User"
AUTH_REQUIRED_ENV = "PLATO_DASHBOARD_AUTH_REQUIRED"


def auth_required() -> bool:
    """True when the deployment demands an authenticated user header."""
    return os.environ.get(AUTH_REQUIRED_ENV) == "1"


def extract_user_id(request: Request) -> str | None:
    """Return the requester's user id, or ``None`` when unauthenticated.

    Returns the header value verbatim (stripped) when present. Returns
    ``None`` either when the header is missing in not-required mode, or
    when required-mode is on but no header was supplied — callers in
    required-mode should refuse the request via :func:`require_user_id`.
    """
    raw = request.headers.get(USER_HEADER)
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    return cleaned


def require_user_id(request: Request) -> str:
    """Return the requester's user id, or raise 401 in required-mode.

    - Required-mode + missing header → ``HTTPException(401)``.
    - Required-mode + header present → return its value.
    - Not-required mode + header present → return its value.
    - Not-required mode + missing header → return ``""`` (legacy
      single-user fallback). Routes can branch on truthiness.
    """
    user_id = extract_user_id(request)
    if user_id:
        return user_id
    if auth_required():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "auth_required",
                "message": (
                    f"Missing required header '{USER_HEADER}'. The dashboard "
                    "is configured for multi-tenant mode."
                ),
            },
        )
    return ""


__all__ = [
    "AUTH_REQUIRED_ENV",
    "USER_HEADER",
    "auth_required",
    "extract_user_id",
    "require_user_id",
]
