"""Double-submit cookie CSRF protection.

Defence-in-depth on top of SameSite cookies and the existing
``X-Plato-User`` proxy header. For every state-mutating request
(``POST``/``PUT``/``PATCH``/``DELETE``) we require an ``X-CSRF-Token``
header whose value matches the ``plato_csrf`` cookie. The cookie is
deliberately readable by client JavaScript (no ``HttpOnly``) so the
frontend can echo it back in the header — that is the whole point of
the double-submit pattern: an attacker on a different origin cannot
read the cookie and therefore cannot forge a matching header.

Safe HTTP methods (``GET``/``HEAD``/``OPTIONS``/``TRACE``) and any
caller-supplied exempt paths skip the check entirely. They still get a
freshly minted ``plato_csrf`` cookie on the way out if none was
present, so the very first navigation to the SPA bootstraps the token
without an extra round trip.

Pure ASGI rather than a Starlette ``BaseHTTPMiddleware`` subclass so we
can mutate response headers without buffering the body and so the
overhead per safe request stays minimal.
"""

from __future__ import annotations

import json
import secrets
from typing import Iterable

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_COOKIE_NAME = "plato_csrf"
_HEADER_NAME = "x-csrf-token"


class CsrfMiddleware:
    """Reject mutating requests whose CSRF header doesn't match the cookie."""

    def __init__(self, app, exempt_paths: Iterable[str] = ()) -> None:  # noqa: ANN001
        self.app = app
        self.exempt_paths = tuple(exempt_paths)

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        method = scope.get("method", "").upper()
        path = scope.get("path", "")

        # Safe methods and exempt paths skip validation but still get a
        # token minted on the way out if they don't already carry one.
        if method in _SAFE_METHODS or any(
            path.startswith(p) for p in self.exempt_paths
        ):
            return await self._app_with_csrf_set(scope, receive, send)

        # Mutating request: header must match cookie. ``compare_digest``
        # is constant-time to avoid leaking match progress through
        # response timing.
        headers = dict(scope.get("headers", []))
        cookie_header = headers.get(b"cookie", b"").decode("utf-8", errors="replace")
        cookie_token = self._parse_cookie(cookie_header, _COOKIE_NAME)
        sent_token = headers.get(_HEADER_NAME.encode(), b"").decode(
            "utf-8", errors="replace"
        )
        if (
            not cookie_token
            or not sent_token
            or not secrets.compare_digest(cookie_token, sent_token)
        ):
            return await self._reject(send, 403, "csrf_token_invalid")

        return await self.app(scope, receive, send)

    async def _app_with_csrf_set(self, scope, receive, send) -> None:  # noqa: ANN001
        """Pass through; on the response, mint a cookie if the request had none."""
        headers = dict(scope.get("headers", []))
        cookie_header = headers.get(b"cookie", b"").decode("utf-8", errors="replace")
        if self._parse_cookie(cookie_header, _COOKIE_NAME):
            return await self.app(scope, receive, send)

        new_token = secrets.token_urlsafe(32)
        cookie_value = (
            f"{_COOKIE_NAME}={new_token}; Path=/; SameSite=Lax"
        ).encode()

        async def send_with_cookie(message):  # noqa: ANN001
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"set-cookie", cookie_value),
                ]
            await send(message)

        return await self.app(scope, receive, send_with_cookie)

    @staticmethod
    def _parse_cookie(header: str, name: str) -> str:
        """Return the value for ``name`` in a Cookie header, or ``""``."""
        for part in header.split(";"):
            kv = part.strip().split("=", 1)
            if len(kv) == 2 and kv[0] == name:
                return kv[1]
        return ""

    @staticmethod
    async def _reject(send, status: int, code: str) -> None:  # noqa: ANN001
        body = json.dumps(
            {"detail": {"code": code, "message": "CSRF token invalid"}}
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


__all__ = ["CsrfMiddleware"]
