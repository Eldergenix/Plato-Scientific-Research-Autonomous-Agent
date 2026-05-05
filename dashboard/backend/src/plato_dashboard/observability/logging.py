"""Structured JSON logging for the Plato dashboard.

Opt-in via ``init_observability``. When enabled, replaces the root
logger's handlers with a single stdout JSON stream so a log shipper
(Vector, Promtail, Fluent Bit, etc.) can ingest events without
parsing free-form text.
"""
from __future__ import annotations

import logging

# python-json-logger 2.x exposes the formatter at ``pythonjsonlogger.jsonlogger``;
# 3.x renamed the canonical path to ``pythonjsonlogger.json``. Try the modern
# path first, fall back to the legacy one so both wheels work.
try:
    from pythonjsonlogger.json import JsonFormatter
except ImportError:  # pragma: no cover - depends on installed wheel
    from pythonjsonlogger.jsonlogger import JsonFormatter  # type: ignore[no-redef]


def configure_json_logging(level: str = "INFO") -> None:
    """Configure root logger to emit JSON to stdout. Idempotent."""
    fmt = "%(asctime)s %(name)s %(levelname)s %(message)s %(process)d %(threadName)s"
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter(fmt, rename_fields={"levelname": "level", "asctime": "ts"})
    )
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level)


__all__ = ["configure_json_logging"]
