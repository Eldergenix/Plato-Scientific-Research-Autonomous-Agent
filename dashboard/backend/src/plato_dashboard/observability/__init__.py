"""Observability bootstrap — Prometheus metrics + structured JSON logs.

Both surfaces are opt-in so existing single-user installs don't pay
the cost of a JSON log shipper or a metrics scraper they aren't using.
Set ``PLATO_OBS_JSON_LOGS=1`` to flip JSON logging on; metrics always
register but are only exposed via the ``/api/v1/metrics`` endpoint.
"""
from __future__ import annotations

import os

from .logging import configure_json_logging
from .metrics import (  # noqa: F401 — re-exported for callers
    ACTIVE_RUNS,
    ERROR_TOTAL,
    HTTP_REQUEST_DURATION,
    REGISTRY_INFO,
    RENDER_DURATION_SECONDS,
    RUN_COMPLETION_TOTAL,
    RUN_DURATION_SECONDS,
    SSE_SUBSCRIBERS,
)


def init_observability() -> None:
    """Initialize observability if PLATO_OBS_JSON_LOGS=1. No-op otherwise."""
    if os.getenv("PLATO_OBS_JSON_LOGS", "").lower() in ("1", "true", "yes"):
        configure_json_logging(level=os.getenv("PLATO_LOG_LEVEL", "INFO"))


__all__ = [
    "ACTIVE_RUNS",
    "ERROR_TOTAL",
    "HTTP_REQUEST_DURATION",
    "REGISTRY_INFO",
    "RENDER_DURATION_SECONDS",
    "RUN_COMPLETION_TOTAL",
    "RUN_DURATION_SECONDS",
    "SSE_SUBSCRIBERS",
    "configure_json_logging",
    "init_observability",
]
