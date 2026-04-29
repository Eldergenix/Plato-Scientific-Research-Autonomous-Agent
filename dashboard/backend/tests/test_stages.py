"""Stage read/write smoke tests."""

from __future__ import annotations

from pathlib import Path


def _create_project(client, name: str = "Stage tests") -> str:
    return client.post("/api/v1/projects", json={"name": name}).json()["id"]


def test_put_writes_stage_and_get_reads_it_back(
    client, tmp_project_root: Path
) -> None:
    pid = _create_project(client)
    md = "# Idea\n\nThis is the idea body."

    put = client.put(f"/api/v1/projects/{pid}/state/idea", json={"markdown": md})
    assert put.status_code == 200
    assert put.json()["stage"] == "idea"
    assert put.json()["markdown"] == md

    got = client.get(f"/api/v1/projects/{pid}/state/idea")
    assert got.status_code == 200
    body = got.json()
    assert body["markdown"] == md
    # On disk where Plato expects it
    assert (tmp_project_root / pid / "input_files" / "idea.md").read_text() == md


def test_writing_stage_marks_status_done_and_origin_edited(client) -> None:
    pid = _create_project(client)
    client.put(f"/api/v1/projects/{pid}/state/idea", json={"markdown": "x"})

    project = client.get(f"/api/v1/projects/{pid}").json()
    idea_stage = project["stages"]["idea"]
    assert idea_stage["status"] == "done"
    assert idea_stage["origin"] == "edited"


def test_writing_upstream_marks_downstream_stale_and_snapshots(
    client, tmp_project_root: Path
) -> None:
    pid = _create_project(client)

    # Mark a downstream stage 'done' first by writing into it.
    client.put(f"/api/v1/projects/{pid}/state/method", json={"markdown": "method v1"})
    project = client.get(f"/api/v1/projects/{pid}").json()
    assert project["stages"]["method"]["status"] == "done"

    # Now write to an upstream stage — method should flip to 'stale'.
    client.put(f"/api/v1/projects/{pid}/state/idea", json={"markdown": "idea v1"})
    project = client.get(f"/api/v1/projects/{pid}").json()
    assert project["stages"]["method"]["status"] == "stale"

    # Re-writing idea (which already exists on disk) should snapshot the prior
    # version into .history/.
    client.put(f"/api/v1/projects/{pid}/state/idea", json={"markdown": "idea v2"})
    history_dir = tmp_project_root / pid / "input_files" / ".history"
    assert history_dir.exists()
    snapshots = list(history_dir.glob("idea_*.md"))
    assert len(snapshots) >= 1, "expected at least one .history snapshot for idea"
