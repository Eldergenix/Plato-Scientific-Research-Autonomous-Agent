"""Tests for ``GET/PUT /api/v1/user/preferences``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plato_dashboard.api.user_preferences import router as prefs_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(prefs_router)
    return TestClient(app)


# ---------------------------------------------------------------- GET


def test_get_returns_null_defaults_when_no_file(tmp_project_root: Path) -> None:
    resp = _client().get("/api/v1/user/preferences")
    assert resp.status_code == 200
    assert resp.json() == {"default_domain": None, "default_executor": None}


def test_get_reads_persisted_preferences(tmp_project_root: Path) -> None:
    user_dir = tmp_project_root / "users" / "alice"
    user_dir.mkdir(parents=True)
    (user_dir / "preferences.json").write_text(
        json.dumps({"default_domain": "biology", "default_executor": None})
    )

    resp = _client().get(
        "/api/v1/user/preferences",
        headers={"X-Plato-User": "alice"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"default_domain": "biology", "default_executor": None}


# ---------------------------------------------------------------- PUT


def test_put_persists_default_domain_and_get_reflects(
    tmp_project_root: Path,
) -> None:
    client = _client()

    put = client.put(
        "/api/v1/user/preferences",
        json={"default_domain": "biology"},
    )
    assert put.status_code == 200
    assert put.json() == {"default_domain": "biology", "default_executor": None}

    # Round-trip: GET reads the same value back.
    got = client.get("/api/v1/user/preferences").json()
    assert got["default_domain"] == "biology"

    # And it actually hit disk under the anon profile.
    saved = (tmp_project_root / "users" / "__anon__" / "preferences.json").read_text()
    assert json.loads(saved)["default_domain"] == "biology"


def test_put_rejects_unknown_domain(tmp_project_root: Path) -> None:
    resp = _client().put(
        "/api/v1/user/preferences",
        json={"default_domain": "definitely-not-real"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unknown_domain"


def test_put_rejects_empty_default_domain(tmp_project_root: Path) -> None:
    resp = _client().put(
        "/api/v1/user/preferences",
        json={"default_domain": ""},
    )
    # Pydantic returns 422 for validation failures on the body.
    assert resp.status_code == 422


# ---------------------------------------------------------------- tenancy


def test_per_user_preferences_are_isolated(tmp_project_root: Path) -> None:
    client = _client()

    # Alice prefers biology, Bob prefers astro.
    client.put(
        "/api/v1/user/preferences",
        headers={"X-Plato-User": "alice"},
        json={"default_domain": "biology"},
    )
    client.put(
        "/api/v1/user/preferences",
        headers={"X-Plato-User": "bob"},
        json={"default_domain": "astro"},
    )

    alice = client.get(
        "/api/v1/user/preferences", headers={"X-Plato-User": "alice"}
    ).json()
    bob = client.get(
        "/api/v1/user/preferences", headers={"X-Plato-User": "bob"}
    ).json()

    assert alice["default_domain"] == "biology"
    assert bob["default_domain"] == "astro"


def test_put_returns_401_when_required_mode_and_no_user_header(
    tmp_project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PLATO_AUTH", "enabled")

    resp = _client().put(
        "/api/v1/user/preferences",
        json={"default_domain": "astro"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "user_required"


def test_get_returns_401_when_required_mode_and_no_user_header(
    tmp_project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PLATO_AUTH", "enabled")

    resp = _client().get("/api/v1/user/preferences")
    assert resp.status_code == 401


def test_put_rejects_malformed_user_header_in_required_mode(
    tmp_project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PLATO_AUTH", "enabled")

    resp = _client().put(
        "/api/v1/user/preferences",
        headers={"X-Plato-User": "../etc/passwd"},
        json={"default_domain": "astro"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "user_invalid"
