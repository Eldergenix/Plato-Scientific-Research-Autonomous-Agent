"""API package.

We attach the citation-graph view router here rather than in
``server.py`` so the latter stays sealed against feature-stream churn.
The hook wraps :func:`server.create_app` once so every fresh app — test
fixture or production — gets the route automatically.
"""

from __future__ import annotations

from . import server as _server
from .citation_graph_view import router as _citation_graph_router


def _patched_create_app() -> "_server.FastAPI":  # type: ignore[name-defined]
    app = _original_create_app()
    # Idempotent: APIRouter(include_router) is safe to call once per app.
    app.include_router(_citation_graph_router, prefix="/api/v1", tags=["citations"])
    return app


_original_create_app = _server.create_app
_server.create_app = _patched_create_app  # type: ignore[assignment]

# Re-bind the module-level ``app`` produced at import time too — it was
# created before our patch took effect.
_server.app = _patched_create_app()
