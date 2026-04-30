"""Tests for /api/v1/user/executor_preferences."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app() -> FastAPI:
    from plato_dashboard.api.executor_preferences import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def client(tmp_project_root: Path):  # noqa: ARG001 — env setup via fixture
    app = _make_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def required_auth(monkeypatch):
    """Force required-mode for the duration of a test."""
    monkeypatch.setenv("PLATO_DASHBOARD_AUTH_REQUIRED", "1")
    yield
    monkeypatch.delenv("PLATO_DASHBOARD_AUTH_REQUIRED", raising=False)


def test_get_returns_null_when_unset(client) -> None:
    resp = client.get("/api/v1/user/executor_preferences")
    assert resp.status_code == 200
    assert resp.json() == {"default_executor": None}


def test_put_persists_a_valid_executor(client) -> None:
    resp = client.put(
        "/api/v1/user/executor_preferences",
        json={"default_executor": "local_jupyter"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"default_executor": "local_jupyter"}

    again = client.get("/api/v1/user/executor_preferences")
    assert again.json() == {"default_executor": "local_jupyter"}


def test_put_rejects_unknown_executor(client) -> None:
    resp = client.put(
        "/api/v1/user/executor_preferences",
        json={"default_executor": "totally_made_up"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unknown_executor"


def test_persistence_writes_legacy_path_without_user_header(
    client, tmp_project_root: Path
) -> None:
    client.put(
        "/api/v1/user/executor_preferences",
        json={"default_executor": "modal"},
    )
    legacy = tmp_project_root / "executor_prefs.json"
    assert legacy.is_file()
    assert json.loads(legacy.read_text()) == {"default_executor": "modal"}


def test_persistence_writes_per_user_path_with_header(
    client, tmp_project_root: Path
) -> None:
    client.put(
        "/api/v1/user/executor_preferences",
        json={"default_executor": "e2b"},
        headers={"X-Plato-User": "alice"},
    )
    user_path = (
        tmp_project_root.parent / "users" / "alice" / "executor_prefs.json"
    )
    assert user_path.is_file()
    assert json.loads(user_path.read_text()) == {"default_executor": "e2b"}

    # And reads round-trip with the same header.
    resp = client.get(
        "/api/v1/user/executor_preferences",
        headers={"X-Plato-User": "alice"},
    )
    assert resp.json() == {"default_executor": "e2b"}


def test_two_users_get_isolated_prefs(client) -> None:
    client.put(
        "/api/v1/user/executor_preferences",
        json={"default_executor": "modal"},
        headers={"X-Plato-User": "alice"},
    )
    client.put(
        "/api/v1/user/executor_preferences",
        json={"default_executor": "e2b"},
        headers={"X-Plato-User": "bob"},
    )
    a = client.get(
        "/api/v1/user/executor_preferences", headers={"X-Plato-User": "alice"}
    )
    b = client.get(
        "/api/v1/user/executor_preferences", headers={"X-Plato-User": "bob"}
    )
    assert a.json()["default_executor"] == "modal"
    assert b.json()["default_executor"] == "e2b"


def test_required_mode_rejects_missing_header_on_get(
    client, required_auth  # noqa: ARG001
) -> None:
    resp = client.get("/api/v1/user/executor_preferences")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "auth_required"


def test_required_mode_rejects_missing_header_on_put(
    client, required_auth  # noqa: ARG001
) -> None:
    resp = client.put(
        "/api/v1/user/executor_preferences",
        json={"default_executor": "cmbagent"},
    )
    assert resp.status_code == 401


def test_corrupt_prefs_file_falls_back_to_null(
    client, tmp_project_root: Path
) -> None:
    """A junk file shouldn't crash the page — return null and let the UI
    let the user re-pick a default, which will rewrite cleanly."""
    legacy = tmp_project_root / "executor_prefs.json"
    legacy.write_text("not valid json {{{")
    resp = client.get("/api/v1/user/executor_preferences")
    assert resp.status_code == 200
    assert resp.json() == {"default_executor": None}
