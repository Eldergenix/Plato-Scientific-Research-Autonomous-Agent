"""Pure-ASGI middleware for the dashboard backend.

These wrap the FastAPI app *outside* the routing layer so they observe
every request — including the ones that get rejected by
``BodySizeLimitMiddleware`` before FastAPI ever sees them.
"""

from .request_id import RequestIdMiddleware, get_request_id

__all__ = ["RequestIdMiddleware", "get_request_id"]
