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
import re

from fastapi import HTTPException, Request, status

USER_HEADER = "X-Plato-User"
USER_COOKIE = "plato_user"
AUTH_REQUIRED_ENV = "PLATO_DASHBOARD_AUTH_REQUIRED"

# A user id is used directly as a path segment under
# ``<project_root>/users/<user_id>/``. Anything outside this allowlist
# would either confuse the filesystem (slashes, dots) or open path
# traversal (``..``) — neither is acceptable. 64 chars is generous for
# any legitimate identity scheme (uuid, slug, email-local-part).
_USER_ID_RE = re.compile(r"\A[A-Za-z0-9._-]{1,64}\Z")


def auth_required() -> bool:
    """True when the deployment demands an authenticated user header."""
    return os.environ.get(AUTH_REQUIRED_ENV) == "1"


def _is_safe_user_id(value: str) -> bool:
    """Return True when ``value`` is safe to use as a path segment.

    Rejects anything containing a path separator, parent-dir reference,
    null byte, leading/trailing dot, or characters outside
    ``[A-Za-z0-9._-]``. The dot constraint also blocks the ``.`` and
    ``..`` directory entries. Length is capped at 64 to bound storage
    layout depth.
    """
    if not _USER_ID_RE.match(value):
        return False
    # Forbid leading/trailing dot so we never produce a hidden directory
    # or a path that resolves to the parent dir.
    if value.startswith(".") or value.endswith("."):
        return False
    return True


def extract_user_id(request: Request) -> str | None:
    """Return the requester's user id, or ``None`` when unauthenticated.

    Source order:
    1. ``X-Plato-User`` header — preferred for API/CLI callers and
       upstream proxies (Cloudflare Access, oauth2-proxy, ...) that
       inject identity downstream.
    2. ``plato_user`` cookie — set by ``/api/v1/auth/login`` for the
       browser dashboard. The frontend's ``fetch`` calls don't repeat
       the header on every request; without this fallback every
       browser-driven router invocation would 401 in auth-required
       mode.

    The returned value has been validated against :data:`_USER_ID_RE`
    so callers can use it directly as a filesystem path segment without
    additional sanitization. An invalid value is treated as missing.
    """
    candidates: list[str | None] = [
        request.headers.get(USER_HEADER),
        request.cookies.get(USER_COOKIE),
    ]
    for raw in candidates:
        if raw is None:
            continue
        cleaned = raw.strip()
        if not cleaned:
            continue
        if not _is_safe_user_id(cleaned):
            continue
        return cleaned
    return None


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
