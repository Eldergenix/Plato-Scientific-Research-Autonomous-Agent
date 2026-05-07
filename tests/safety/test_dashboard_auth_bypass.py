"""Adversarial header attacks against the dashboard's ``X-Plato-User`` auth.

The dashboard delegates identity to an upstream proxy (Cloudflare Access,
oauth2-proxy, ...) which sets the ``X-Plato-User`` header. We never sign
the header ourselves — the trust assumption is that the proxy is
authenticated and the dashboard is not bound to a public interface.

Within that posture, the dashboard still needs to refuse a few obvious
bypass shapes:

1. Empty / whitespace-only header values must not impersonate a user.
2. CRLF injection in the header value must not let the attacker append
   forged headers downstream.
3. In ``PLATO_DASHBOARD_AUTH_REQUIRED=1`` mode, a missing header must
   produce a 401, not silently fall through to single-user mode.

Stream C may or may not be merged when this test runs — gate everything
behind ``importorskip``.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

# Skip the entire module if the dashboard auth shim isn't available yet.
auth = pytest.importorskip("plato_dashboard.auth")


def _make_request(headers: dict[str, str] | None = None) -> Request:
    """Build a minimal ASGI ``Request`` with ``headers``.

    Header values must already be ASCII-encoded as bytes per ASGI.
    """
    raw_headers: list[tuple[bytes, bytes]] = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": raw_headers,
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# Empty / whitespace headers
# ---------------------------------------------------------------------------


def test_missing_header_is_unauthenticated():
    req = _make_request()
    assert auth.extract_user_id(req) is None


def test_empty_header_is_unauthenticated():
    req = _make_request({"X-Plato-User": ""})
    assert auth.extract_user_id(req) is None


@pytest.mark.parametrize(
    "value",
    [
        " ",
        "\t",
        "  \t  ",
        "\n",
        "\r\n",
        " ",  # non-breaking space — Python ``str.strip`` handles this
    ],
)
def test_whitespace_only_header_is_unauthenticated(value: str):
    req = _make_request({"X-Plato-User": value})
    assert auth.extract_user_id(req) is None


# ---------------------------------------------------------------------------
# CRLF / header-injection
# ---------------------------------------------------------------------------


def test_crlf_in_header_does_not_smuggle_a_second_header():
    """ASGI / Starlette must not interpret CRLF inside a value as a new header.

    A naive implementation could let an attacker pass
    ``"alice\\r\\nX-Forwarded-For: bob"`` and have ``X-Forwarded-For``
    show up as a second logical header. The dashboard rejects the poisoned
    identity outright and Starlette does not expose a forged second header.
    """
    poisoned = "alice\nX-Forwarded-For: bob"
    req = _make_request({"X-Plato-User": poisoned})

    assert auth.extract_user_id(req) is None
    assert req.headers.get("X-Forwarded-For") is None


def test_crlf_in_header_value_is_rejected_after_strip():
    """A value that still contains CRLF after strip is not a safe user id."""
    poisoned = "  alice\r\nX-Forwarded-For: bob  "
    req = _make_request({"X-Plato-User": poisoned})
    assert auth.extract_user_id(req) is None


# ---------------------------------------------------------------------------
# require_user_id — required-mode hard gate
# ---------------------------------------------------------------------------


def test_required_mode_missing_header_raises_401(monkeypatch):
    monkeypatch.setenv(auth.AUTH_REQUIRED_ENV, "1")

    req = _make_request()
    with pytest.raises(Exception) as excinfo:
        auth.require_user_id(req)

    # We don't depend on the exact import path of HTTPException — match
    # by attribute, since both starlette and fastapi expose status_code.
    exc = excinfo.value
    assert getattr(exc, "status_code", None) == 401


def test_required_mode_empty_header_raises_401(monkeypatch):
    monkeypatch.setenv(auth.AUTH_REQUIRED_ENV, "1")

    req = _make_request({"X-Plato-User": ""})
    with pytest.raises(Exception) as excinfo:
        auth.require_user_id(req)
    assert getattr(excinfo.value, "status_code", None) == 401


def test_required_mode_whitespace_header_raises_401(monkeypatch):
    monkeypatch.setenv(auth.AUTH_REQUIRED_ENV, "1")

    req = _make_request({"X-Plato-User": "   "})
    with pytest.raises(Exception) as excinfo:
        auth.require_user_id(req)
    assert getattr(excinfo.value, "status_code", None) == 401


def test_required_mode_valid_header_returns_user_id(monkeypatch):
    monkeypatch.setenv(auth.AUTH_REQUIRED_ENV, "1")

    req = _make_request({"X-Plato-User": "alice"})
    assert auth.require_user_id(req) == "alice"


# ---------------------------------------------------------------------------
# Single-user fallback (auth not required)
# ---------------------------------------------------------------------------


def test_optional_mode_missing_header_falls_back_to_empty_string(monkeypatch):
    monkeypatch.delenv(auth.AUTH_REQUIRED_ENV, raising=False)

    req = _make_request()
    # In optional mode the contract is "return ''" — routes branch on truthiness.
    assert auth.require_user_id(req) == ""


def test_optional_mode_empty_header_falls_back_to_empty_string(monkeypatch):
    monkeypatch.delenv(auth.AUTH_REQUIRED_ENV, raising=False)

    req = _make_request({"X-Plato-User": ""})
    assert auth.require_user_id(req) == ""


def test_optional_mode_present_header_is_honored(monkeypatch):
    """Even when auth isn't required, a supplied header still scopes the user."""
    monkeypatch.delenv(auth.AUTH_REQUIRED_ENV, raising=False)

    req = _make_request({"X-Plato-User": "bob"})
    assert auth.require_user_id(req) == "bob"


# ---------------------------------------------------------------------------
# Header/cookie identity is explicit — no fallback to query string or
# misleading cookie names
# ---------------------------------------------------------------------------


def test_query_string_user_param_is_ignored():
    """``?user=alice`` must not set the auth principal — only the header does."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"user=alice",
        "headers": [],
    }
    req = Request(scope)
    assert auth.extract_user_id(req) is None


def test_header_named_cookie_is_ignored():
    """A cookie named ``X-Plato-User`` must not impersonate the header."""
    req = _make_request({"Cookie": "X-Plato-User=alice"})
    assert auth.extract_user_id(req) is None


def test_dashboard_user_cookie_is_honored():
    """The dashboard login flow stores the tenant id in ``plato_user``."""
    req = _make_request({"Cookie": "plato_user=alice"})
    assert auth.extract_user_id(req) == "alice"


def test_unsafe_dashboard_user_cookie_is_rejected():
    req = _make_request({"Cookie": "plato_user=../alice"})
    assert auth.extract_user_id(req) is None
