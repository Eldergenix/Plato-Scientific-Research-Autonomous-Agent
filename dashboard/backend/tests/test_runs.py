"""Run-lifecycle smoke tests.

We never let the real subprocess executor spawn — the worker is mocked
out so tests stay sub-second. The friendly "Plato is not installed"
fallback path is covered by an integration suite, not these unit tests.
"""

from __future__ import annotations

import pytest

from plato_dashboard.domain.models import Run, utcnow


def _create_project(client, name: str = "Runs") -> str:
    return client.post("/api/v1/projects", json={"name": name}).json()["id"]


@pytest.fixture
def stub_start_run(monkeypatch: pytest.MonkeyPatch):
    """Replace ``start_run`` with a tiny stub that returns a queued Run.

    The real implementation forks a multiprocessing.Process, which we do
    not want to do inside pytest. The stub also pokes the run into the
    in-memory registry so subsequent GET /runs/{id} calls work.
    """
    from plato_dashboard.worker import run_manager

    async def _fake_start_run(project_id, stage, config, bus):
        run = Run(
            project_id=project_id,
            stage=stage,
            mode=config.get("mode", "fast"),
            config=config,
            status="queued",
            started_at=utcnow(),
        )
        run_manager._active_runs[run.id] = run
        return run

    monkeypatch.setattr(run_manager, "start_run", _fake_start_run)
    # The server module imported start_run by name — patch that binding too.
    from plato_dashboard.api import server as server_mod
    monkeypatch.setattr(server_mod, "start_run", _fake_start_run)
    return _fake_start_run


def test_post_run_returns_202_with_run_id(client, stub_start_run) -> None:
    pid = _create_project(client)
    resp = client.post(
        f"/api/v1/projects/{pid}/stages/idea/run",
        json={"mode": "fast", "models": {}, "extra": {}},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["id"].startswith("run_")
    assert body["project_id"] == pid
    assert body["stage"] == "idea"


def test_get_run_returns_run_shape(client, stub_start_run) -> None:
    pid = _create_project(client)
    started = client.post(
        f"/api/v1/projects/{pid}/stages/idea/run",
        json={"mode": "fast", "models": {}, "extra": {}},
    ).json()

    got = client.get(f"/api/v1/projects/{pid}/runs/{started['id']}")
    assert got.status_code == 200
    body = got.json()
    assert body["id"] == started["id"]
    assert body["stage"] == "idea"
    assert body["status"] in ("queued", "running")


def test_demo_mode_blocks_results_with_stage_locked(
    monkeypatch: pytest.MonkeyPatch, tmp_project_root, stub_start_run
) -> None:
    """Demo mode rejects 'results' (and the rest of the locked list)."""
    monkeypatch.setenv("PLATO_DEMO_MODE", "enabled")

    from fastapi.testclient import TestClient
    from plato_dashboard.api.server import create_app

    app = create_app()
    with TestClient(app) as c:
        pid = c.post("/api/v1/projects", json={"name": "demo"}).json()["id"]
        resp = c.post(
            f"/api/v1/projects/{pid}/stages/results/run",
            json={"mode": "fast", "models": {}, "extra": {}},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "stage_locked"


def test_concurrency_cap_returns_429(
    client, monkeypatch: pytest.MonkeyPatch, stub_start_run
) -> None:
    """When count_active_runs() is over the cap, POST run → 429."""
    pid = _create_project(client)

    from plato_dashboard.api import server as server_mod
    monkeypatch.setattr(server_mod, "count_active_runs", lambda: 999)

    resp = client.post(
        f"/api/v1/projects/{pid}/stages/idea/run",
        json={"mode": "fast", "models": {}, "extra": {}},
    )
    assert resp.status_code == 429
    body = resp.json()
    assert body["detail"]["code"] == "too_many_concurrent_runs"
