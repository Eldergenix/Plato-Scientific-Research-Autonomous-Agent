"""Project CRUD smoke tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from plato_dashboard.api.server import create_app


def test_create_project_returns_201_with_prj_prefix(client) -> None:
    resp = client.post("/api/v1/projects", json={"name": "Test project"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"].startswith("prj_")
    assert body["name"] == "Test project"
    # All seven canonical stages should be initialised.
    assert sorted(body["stages"].keys()) == sorted(
        ["data", "idea", "literature", "method", "results", "paper", "referee"]
    )


def test_create_project_without_description_writes_default_data_file(
    client, tmp_project_root: Path
) -> None:
    created = client.post("/api/v1/projects", json={"name": "Empty project"}).json()
    data_file = tmp_project_root / created["id"] / "input_files" / "data_description.md"

    assert data_file.exists()
    assert "No dataset has been uploaded yet" in data_file.read_text()
    assert created["stages"]["data"]["status"] == "empty"


def test_list_projects_returns_created_one(client) -> None:
    created = client.post("/api/v1/projects", json={"name": "Alpha"}).json()
    listed = client.get("/api/v1/projects").json()
    ids = [p["id"] for p in listed]
    assert created["id"] in ids


def test_get_single_project_shape_and_404(client) -> None:
    created = client.post("/api/v1/projects", json={"name": "Beta"}).json()

    got = client.get(f"/api/v1/projects/{created['id']}")
    assert got.status_code == 200
    body = got.json()
    assert body["id"] == created["id"]
    assert body["name"] == "Beta"
    assert "stages" in body and "data" in body["stages"]

    missing = client.get("/api/v1/projects/prj_does_not_exist")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "project_not_found"


def test_read_stage_missing_project_returns_404(client) -> None:
    resp = client.get("/api/v1/projects/prj_does_not_exist/state/idea")

    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "project_not_found"


def test_legacy_auth_env_requires_project_identity(
    monkeypatch, tmp_project_root: Path  # noqa: ARG001
) -> None:
    monkeypatch.delenv("PLATO_DASHBOARD_AUTH_REQUIRED", raising=False)
    monkeypatch.setenv("PLATO_AUTH", "enabled")

    with TestClient(create_app()) as authed:
        missing = authed.get("/api/v1/projects")
        assert missing.status_code == 401
        assert missing.json()["detail"]["code"] == "auth_required"

        created = authed.post(
            "/api/v1/projects",
            json={"name": "Legacy auth tenant"},
            headers={"X-Plato-User": "alice"},
        )
        assert created.status_code == 201
        assert created.json()["user_id"] == "alice"


def test_delete_project_removes_from_disk(client, tmp_project_root: Path) -> None:
    created = client.post("/api/v1/projects", json={"name": "Gamma"}).json()
    pid = created["id"]
    project_dir = tmp_project_root / pid
    assert project_dir.exists(), "project_dir should exist after creation"

    resp = client.delete(f"/api/v1/projects/{pid}")
    assert resp.status_code == 204
    assert not project_dir.exists(), "project_dir should be gone after DELETE"
