"""Project CRUD smoke tests."""

from __future__ import annotations

from pathlib import Path


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


def test_delete_project_removes_from_disk(client, tmp_project_root: Path) -> None:
    created = client.post("/api/v1/projects", json={"name": "Gamma"}).json()
    pid = created["id"]
    project_dir = tmp_project_root / pid
    assert project_dir.exists(), "project_dir should exist after creation"

    resp = client.delete(f"/api/v1/projects/{pid}")
    assert resp.status_code == 204
    assert not project_dir.exists(), "project_dir should be gone after DELETE"
