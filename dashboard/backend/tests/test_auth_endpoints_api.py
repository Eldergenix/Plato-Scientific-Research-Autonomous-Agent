"""Tests for the F10 auth router (login / logout / me).

The integration commit will mount this router on the main app. Until
that lands, these tests build a small FastAPI app that includes only the
auth router — the unit-level behaviour (cookie set/clear, header vs
cookie precedence, auth_required flag) does not depend on any other
endpoint.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plato_dashboard.api.auth_endpoints import router as auth_router


@pytest.fixture
def auth_client(tmp_project_root) -> Iterator[TestClient]:  # noqa: ARG001 — fixture redirects settings paths
    app = FastAPI()
    app.include_router(auth_router)
    with TestClient(app) as c:
        yield c


def test_login_sets_cookie_and_echoes_user_id(auth_client: TestClient) -> None:
    resp = auth_client.post("/api/v1/auth/login", json={"user_id": "alice"})
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"user_id": "alice", "ok": True}

    # Set-Cookie should carry plato_user with the right flags.
    set_cookie = resp.headers.get("set-cookie", "")
    assert "plato_user=alice" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "samesite=lax" in set_cookie.lower()
    assert "Path=/" in set_cookie


def test_login_strips_whitespace(auth_client: TestClient) -> None:
    resp = auth_client.post("/api/v1/auth/login", json={"user_id": "  bob  "})
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "bob"
    assert "plato_user=bob" in resp.headers.get("set-cookie", "")


def test_login_rejects_empty_user_id(auth_client: TestClient) -> None:
    for bad in [{"user_id": ""}, {"user_id": "   "}, {"user_id": None}, {}]:
        resp = auth_client.post("/api/v1/auth/login", json=bad)
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_user_id"


def test_logout_clears_cookie(auth_client: TestClient) -> None:
    # Sign in first so the test client carries the cookie.
    auth_client.post("/api/v1/auth/login", json={"user_id": "alice"})
    assert auth_client.cookies.get("plato_user") == "alice"

    resp = auth_client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    # Set-Cookie on logout should clear plato_user (Max-Age=0 or expired).
    set_cookie = resp.headers.get("set-cookie", "")
    assert "plato_user=" in set_cookie
    assert ("Max-Age=0" in set_cookie) or ("expires=" in set_cookie.lower())


def test_me_returns_user_from_cookie(auth_client: TestClient) -> None:
    auth_client.post("/api/v1/auth/login", json={"user_id": "alice"})
    resp = auth_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "alice"
    assert "auth_required" in body
    assert isinstance(body["auth_required"], bool)


def test_me_returns_user_from_header_alone(auth_client: TestClient) -> None:
    # Fresh client — no cookie yet — but header is set.
    resp = auth_client.get("/api/v1/auth/me", headers={"X-Plato-User": "bob"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "bob"


def test_me_header_overrides_cookie(auth_client: TestClient) -> None:
    auth_client.post("/api/v1/auth/login", json={"user_id": "alice"})
    resp = auth_client.get("/api/v1/auth/me", headers={"X-Plato-User": "carol"})
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "carol"


def test_me_returns_null_when_neither_header_nor_cookie(auth_client: TestClient) -> None:
    resp = auth_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] is None
    assert isinstance(body["auth_required"], bool)


def test_me_auth_required_reflects_setting(
    monkeypatch: pytest.MonkeyPatch, tmp_project_root  # noqa: ARG001
) -> None:
    monkeypatch.setenv("PLATO_AUTH", "enabled")

    app = FastAPI()
    app.include_router(auth_router)
    with TestClient(app) as c:
        body = c.get("/api/v1/auth/me").json()
        assert body["auth_required"] is True
