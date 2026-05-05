"""X-Request-ID correlation middleware.

Reads an inbound ``X-Request-ID`` header (set by an upstream LB or by a
client retrying a known request) or generates a fresh UUID4. Echoes the
value back on the response and stashes it in a ContextVar so log
records, exception handlers, and downstream code can include it in
their output.

Pure ASGI rather than a Starlette ``BaseHTTPMiddleware`` subclass: we
want zero overhead per request and we want to mutate the response
headers without forcing the body to be buffered.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_request_id_var: ContextVar[str] = ContextVar("plato_request_id", default="")


def get_request_id() -> str:
    """Return the current request's correlation id, or empty string."""
    return _request_id_var.get()


class RequestIdMiddleware:
    def __init__(self, app) -> None:  # noqa: ANN001 — ASGI callable
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        # Inbound header lookup. ``scope["headers"]`` is a list of
        # (bytes, bytes) tuples; dict() gives us last-wins lookup which
        # matches HTTP semantics for a duplicated header.
        headers = dict(scope.get("headers", []))
        rid_bytes = headers.get(b"x-request-id")
        rid = (
            rid_bytes.decode("utf-8", errors="replace")
            if rid_bytes
            else str(uuid.uuid4())
        )
        token = _request_id_var.set(rid)

        async def send_with_header(message):  # noqa: ANN001
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-request-id", rid.encode()),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            _request_id_var.reset(token)
