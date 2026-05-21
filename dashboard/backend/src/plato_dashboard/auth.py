"""Multi-tenant auth for the dashboard.

The dashboard ships single-user by default — a no-op auth shim until you
flip ``PLATO_DASHBOARD_AUTH_REQUIRED=1`` or ``PLATO_AUTH=enabled``. In
required-mode every request must carry an ``X-Plato-User`` header or the
dashboard-managed ``plato_user`` cookie; the value scopes the project
directory and the run-manifest tenant id.

We deliberately avoid any signed-token plumbing here: the dashboard does
not own identity. The header is meant to be set by the upstream proxy
(Cloudflare Access, oauth2-proxy, ...) after it has authenticated the
user against the real IdP. In dev or single-user setups, the header is
simply absent and we fall through to the legacy un-namespaced layout.
"""

from __future__ import annotations

import hmac
import os
import re

from fastapi import HTTPException, Request, status

USER_HEADER = "X-Plato-User"
USER_COOKIE = "plato_user"
PROXY_SECRET_HEADER = "X-Plato-Proxy-Secret"
AUTH_REQUIRED_ENV = "PLATO_DASHBOARD_AUTH_REQUIRED"
LEGACY_AUTH_ENV = "PLATO_AUTH"
BACKEND_PROXY_SECRET_ENV = "PLATO_BACKEND_PROXY_SECRET"
MIN_PROXY_SECRET_LENGTH = 32

# A user id is used directly as a path segment under
# ``<project_root>/users/<user_id>/``. Anything outside this allowlist
# would either confuse the filesystem (slashes, dots) or open path
# traversal (``..``) — neither is acceptable. 64 chars is generous for
# any legitimate identity scheme (uuid, slug, email-local-part).
_USER_ID_RE = re.compile(r"\A[A-Za-z0-9._-]{1,64}\Z")


def auth_required() -> bool:
    """True when the deployment demands an authenticated user header."""
    return (
        os.environ.get(AUTH_REQUIRED_ENV) == "1"
        or os.environ.get(LEGACY_AUTH_ENV) == "enabled"
    )


def _proxy_secret() -> str | None:
    secret = os.environ.get(BACKEND_PROXY_SECRET_ENV, "").strip()
    return secret or None


def proxy_secret_configuration_error() -> str | None:
    secret = _proxy_secret()
    if secret is None:
        return None
    if len(secret) < MIN_PROXY_SECRET_LENGTH:
        return (
            f"{BACKEND_PROXY_SECRET_ENV} must be at least "
            f"{MIN_PROXY_SECRET_LENGTH} characters."
        )
    return None


def proxy_secret_configured() -> bool:
    return _proxy_secret() is not None


def has_trusted_proxy_secret(request: Request) -> bool:
    secret = _proxy_secret()
    if secret is None:
        return True
    supplied = request.headers.get(PROXY_SECRET_HEADER, "")
    return hmac.compare_digest(supplied, secret)


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


def _clean_user_id(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if not _is_safe_user_id(cleaned):
        return None
    return cleaned


def extract_user_id(request: Request) -> str | None:
    """Return the requester's user id, or ``None`` when unauthenticated.

    Header wins when both are present so upstream authenticated proxies
    can override the dashboard cookie. The returned value has been
    validated against :data:`_USER_ID_RE` so callers can use it directly
    as a filesystem path segment without additional sanitization.

    When ``PLATO_BACKEND_PROXY_SECRET`` is configured, tenant identity is
    accepted only from requests carrying the matching
    ``X-Plato-Proxy-Secret`` header. This keeps the legacy local contract
    unchanged while letting production deployments bind direct backend
    exposure to the trusted Next/proxy layer instead of client-supplied
    headers or cookies.
    """
    if not has_trusted_proxy_secret(request):
        return None

    header_user_id = _clean_user_id(request.headers.get(USER_HEADER))
    if header_user_id:
        return header_user_id
    return _clean_user_id(request.cookies.get(USER_COOKIE))


def require_user_id(request: Request) -> str:
    """Return the requester's user id, or raise 401 in required-mode.

    - Required-mode + missing identity → ``HTTPException(401)``.
    - Required-mode + header present → return its value.
    - Not-required mode + header present → return its value.
    - Not-required mode + missing identity → return ``""`` (legacy
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
                    f"Missing required header '{USER_HEADER}' or cookie "
                    f"'{USER_COOKIE}'. The dashboard is configured for "
                    "multi-tenant mode."
                ),
            },
        )
    return ""


__all__ = [
    "AUTH_REQUIRED_ENV",
    "BACKEND_PROXY_SECRET_ENV",
    "LEGACY_AUTH_ENV",
    "MIN_PROXY_SECRET_LENGTH",
    "PROXY_SECRET_HEADER",
    "USER_COOKIE",
    "USER_HEADER",
    "auth_required",
    "extract_user_id",
    "has_trusted_proxy_secret",
    "proxy_secret_configuration_error",
    "proxy_secret_configured",
    "require_user_id",
]
