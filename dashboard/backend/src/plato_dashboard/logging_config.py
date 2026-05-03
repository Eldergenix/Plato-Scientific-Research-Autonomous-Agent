"""Structured logging + observability for the Plato dashboard backend.

This module sits beside the existing ``plato.logging_config`` (which
configures Plato workflow logging globally) and layers on the bits the
dashboard process specifically cares about:

* JSON output via ``python-json-logger`` when it's installed, plain text
  otherwise — the heavy dep stays optional.
* Three correlation contextvars: ``request_id``, ``user_id``, and a
  re-export of ``run_id_var`` from ``plato.logging_config`` so the
  dashboard never holds two competing run-id contextvars.
* ``setup_logging()`` — idempotent, called from the FastAPI lifespan.
* ``RequestLoggingMiddleware`` — mints a request_id, binds it to the
  contextvar, logs request completion, and surfaces 5xx with a
  traceback when one happens.
* ``unhandled_exception_handler`` — last-resort catch that logs the
  failure with full structured detail and returns a stable JSON body
  the client can quote back to support.

The middleware purposely does NOT swallow ``HTTPException`` — FastAPI's
own handler turns those into well-formed responses already, and we
don't want a route that does ``raise HTTPException(404)`` to show up
as a server error in the structured log stream.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Re-export the shared run_id contextvar so callers don't have to know
# whether it lives here or in ``plato.logging_config`` — there is one
# run_id contextvar in the process, full stop.
from plato.logging_config import run_id_var

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "plato_request_id", default=None
)
user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "plato_user_id", default=None
)

_DASHBOARD_HANDLER_ATTR = "_plato_dashboard_root_handler"

_LOG_RECORD_DEFAULTS = frozenset(
    logging.LogRecord(
        "name", logging.INFO, "pathname", 0, "msg", None, None
    ).__dict__
)


class _ContextFilter(logging.Filter):
    """Stamp every record with our three correlation ids.

    Using a Filter instead of stuffing the values into ``extra=`` at
    every call site means existing ``logger.info("foo")`` calls
    automatically pick up the bound context. When a caller passes an
    explicit ``extra={"request_id": ...}`` we leave it alone — the
    explicit value always wins so handlers like
    ``unhandled_exception_handler`` can attribute the record to a
    request even when the contextvar binding has already been reset.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None):
            record.request_id = request_id_var.get() or "-"
        if not getattr(record, "user_id", None):
            record.user_id = user_id_var.get() or "-"
        if not getattr(record, "run_id", None):
            record.run_id = run_id_var.get() or "-"
        return True


class _PlainTextFallbackFormatter(logging.Formatter):
    """Used when ``python-json-logger`` isn't importable.

    Emits ISO timestamps and the three correlation ids as a stable
    suffix so a grep-based pipeline still works without the JSON dep.
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        base = (
            f"{ts} {record.levelname} {record.name} "
            f"[req={getattr(record, 'request_id', '-')} "
            f"user={getattr(record, 'user_id', '-')} "
            f"run={getattr(record, 'run_id', '-')}] "
            f"{record.getMessage()}"
        )
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


class _StdlibJsonFormatter(logging.Formatter):
    """Last-resort JSON formatter using only the stdlib.

    We prefer ``python-json-logger`` when it's available because it
    handles edge cases (extras, non-serialisable objects) more
    robustly. This stdlib version is only here so the test suite and
    minimal installs don't have to choose between JSON and the dep.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "user_id": getattr(record, "user_id", "-"),
            "run_id": getattr(record, "run_id", "-"),
        }
        # Surface anything the caller passed via ``extra=`` without
        # stomping on the structural fields above.
        for key, value in record.__dict__.items():
            if key in _LOG_RECORD_DEFAULTS or key in payload:
                continue
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                value = repr(value)
            payload[key] = value
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            payload["traceback"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _build_formatter(use_json: bool) -> logging.Formatter:
    """Pick the best available formatter without importing eagerly."""
    if not use_json:
        return _PlainTextFallbackFormatter()
    try:
        # ``python-json-logger`` ships its module under both ``pythonjsonlogger``
        # (older) and ``python_json_logger`` (newer). Try both.
        try:
            from pythonjsonlogger import jsonlogger  # type: ignore[import-not-found]
        except ImportError:
            from python_json_logger import jsonlogger  # type: ignore[import-not-found, no-redef]
    except ImportError:
        return _StdlibJsonFormatter()

    fmt = (
        "%(timestamp)s %(level)s %(logger)s %(message)s "
        "%(request_id)s %(user_id)s %(run_id)s"
    )
    return jsonlogger.JsonFormatter(
        fmt,
        rename_fields={
            "asctime": "timestamp",
            "levelname": "level",
            "name": "logger",
        },
        timestamp=True,
    )


def _resolve_level(level: int | str | None) -> int:
    """Honour explicit override, then ``PLATO_LOG_LEVEL`` env var, then INFO."""
    if level is not None:
        if isinstance(level, str):
            return logging.getLevelName(level.upper())
        return level
    env = os.environ.get("PLATO_LOG_LEVEL")
    if env:
        return logging.getLevelName(env.upper())
    return logging.INFO


def setup_logging(
    *,
    level: int | str | None = None,
    use_json: bool | None = None,
) -> None:
    """Install the dashboard's structured-logging stack on the root logger.

    Idempotent — calling twice updates the level but never stacks
    handlers. ``use_json`` defaults to True when ``PLATO_LOG_JSON`` is
    unset; pass ``False`` from tests to keep output greppable.
    """
    if use_json is None:
        flag = os.environ.get("PLATO_LOG_JSON", "1").strip().lower()
        use_json = flag not in {"0", "false", "no", ""}

    effective_level = _resolve_level(level)

    root = logging.getLogger()
    root.setLevel(effective_level)

    handler: logging.Handler | None = None
    for h in root.handlers:
        if getattr(h, _DASHBOARD_HANDLER_ATTR, False):
            handler = h
            break

    if handler is None:
        handler = logging.StreamHandler(stream=sys.stderr)
        setattr(handler, _DASHBOARD_HANDLER_ATTR, True)
        handler.addFilter(_ContextFilter())
        root.addHandler(handler)

    handler.setLevel(effective_level)
    handler.setFormatter(_build_formatter(use_json=use_json))

    # Cap the noisiest framework loggers so the dashboard's own
    # records aren't drowned out by httpx connection chatter.
    for name in (
        "httpx",
        "httpcore",
        "uvicorn.access",
        "uvicorn.error",
        "asyncio",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)


# --------------------------------------------------------------- middleware

_HEADER_REQUEST_ID = "X-Request-Id"


def _decode_header(headers: list[tuple[bytes, bytes]], name: str) -> str:
    """Pull a header value off an ASGI scope's headers list."""
    needle = name.lower().encode("latin-1")
    for k, v in headers:
        if k.lower() == needle:
            try:
                return v.decode("latin-1").strip()
            except UnicodeDecodeError:
                return ""
    return ""


class RequestLoggingMiddleware:
    """Pure-ASGI middleware: mint request_id, bind contextvars, log result.

    Using raw ASGI rather than ``BaseHTTPMiddleware`` is deliberate.
    ``BaseHTTPMiddleware`` runs the inner app in a separate ``anyio``
    task, which means contextvars set in ``dispatch()`` aren't visible
    to route handlers, exception handlers, or downstream loggers (each
    sub-task gets a snapshot of the outer context, not a live binding).
    With pure ASGI everything stays on one task and ``contextvars.set``
    propagates cleanly into handlers and the global ``logging`` filter.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        logger_name: str = "plato_dashboard.request",
    ) -> None:
        self._app = app
        self._logger = logging.getLogger(logger_name)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers: list[tuple[bytes, bytes]] = scope.get("headers") or []
        incoming = _decode_header(headers, _HEADER_REQUEST_ID)
        request_id = incoming if 0 < len(incoming) <= 64 else uuid.uuid4().hex

        raw_user = _decode_header(headers, "X-Plato-User")
        user_id = raw_user[:128] if raw_user else None

        rid_token = request_id_var.set(request_id)
        user_token = user_id_var.set(user_id)

        # Stash on scope state so handlers (especially the unhandled
        # exception handler — which runs OUTSIDE this middleware in
        # Starlette's ServerErrorMiddleware, after our ``finally``
        # already reset the contextvars) can still recover the
        # correlation ids via ``request.state``.
        scope.setdefault("state", {})
        try:
            scope["state"]["request_id"] = request_id  # type: ignore[index]
            scope["state"]["plato_user_id"] = user_id  # type: ignore[index]
        except TypeError:
            pass

        method = scope.get("method", "GET")
        path = scope.get("path", "")
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message.get("status", 500)
                # Inject the request id header so clients can grab it
                # off the response without parsing the body.
                msg_headers = list(message.get("headers") or [])
                msg_headers.append(
                    (_HEADER_REQUEST_ID.lower().encode("latin-1"), request_id.encode("latin-1"))
                )
                message = dict(message)
                message["headers"] = msg_headers
            await send(message)

        exc: BaseException | None = None
        try:
            await self._app(scope, receive, send_wrapper)
        except BaseException as e:  # noqa: BLE001 -- re-raised below
            exc = e
            raise
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            log_extra = {
                "method": method,
                "path": path,
                "status": status_code,
                "duration_ms": duration_ms,
            }
            if exc is not None:
                self._logger.error(
                    "request errored: %s %s",
                    method,
                    path,
                    extra=log_extra,
                    exc_info=(type(exc), exc, exc.__traceback__),
                )
            elif status_code >= 500:
                self._logger.error(
                    "5xx response: %s %s -> %s",
                    method,
                    path,
                    status_code,
                    extra=log_extra,
                )
            else:
                self._logger.info(
                    "%s %s -> %s",
                    method,
                    path,
                    status_code,
                    extra=log_extra,
                )

            user_id_var.reset(user_token)
            request_id_var.reset(rid_token)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler for anything not caught by FastAPI.

    Runs in Starlette's ``ServerErrorMiddleware``, which sits OUTSIDE
    our ``RequestLoggingMiddleware``. By the time we get here, that
    middleware's ``finally`` has already reset the request_id /
    user_id contextvars — so we recover them from ``request.state``,
    which the middleware also stashed before re-raising.

    Logs the failure with full structured context (request_id, user_id,
    run_id, exception class, traceback) and returns a stable error
    body the client can show the user. The user can then quote
    ``request_id`` back to support to look up the failure in logs.
    """
    state = request.state
    request_id = (
        getattr(state, "request_id", None)
        or request_id_var.get()
        or uuid.uuid4().hex
    )
    user_id = (
        getattr(state, "plato_user_id", None) or user_id_var.get() or "-"
    )
    run_id = run_id_var.get() or "-"

    logger = logging.getLogger("plato_dashboard.exception")
    logger.error(
        "unhandled exception: %s",
        exc.__class__.__name__,
        extra={
            "request_id": request_id,
            "user_id": user_id,
            "run_id": run_id,
            "exception_class": exc.__class__.__name__,
            "method": request.method,
            "path": request.url.path,
            "traceback": traceback.format_exc(),
        },
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content={"code": "internal_error", "request_id": request_id},
        headers={_HEADER_REQUEST_ID: request_id},
    )


__all__ = [
    "RequestLoggingMiddleware",
    "request_id_var",
    "run_id_var",
    "setup_logging",
    "unhandled_exception_handler",
    "user_id_var",
]
