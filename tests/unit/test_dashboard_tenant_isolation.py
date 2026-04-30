"""Phase 5 — multi-tenant isolation in the dashboard API.

End-to-end-ish: drive the FastAPI app via ``TestClient``, plant manifest
files under each tenant's namespaced project directory, then prove that
user A cannot fetch user B's run when required-mode is on.

We bypass the Plato runtime — the tests stub ``start_run`` with the
queued-run fixture from the dashboard suite — and write the
``runs/<run_id>/manifest.json`` files by hand to exercise just the
tenant-boundary logic.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Make the dashboard backend src importable.
_DASHBOARD_SRC = (
    Path(__file__).resolve().parents[2] / "dashboard" / "backend" / "src"
)
if str(_DASHBOARD_SRC) not in sys.path:
    sys.path.insert(0, str(_DASHBOARD_SRC))


def _write_manifest(project_dir: Path, run_id: str, user_id: str | None) -> Path:
    """Drop a minimal-but-valid ``runs/<run_id>/manifest.json``."""
    runs_dir = project_dir / "runs" / run_id
    runs_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "workflow": "test_workflow",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "domain": "astro",
        "git_sha": "",
        "project_sha": "",
        "user_id": user_id,
        "models": {},
        "prompt_hashes": {},
        "seeds": {},
        "source_ids": [],
        "cost_usd": 0.0,
        "tokens_in": 0,
        "tokens_out": 0,
        "error": None,
        "extra": {},
        "ended_at": None,
    }
    target = runs_dir / "manifest.json"
    target.write_text(json.dumps(payload))
    return target


@pytest.fixture
def required_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Enable PLATO_DASHBOARD_AUTH_REQUIRED + redirect project_root."""
    proj_root = tmp_path / "projects"
    proj_root.mkdir(parents=True, exist_ok=True)
    keys_path = tmp_path / "keys.json"
    monkeypatch.setenv("PLATO_DASHBOARD_AUTH_REQUIRED", "1")
    monkeypatch.setenv("PLATO_PROJECT_ROOT", str(proj_root))
    monkeypatch.setenv("PLATO_KEYS_PATH", str(keys_path))
    monkeypatch.delenv("PLATO_DEMO_MODE", raising=False)
    return tmp_path


@pytest.fixture
def app_client(required_mode: Path):
    """Fresh FastAPI TestClient bound to a clean app instance."""
    from fastapi.testclient import TestClient

    # Reset stale module-level run state between tests.
    from plato_dashboard.worker import run_manager
    run_manager._active_runs.clear()
    run_manager._run_tasks.clear()
    run_manager._subprocesses.clear()

    from plato_dashboard.events import bus as bus_mod
    bus_mod._bus = None

    from plato_dashboard.api.server import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c

    run_manager._active_runs.clear()
    run_manager._run_tasks.clear()
    run_manager._subprocesses.clear()
    bus_mod._bus = None


def _user_root(plato_home: Path, user_id: str) -> Path:
    """Mirrors ``_resolve_project_root`` in the server."""
    return plato_home / "users" / user_id


def test_required_mode_rejects_missing_header(app_client) -> None:
    """No header at all → 401 from any tenant-scoped endpoint."""
    resp = app_client.get("/api/v1/projects")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "auth_required"


def test_required_mode_creates_per_user_namespaces(
    app_client, required_mode: Path
) -> None:
    """Two users → two on-disk roots under ``users/<id>/``."""
    plato_home = required_mode / "projects"  # parent for users/<id>/
    a_proj = app_client.post(
        "/api/v1/projects",
        json={"name": "alice's"},
        headers={"X-Plato-User": "alice"},
    ).json()
    b_proj = app_client.post(
        "/api/v1/projects",
        json={"name": "bob's"},
        headers={"X-Plato-User": "bob"},
    ).json()

    # Each user lands under users/<id>/<pid>/.
    assert (_user_root(plato_home.parent, "alice") / a_proj["id"]).exists()
    assert (_user_root(plato_home.parent, "bob") / b_proj["id"]).exists()
    # Cross-namespace pollution check.
    assert not (_user_root(plato_home.parent, "alice") / b_proj["id"]).exists()


def test_user_b_cannot_fetch_user_a_run(
    app_client, required_mode: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cross-tenant fetch must fail (4xx, never 2xx)."""
    plato_home = required_mode / "projects"

    # Create alice's project; plant a manifest with user_id='alice'.
    a_resp = app_client.post(
        "/api/v1/projects",
        json={"name": "alice"},
        headers={"X-Plato-User": "alice"},
    )
    assert a_resp.status_code == 201
    pid_a = a_resp.json()["id"]
    a_project_dir = _user_root(plato_home.parent, "alice") / pid_a
    _write_manifest(a_project_dir, run_id="r_alice_1", user_id="alice")

    # Pre-load the run into the in-memory registry so the route doesn't
    # 404 before the tenant check fires. We can't easily exercise the
    # subprocess-spawning path in a unit test, so reach in directly.
    from plato_dashboard.domain.models import Run, utcnow
    from plato_dashboard.worker import run_manager
    run_manager._active_runs["r_alice_1"] = Run(
        id="r_alice_1",
        project_id=pid_a,
        stage="idea",
        mode="fast",
        config={},
        status="running",
        started_at=utcnow(),
    )

    # Alice can fetch her own run.
    self_fetch = app_client.get(
        f"/api/v1/projects/{pid_a}/runs/r_alice_1",
        headers={"X-Plato-User": "alice"},
    )
    assert self_fetch.status_code == 200, self_fetch.text

    # Bob, with a different X-Plato-User, gets blocked. The route would
    # have to read alice's project_dir — we pass alice's pid in the
    # path because that's the URL bob would have to guess; the tenant
    # check fires off the manifest's user_id.
    cross_fetch = app_client.get(
        f"/api/v1/projects/{pid_a}/runs/r_alice_1",
        headers={"X-Plato-User": "bob"},
    )
    # Bob's namespace doesn't have alice's project; the store-level
    # 401 / 404 / 403 is fine — what matters is that bob never sees
    # the run payload.
    assert cross_fetch.status_code != 200, cross_fetch.text
    assert "r_alice_1" not in cross_fetch.text


def test_legacy_unauth_path_unaffected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without PLATO_DASHBOARD_AUTH_REQUIRED, the legacy flow still works."""
    proj_root = tmp_path / "projects"
    proj_root.mkdir(parents=True, exist_ok=True)
    keys_path = tmp_path / "keys.json"
    monkeypatch.setenv("PLATO_PROJECT_ROOT", str(proj_root))
    monkeypatch.setenv("PLATO_KEYS_PATH", str(keys_path))
    monkeypatch.delenv("PLATO_DASHBOARD_AUTH_REQUIRED", raising=False)
    monkeypatch.delenv("PLATO_DEMO_MODE", raising=False)

    from fastapi.testclient import TestClient
    from plato_dashboard.worker import run_manager
    run_manager._active_runs.clear()
    run_manager._run_tasks.clear()
    run_manager._subprocesses.clear()

    from plato_dashboard.api.server import create_app

    app = create_app()
    with TestClient(app) as c:
        # No header — legacy mode should serve the project list.
        resp = c.get("/api/v1/projects")
        assert resp.status_code == 200
        assert resp.json() == []
        # Create a project, no header at all.
        created = c.post("/api/v1/projects", json={"name": "legacy"})
        assert created.status_code == 201
        # Project landed at the legacy un-namespaced root.
        assert (proj_root / created.json()["id"]).exists()


def test_required_mode_run_self_access_works(
    app_client, required_mode: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sanity: alice fetching alice's own run still returns 200."""
    plato_home = required_mode / "projects"
    a_resp = app_client.post(
        "/api/v1/projects",
        json={"name": "alice"},
        headers={"X-Plato-User": "alice"},
    )
    pid = a_resp.json()["id"]
    project_dir = _user_root(plato_home.parent, "alice") / pid
    _write_manifest(project_dir, run_id="r_alice_2", user_id="alice")

    from plato_dashboard.domain.models import Run, utcnow
    from plato_dashboard.worker import run_manager
    run_manager._active_runs["r_alice_2"] = Run(
        id="r_alice_2",
        project_id=pid,
        stage="idea",
        mode="fast",
        config={},
        status="running",
        started_at=utcnow(),
    )

    resp = app_client.get(
        f"/api/v1/projects/{pid}/runs/r_alice_2",
        headers={"X-Plato-User": "alice"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == "r_alice_2"
