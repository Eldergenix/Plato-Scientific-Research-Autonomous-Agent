"""
Centralised logging configuration for Plato.

Call :func:`configure_logging` once per process at the entry point
(``plato run`` / ``plato dashboard`` / ``plato loop`` / dashboard
worker / standalone script). It is idempotent — repeated calls
update the level but never re-add handlers.

Why this lives here rather than in :mod:`plato.cli`:
    Several entry points exist (CLI subcommands, dashboard worker,
    eval runner). They each need the same log shape. Centralising
    avoids per-entry-point drift.

Layout:
    - A single ``StreamHandler`` on stderr.
    - A formatter that surfaces the optional :data:`run_id` contextvar
      so log lines can be correlated back to a manifest.
    - Noisy third-party loggers (``langchain*``, ``httpx``, ``openai``)
      are capped at ``WARNING`` so the user sees Plato output, not
      framework chatter.
"""
from __future__ import annotations

import contextvars
import logging
import os
import sys
from typing import Iterable

# Per-task ``run_id`` correlation. Workflows set this at the start of
# ``Plato.get_*`` via ``run_id_var.set(recorder.manifest.run_id)`` and
# every log record emitted under that task picks the value up. When
# unset, the formatter writes ``"-"`` so the column stays aligned.
run_id_var: "contextvars.ContextVar[str | None]" = contextvars.ContextVar(
    "plato_run_id", default=None
)


_NOISY_LOGGERS: tuple[str, ...] = (
    "langchain",
    "langchain_core",
    "langchain_community",
    "langgraph",
    "httpx",
    "httpcore",
    "openai",
    "anthropic",
    "google.generativeai",
    "urllib3",
)

# Sentinel attribute on the root handler so we can detect whether we
# already configured logging in this process and skip re-installing
# the handler. Without it, repeated configure_logging() calls would
# stack handlers and emit each line N times.
_PLATO_HANDLER_ATTR = "_plato_root_handler"


class _RunIdFilter(logging.Filter):
    """Inject the current ``run_id`` contextvar onto every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = run_id_var.get() or "-"
        return True


def _resolve_level(level: int | str | None) -> int:
    """Pick the effective log level, honouring ``PLATO_LOG_LEVEL`` env var."""
    if level is not None:
        if isinstance(level, str):
            return logging.getLevelName(level.upper())
        return level
    env = os.environ.get("PLATO_LOG_LEVEL")
    if env:
        return logging.getLevelName(env.upper())
    return logging.INFO


def configure_logging(
    *,
    level: int | str | None = None,
    quiet_third_party: bool = True,
    noisy_loggers: Iterable[str] = _NOISY_LOGGERS,
    fmt: str | None = None,
) -> None:
    """Install a single root-handler logging config.

    Idempotent: calling twice updates the level but does not duplicate
    handlers. Call once at every entry point (CLI, worker, dashboard
    lifespan).
    """
    root = logging.getLogger()
    effective_level = _resolve_level(level)
    root.setLevel(effective_level)

    # Find or install the canonical handler.
    handler: logging.Handler | None = None
    for h in root.handlers:
        if getattr(h, _PLATO_HANDLER_ATTR, False):
            handler = h
            break

    if handler is None:
        handler = logging.StreamHandler(stream=sys.stderr)
        setattr(handler, _PLATO_HANDLER_ATTR, True)
        handler.addFilter(_RunIdFilter())
        root.addHandler(handler)

    handler.setLevel(effective_level)
    handler.setFormatter(
        logging.Formatter(
            fmt or "%(levelname)s %(name)s [%(run_id)s] %(message)s",
        )
    )

    if quiet_third_party:
        for name in noisy_loggers:
            logging.getLogger(name).setLevel(logging.WARNING)


__all__ = ["configure_logging", "run_id_var"]
