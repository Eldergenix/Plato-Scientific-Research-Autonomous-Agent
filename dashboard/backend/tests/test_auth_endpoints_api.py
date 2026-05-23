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
from plato_dashboard.api.server import create_app
from plato_dashboard.auth import (
    AUTH_REQUIRED_ENV,
    BACKEND_PROXY_SECRET_ENV,
    PROXY_SECRET_HEADER,
    USER_HEADER,
)


@pytest.fixture
def auth_client(tmp_project_root) -> Iterator[TestClient]:  # noqa: ARG001 — fixture redirects settings paths
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
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


def test_login_sets_secure_cookie_when_request_is_https(auth_client: TestClient) -> None:
    resp = auth_client.post(
        "/api/v1/auth/login",
        json={"user_id": "alice"},
        headers={"x-forwarded-proto": "https"},
    )
    assert resp.status_code == 200
    assert "Secure" in resp.headers.get("set-cookie", "")


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


def test_logout_clears_secure_cookie_when_request_is_https(auth_client: TestClient) -> None:
    resp = auth_client.post(
        "/api/v1/auth/logout",
        headers={"x-forwarded-proto": "https"},
    )
    assert resp.status_code == 200
    assert "Secure" in resp.headers.get("set-cookie", "")


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


def test_proxy_secret_required_before_trusting_tenant_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_project_root  # noqa: ARG001
) -> None:
    monkeypatch.setenv(AUTH_REQUIRED_ENV, "1")
    monkeypatch.setenv(BACKEND_PROXY_SECRET_ENV, "shared-secret-32-characters-minimum")

    app = create_app()
    with TestClient(app) as c:
        spoofed = c.get("/api/v1/auth/me", headers={USER_HEADER: "alice"})
        assert spoofed.status_code == 401
        assert spoofed.json()["detail"]["code"] == "proxy_secret_required"

        c.cookies.set("plato_user", "alice")
        cookie_spoofed = c.get("/api/v1/auth/me")
        assert cookie_spoofed.status_code == 401
        assert cookie_spoofed.json()["detail"]["code"] == "proxy_secret_required"

        private_spoofed = c.get("/api/v1/projects", headers={USER_HEADER: "alice"})
        assert private_spoofed.status_code == 401
        assert private_spoofed.json()["detail"]["code"] == "proxy_secret_required"

        trusted = c.get(
            "/api/v1/auth/me",
            headers={
                USER_HEADER: "alice",
                PROXY_SECRET_HEADER: "shared-secret-32-characters-minimum",
            },
        )
        assert trusted.status_code == 200
        assert trusted.json()["user_id"] == "alice"


def test_proxy_secret_blocks_private_backend_routes_even_without_auth_required(
    monkeypatch: pytest.MonkeyPatch, tmp_project_root  # noqa: ARG001
) -> None:
    monkeypatch.delenv(AUTH_REQUIRED_ENV, raising=False)
    monkeypatch.setenv(BACKEND_PROXY_SECRET_ENV, "shared-secret-32-characters-minimum")

    app = create_app()
    with TestClient(app) as c:
        public = c.get("/api/v1/health")
        assert public.status_code == 200

        publication_feed = c.get("/api/v1/publications")
        assert publication_feed.status_code == 200

        publication_detail = c.get("/api/v1/publications/example")
        assert publication_detail.status_code == 404
        assert publication_detail.json()["detail"]["code"] == "publication_not_found"

        nested_publication_route = c.get("/api/v1/publications/example/comments")
        assert nested_publication_route.status_code == 401
        assert nested_publication_route.json()["detail"]["code"] == "proxy_secret_required"

        direct = c.get("/api/v1/projects", headers={USER_HEADER: "alice"})
        assert direct.status_code == 401
        assert direct.json()["detail"]["code"] == "proxy_secret_required"
        assert direct.headers["X-Content-Type-Options"] == "nosniff"
        assert direct.headers["X-Frame-Options"] == "DENY"
        assert direct.headers["Cross-Origin-Opener-Policy"] == "same-origin"

        trusted = c.get(
            "/api/v1/projects",
            headers={
                USER_HEADER: "alice",
                PROXY_SECRET_HEADER: "shared-secret-32-characters-minimum",
            },
        )
        assert trusted.status_code == 200


def test_short_proxy_secret_fails_closed_for_private_backend_routes(
    monkeypatch: pytest.MonkeyPatch, tmp_project_root  # noqa: ARG001
) -> None:
    monkeypatch.delenv(AUTH_REQUIRED_ENV, raising=False)
    monkeypatch.setenv(BACKEND_PROXY_SECRET_ENV, "short")

    app = create_app()
    with TestClient(app) as c:
        public = c.get("/api/v1/health")
        assert public.status_code == 200

        private = c.get(
            "/api/v1/projects",
            headers={
                USER_HEADER: "alice",
                PROXY_SECRET_HEADER: "short",
            },
        )
        assert private.status_code == 503
        assert private.json()["detail"]["code"] == "proxy_secret_misconfigured"
        assert "at least 32 characters" in private.json()["detail"]["message"]


def test_me_returns_null_when_neither_header_nor_cookie(auth_client: TestClient) -> None:
    resp = auth_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] is None
    assert isinstance(body["auth_required"], bool)


def test_me_auth_required_reflects_setting(
    monkeypatch: pytest.MonkeyPatch, tmp_project_root  # noqa: ARG001
) -> None:
    # Two env-var conventions exist in the codebase: ``auth.auth_required()``
    # reads ``PLATO_DASHBOARD_AUTH_REQUIRED=1`` and is the canonical helper
    # that auth_endpoints prefers when ``plato_dashboard.auth`` is importable;
    # ``Settings.is_auth_required`` reads ``PLATO_AUTH=enabled`` and is the
    # fallback. Set both so the test is correct regardless of which path
    # wins on a given worktree state.
    monkeypatch.setenv("PLATO_AUTH", "enabled")
    monkeypatch.setenv("PLATO_DASHBOARD_AUTH_REQUIRED", "1")

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
    with TestClient(app) as c:
        body = c.get("/api/v1/auth/me").json()
        assert body["auth_required"] is True
