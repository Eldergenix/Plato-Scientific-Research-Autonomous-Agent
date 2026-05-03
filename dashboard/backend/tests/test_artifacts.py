"""Smoke tests for ``GET /projects/{pid}/runs/{run_id}/artifacts``.

The endpoint walks a real on-disk run directory, so we set up a
fixture project under the same per-test ``project_root`` the rest of
the suite uses. No worker process is involved — the dashboard treats
the run dir as opaque storage on read.
"""

from __future__ import annotations

import json
from pathlib import Path


def _create_project(client) -> str:
    return client.post("/api/v1/projects", json={"name": "Artifacts"}).json()["id"]


def _seed_run(project_root: Path, pid: str, run_id: str) -> Path:
    run_dir = project_root / pid / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "paper_v4_final.pdf").write_bytes(b"%PDF-1.4 stub")
    (run_dir / "idea.md").write_text("# idea\n")
    (run_dir / "manifest.json").write_text(json.dumps({"run_id": run_id}))
    (run_dir / "validation_report.json").write_text("{}")
    (run_dir / "evidence_matrix.jsonl").write_text("")
    (run_dir / "run.log").write_text("hello world\n")
    # Junk that must be filtered out:
    pycache = run_dir / "__pycache__"
    pycache.mkdir()
    (pycache / "x.pyc").write_bytes(b"")
    (run_dir / ".hidden").write_text("nope")
    (run_dir / "uv.lock").write_text("nope")
    return run_dir


def test_artifacts_lists_expected_files(client, tmp_project_root: Path) -> None:
    pid = _create_project(client)
    run_id = "run_abc123"
    _seed_run(tmp_project_root, pid, run_id)

    resp = client.get(f"/api/v1/projects/{pid}/runs/{run_id}/artifacts")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "items" in body
    paths = {item["path"] for item in body["items"]}

    # Real artefacts surface…
    assert "paper_v4_final.pdf" in paths
    assert "idea.md" in paths
    assert "manifest.json" in paths
    assert "validation_report.json" in paths
    assert "run.log" in paths

    # …junk is filtered.
    assert not any(p.startswith("__pycache__") for p in paths)
    assert not any(p.startswith(".") for p in paths)
    assert "uv.lock" not in paths


def test_artifacts_classifies_kind(client, tmp_project_root: Path) -> None:
    pid = _create_project(client)
    run_id = "run_kinds"
    _seed_run(tmp_project_root, pid, run_id)

    resp = client.get(f"/api/v1/projects/{pid}/runs/{run_id}/artifacts")
    assert resp.status_code == 200
    items = {item["path"]: item for item in resp.json()["items"]}

    assert items["paper_v4_final.pdf"]["kind"] == "paper_pdf"
    assert items["manifest.json"]["kind"] == "manifest"
    assert items["validation_report.json"]["kind"] == "report"
    assert items["evidence_matrix.jsonl"]["kind"] == "data"
    assert items["run.log"]["kind"] == "log"
    assert items["idea.md"]["kind"] == "other"

    # ISO-8601 mtime + non-negative size on every entry.
    for item in items.values():
        assert isinstance(item["size"], int) and item["size"] >= 0
        assert item["mtime"].endswith("Z") or "+" in item["mtime"]


def test_artifacts_404_when_run_missing(client, tmp_project_root: Path) -> None:
    pid = _create_project(client)
    resp = client.get(f"/api/v1/projects/{pid}/runs/run_missing/artifacts")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "run_not_found"


def test_artifacts_caps_at_100_alphabetical(
    client, tmp_project_root: Path
) -> None:
    pid = _create_project(client)
    run_id = "run_many"
    run_dir = tmp_project_root / pid / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    # Names are zero-padded so alphabetical == numerical.
    for i in range(150):
        (run_dir / f"plot_{i:03d}.png").write_bytes(b"\x89PNG")

    resp = client.get(f"/api/v1/projects/{pid}/runs/{run_id}/artifacts")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 100
    assert items[0]["path"] == "plot_000.png"
    assert items[-1]["path"] == "plot_099.png"
