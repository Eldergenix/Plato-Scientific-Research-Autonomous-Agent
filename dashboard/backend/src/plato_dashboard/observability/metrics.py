"""Prometheus metrics for the Plato dashboard.

Defined once at import time so /metrics scrapes always return a stable
series shape. Counters monotonically increase across process lifetime;
gauges are refreshed by the /metrics handler (or by the call sites that
own the underlying state).
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, Info

REGISTRY_INFO = Info("plato_dashboard", "Plato Dashboard build info")

ACTIVE_RUNS = Gauge(
    "plato_active_runs",
    "Active runs currently executing",
)

RUN_COMPLETION_TOTAL = Counter(
    "plato_run_completion_total",
    "Run completions",
    ["status", "stage"],
)

RUN_DURATION_SECONDS = Histogram(
    "plato_run_duration_seconds",
    "Run duration",
    ["stage"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600, 7200),
)

SSE_SUBSCRIBERS = Gauge(
    "plato_sse_subscribers",
    "Active SSE subscribers",
)

ERROR_TOTAL = Counter(
    "plato_error_total",
    "Errors by source",
    ["source", "kind"],
)

RENDER_DURATION_SECONDS = Histogram(
    "plato_render_duration_seconds",
    "Quarkdown render duration",
    ["doctype"],
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120),
)

HTTP_REQUEST_DURATION = Histogram(
    "plato_http_request_seconds",
    "HTTP request duration",
    ["method", "path", "status"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 5, 10),
)


__all__ = [
    "ACTIVE_RUNS",
    "ERROR_TOTAL",
    "HTTP_REQUEST_DURATION",
    "REGISTRY_INFO",
    "RENDER_DURATION_SECONDS",
    "RUN_COMPLETION_TOTAL",
    "RUN_DURATION_SECONDS",
    "SSE_SUBSCRIBERS",
]
