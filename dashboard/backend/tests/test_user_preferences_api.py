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
    app.include_router(prefs_router, prefix="/api/v1")
    return TestClient(app)


# ---------------------------------------------------------------- GET


def test_get_returns_null_defaults_when_no_file(tmp_project_root: Path) -> None:
    resp = _client().get("/api/v1/user/preferences")
    assert resp.status_code == 200
    assert resp.json() == {
        "default_domain": None,
        "default_executor": None,
        "models_by_stage": {},
    }


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
    assert resp.json() == {
        "default_domain": "biology",
        "default_executor": None,
        "models_by_stage": {},
    }


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
    assert put.json() == {
        "default_domain": "biology",
        "default_executor": None,
        "models_by_stage": {},
    }

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


def test_lab_preferences_are_isolated_from_personal_user(
    tmp_project_root: Path,
) -> None:
    client = _client()

    client.put(
        "/api/v1/user/preferences",
        headers={"X-Plato-User": "lab_org_alpha"},
        json={"default_domain": "biology", "models_by_stage": {"paper": "gpt-5"}},
    )
    client.put(
        "/api/v1/user/preferences",
        headers={"X-Plato-User": "user_scientist_a"},
        json={"default_domain": "astro", "models_by_stage": {"paper": "claude"}},
    )

    lab = client.get(
        "/api/v1/user/preferences", headers={"X-Plato-User": "lab_org_alpha"}
    ).json()
    personal = client.get(
        "/api/v1/user/preferences", headers={"X-Plato-User": "user_scientist_a"}
    ).json()

    assert lab["default_domain"] == "biology"
    assert lab["models_by_stage"] == {"paper": "gpt-5"}
    assert personal["default_domain"] == "astro"
    assert personal["models_by_stage"] == {"paper": "claude"}

    assert (
        tmp_project_root / "users" / "lab_org_alpha" / "preferences.json"
    ).is_file()
    assert (
        tmp_project_root / "users" / "user_scientist_a" / "preferences.json"
    ).is_file()


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


def test_get_returns_401_when_dashboard_auth_required_and_no_user_header(
    tmp_project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PLATO_AUTH", raising=False)
    monkeypatch.setenv("PLATO_DASHBOARD_AUTH_REQUIRED", "1")

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


# ---------------------------------------------------------------- models_by_stage


def test_put_models_by_stage_round_trips_through_get(
    tmp_project_root: Path,
) -> None:
    client = _client()

    put = client.put(
        "/api/v1/user/preferences",
        json={"models_by_stage": {"idea": "gpt-5"}},
    )
    assert put.status_code == 200, put.text
    assert put.json()["models_by_stage"] == {"idea": "gpt-5"}

    got = client.get("/api/v1/user/preferences").json()
    assert got["models_by_stage"] == {"idea": "gpt-5"}

    saved = json.loads(
        (tmp_project_root / "users" / "__anon__" / "preferences.json").read_text()
    )
    assert saved["models_by_stage"] == {"idea": "gpt-5"}


def test_put_models_by_stage_merges_with_existing(
    tmp_project_root: Path,
) -> None:
    client = _client()

    client.put(
        "/api/v1/user/preferences",
        json={"models_by_stage": {"idea": "gpt-5"}},
    )
    second = client.put(
        "/api/v1/user/preferences",
        json={"models_by_stage": {"results": "claude-4.1-opus"}},
    )
    assert second.status_code == 200
    assert second.json()["models_by_stage"] == {
        "idea": "gpt-5",
        "results": "claude-4.1-opus",
    }


def test_put_rejects_unknown_stage_id(tmp_project_root: Path) -> None:
    resp = _client().put(
        "/api/v1/user/preferences",
        json={"models_by_stage": {"not-a-stage": "gpt-5"}},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unknown_stage"


def test_put_rejects_empty_model_id(tmp_project_root: Path) -> None:
    resp = _client().put(
        "/api/v1/user/preferences",
        json={"models_by_stage": {"idea": ""}},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_model_id"


def test_put_rejects_model_id_too_long(tmp_project_root: Path) -> None:
    resp = _client().put(
        "/api/v1/user/preferences",
        json={"models_by_stage": {"idea": "x" * 201}},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "model_id_too_long"
