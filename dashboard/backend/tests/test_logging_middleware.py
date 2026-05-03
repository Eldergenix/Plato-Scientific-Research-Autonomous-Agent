"""Structured-logging + request-id middleware contract.

These tests pin three things:

1. Every successful request gets a ``request_id`` propagated into the
   log record's ``extra``, into the response header, and into the
   request_id contextvar visible to handlers.
2. A 5xx response (raised inside a route as anything other than an
   ``HTTPException``) gets logged at ERROR with a structured payload
   *and* exposes the request_id back to the caller via the
   ``{code, request_id}`` envelope.
3. The unhandled-exception handler logs structured details, including
   request_id, user_id, run_id, and the exception class.

They use a one-off ``FastAPI`` app rather than the project ``client``
fixture so we can register intentionally-failing routes without
polluting the real router graph.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plato_dashboard.logging_config import (
    RequestLoggingMiddleware,
    request_id_var,
    setup_logging,
    unhandled_exception_handler,
    user_id_var,
)


def _build_app() -> FastAPI:
    """Minimal app with the middleware + a couple of trip-wire routes.

    We deliberately do NOT call ``create_app`` here — the goal is to
    isolate the middleware contract from the rest of the dashboard's
    routing surface. setup_logging is idempotent so running it again
    in-test is safe.
    """
    setup_logging(use_json=False)

    app = FastAPI()
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/ok")
    def _ok() -> dict:
        # Touch the contextvar so we can assert it propagates through
        # to handler scope.
        return {"request_id": request_id_var.get(), "user_id": user_id_var.get()}

    @app.get("/boom")
    def _boom() -> dict:
        # Anything that isn't an HTTPException — we want to see this
        # caught by ``unhandled_exception_handler`` and turned into a
        # 500 with a structured body.
        raise RuntimeError("kaboom")

    return app


@pytest.fixture
def client() -> TestClient:
    app = _build_app()
    return TestClient(app, raise_server_exceptions=False)


def test_request_id_propagated_in_log(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Successful request: id flows into log record + response header."""
    with caplog.at_level(logging.INFO, logger="plato_dashboard.request"):
        resp = client.get("/ok", headers={"X-Plato-User": "alice"})
    assert resp.status_code == 200

    rid = resp.headers.get("X-Request-Id")
    assert rid and len(rid) >= 8

    # The handler-scope contextvar value must match the header the
    # client received — that's the contract that lets a route hand
    # the id off to background tasks.
    body = resp.json()
    assert body["request_id"] == rid
    assert body["user_id"] == "alice"

    matching = [r for r in caplog.records if r.name == "plato_dashboard.request"]
    assert matching, "no request log record captured"
    record = matching[-1]
    assert getattr(record, "request_id", None) == rid
    assert getattr(record, "method", None) == "GET"
    assert getattr(record, "path", None) == "/ok"
    assert getattr(record, "status", None) == 200
    assert isinstance(getattr(record, "duration_ms", None), float)


def test_5xx_response_includes_request_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Unhandled exception: response carries request_id; log is ERROR."""
    with caplog.at_level(logging.ERROR):
        resp = client.get("/boom")
    assert resp.status_code == 500

    body = resp.json()
    assert body["code"] == "internal_error"
    assert body["request_id"]

    # The header echoes the same id so a client that only inspects
    # headers (e.g. a fetch wrapper) can still surface it.
    assert resp.headers.get("X-Request-Id") == body["request_id"]

    # Request-logger surfaced the failure with extras, AND the
    # exception handler emitted its own structured record.
    req_records = [
        r for r in caplog.records if r.name == "plato_dashboard.request"
    ]
    exc_records = [
        r for r in caplog.records if r.name == "plato_dashboard.exception"
    ]
    assert req_records, "request middleware did not log the failure"
    assert exc_records, "unhandled exception handler did not log"
    assert req_records[-1].levelno == logging.ERROR


def test_exception_handler_logs_structured(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Exception log record carries all the correlation fields."""
    with caplog.at_level(logging.ERROR, logger="plato_dashboard.exception"):
        resp = client.get(
            "/boom",
            headers={"X-Plato-User": "bob", "X-Plato-Run-Id": "run-xyz"},
        )
    assert resp.status_code == 500

    matching = [
        r for r in caplog.records if r.name == "plato_dashboard.exception"
    ]
    assert matching, "no exception log record captured"
    record = matching[-1]

    assert getattr(record, "exception_class", None) == "RuntimeError"
    assert getattr(record, "request_id", None) == resp.json()["request_id"]
    # user_id was bound via header
    assert getattr(record, "user_id", None) == "bob"
    # method + path land in extras for log shipping
    assert getattr(record, "method", None) == "GET"
    assert getattr(record, "path", None) == "/boom"
    # traceback present and string-shaped
    tb = getattr(record, "traceback", None)
    assert isinstance(tb, str) and "RuntimeError" in tb


def test_setup_logging_is_idempotent() -> None:
    """Calling setup_logging twice does not duplicate handlers."""
    setup_logging(use_json=False)
    before = len(logging.getLogger().handlers)
    setup_logging(use_json=False)
    after = len(logging.getLogger().handlers)
    assert before == after


def test_json_formatter_emits_parseable_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When JSON mode is on, records render to valid JSON.

    We don't assert on python-json-logger specifically — the stdlib
    fallback path also produces valid JSON, and either is acceptable.
    """
    setup_logging(use_json=True)
    root = logging.getLogger()

    handler = next(
        (h for h in root.handlers if getattr(h, "_plato_dashboard_root_handler", False)),
        None,
    )
    assert handler is not None, "dashboard handler not installed"
    formatter = handler.formatter
    assert formatter is not None

    record = logging.LogRecord(
        name="plato_dashboard.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="hello",
        args=None,
        exc_info=None,
    )
    # Filters run via Logger.handle, not Formatter.format, so stamp
    # the contextvar fields manually for the formatter's benefit.
    record.request_id = "rid-123"
    record.user_id = "u-1"
    record.run_id = "run-9"

    rendered = formatter.format(record)
    payload = json.loads(rendered)
    assert payload["message"] == "hello"
    assert payload["request_id"] == "rid-123"
    # Reset to plain text so the rest of the suite stays grep-friendly.
    setup_logging(use_json=False)
