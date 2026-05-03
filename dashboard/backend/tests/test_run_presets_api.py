"""Tests for /api/v1/run-presets — list / create / update / delete."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app() -> FastAPI:
    from plato_dashboard.api.run_presets import router

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
    monkeypatch.setenv("PLATO_DASHBOARD_AUTH_REQUIRED", "1")
    yield
    monkeypatch.delenv("PLATO_DASHBOARD_AUTH_REQUIRED", raising=False)


SAMPLE_CONFIG = {
    "idea_iters": 3,
    "max_revision_iters": 2,
    "journal": "NONE",
    "domain": "astro",
    "executor": "cmbagent",
}


def test_list_empty_by_default(client) -> None:
    resp = client.get("/api/v1/run-presets")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_then_get_roundtrip(client) -> None:
    create = client.post(
        "/api/v1/run-presets",
        json={"name": "astro lite", "config": SAMPLE_CONFIG},
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["name"] == "astro lite"
    assert body["config"] == SAMPLE_CONFIG
    assert body["id"]
    assert body["created_at"]

    listing = client.get("/api/v1/run-presets")
    assert listing.status_code == 200
    rows = listing.json()
    assert len(rows) == 1
    assert rows[0]["id"] == body["id"]


def test_create_rejects_invalid_name(client) -> None:
    resp = client.post(
        "/api/v1/run-presets",
        json={"name": "  ", "config": {}},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_name"


def test_create_rejects_duplicate_name(client) -> None:
    client.post(
        "/api/v1/run-presets",
        json={"name": "Daily", "config": {}},
    )
    dup = client.post(
        "/api/v1/run-presets",
        json={"name": "daily", "config": {}},  # case-insensitive
    )
    assert dup.status_code == 409
    assert dup.json()["detail"]["code"] == "duplicate_name"


def test_get_returns_single_preset(client) -> None:
    created = client.post(
        "/api/v1/run-presets",
        json={"name": "fetchme", "config": SAMPLE_CONFIG},
    ).json()
    pid = created["id"]

    resp = client.get(f"/api/v1/run-presets/{pid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == pid
    assert body["name"] == "fetchme"
    assert body["config"] == SAMPLE_CONFIG


def test_get_404_for_unknown_id(client) -> None:
    resp = client.get("/api/v1/run-presets/missing")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "preset_not_found"


def test_update_changes_config_and_name(client) -> None:
    created = client.post(
        "/api/v1/run-presets",
        json={"name": "old", "config": {"idea_iters": 1}},
    ).json()
    pid = created["id"]

    updated = client.put(
        f"/api/v1/run-presets/{pid}",
        json={"name": "new", "config": {"idea_iters": 9}},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["name"] == "new"
    assert body["config"] == {"idea_iters": 9}
    assert body["id"] == pid
    assert body["created_at"] == created["created_at"]


def test_update_404_for_unknown_id(client) -> None:
    resp = client.put(
        "/api/v1/run-presets/does-not-exist",
        json={"name": "anything"},
    )
    assert resp.status_code == 404


def test_delete_removes_from_list(client) -> None:
    created = client.post(
        "/api/v1/run-presets",
        json={"name": "tmp", "config": {}},
    ).json()
    pid = created["id"]

    delete = client.delete(f"/api/v1/run-presets/{pid}")
    assert delete.status_code == 204

    listing = client.get("/api/v1/run-presets")
    assert listing.json() == []


def test_delete_404_for_unknown_id(client) -> None:
    resp = client.delete("/api/v1/run-presets/nope")
    assert resp.status_code == 404


def test_persists_to_legacy_path_without_user_header(
    client, tmp_project_root: Path
) -> None:
    client.post(
        "/api/v1/run-presets",
        json={"name": "saved", "config": SAMPLE_CONFIG},
    )
    legacy = tmp_project_root / "run_presets.json"
    assert legacy.is_file()
    payload = json.loads(legacy.read_text())
    assert len(payload["presets"]) == 1
    assert payload["presets"][0]["name"] == "saved"


def test_two_users_get_isolated_presets(client) -> None:
    client.post(
        "/api/v1/run-presets",
        json={"name": "alice-preset", "config": {}},
        headers={"X-Plato-User": "alice"},
    )
    client.post(
        "/api/v1/run-presets",
        json={"name": "bob-preset", "config": {}},
        headers={"X-Plato-User": "bob"},
    )
    a = client.get(
        "/api/v1/run-presets", headers={"X-Plato-User": "alice"}
    )
    b = client.get(
        "/api/v1/run-presets", headers={"X-Plato-User": "bob"}
    )
    a_names = [p["name"] for p in a.json()]
    b_names = [p["name"] for p in b.json()]
    assert a_names == ["alice-preset"]
    assert b_names == ["bob-preset"]


def test_required_mode_rejects_missing_header(
    client, required_auth  # noqa: ARG001
) -> None:
    resp = client.get("/api/v1/run-presets")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "auth_required"


def test_corrupt_file_returns_empty_list(
    client, tmp_project_root: Path
) -> None:
    legacy = tmp_project_root / "run_presets.json"
    legacy.write_text("not valid json {{{")
    resp = client.get("/api/v1/run-presets")
    assert resp.status_code == 200
    assert resp.json() == []
