"""Tests for ``run_manager.resume_run`` + the ``/resume`` endpoint.

Mirrors the unit-style of ``test_runs.py``: the real ``start_run`` is
stubbed out so the supervisor never spawns a subprocess. The fake
``start_run`` mints a fresh queued ``Run`` and parks it in the in-memory
registry — enough for the resume code path to round-trip without
touching multiprocessing or the FS.
"""

from __future__ import annotations

import asyncio

import pytest

from plato_dashboard.domain.models import Run, utcnow


def _create_project(client, name: str = "Resume") -> str:
    return client.post("/api/v1/projects", json={"name": name}).json()["id"]


@pytest.fixture
def stub_start_run(monkeypatch: pytest.MonkeyPatch):
    """Stand-in ``start_run`` that pokes a queued Run into the registry.

    The ``run_manager.resume_run`` implementation calls ``start_run``
    after building its fresh config dict; we intercept that call so
    we can both (a) capture the args resume_run passed and (b) avoid
    the multiprocessing.Process spawn.
    """
    from plato_dashboard.worker import run_manager

    captured: dict = {}

    async def _fake_start_run(project_id, stage, config, bus, project_dir=None):
        captured["project_id"] = project_id
        captured["stage"] = stage
        captured["config"] = dict(config)
        captured["project_dir"] = project_dir
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
    # The api.server module imported start_run by name — patch that
    # binding too so the /run endpoint (used by the helper to seed a
    # prior run) routes through the stub.
    from plato_dashboard.api import server as server_mod
    monkeypatch.setattr(server_mod, "start_run", _fake_start_run)
    return captured


def _seed_prior_run(
    project_id: str,
    *,
    stage: str = "idea",
    mode: str = "fast",
    status: str = "failed",
    config: dict | None = None,
) -> Run:
    """Build a Run directly and stash it in ``_active_runs``.

    Bypasses the FastAPI launch path so we can pick the run's status
    deterministically (running, failed, cancelled) without driving the
    real supervisor. ``_write_status`` is also called so resume_run's
    on-disk fallback path has something to read after the in-memory
    entry is cleared between tests.
    """
    from plato_dashboard.worker import run_manager

    run = Run(
        project_id=project_id,
        stage=stage,
        mode=mode,
        config=config or {"mode": mode, "models": {}, "extra": {}},
        status=status,
        started_at=utcnow(),
    )
    run_manager._active_runs[run.id] = run
    return run


# --------------------------------------------------------------------- #
# resume_run direct (no FastAPI layer)
# --------------------------------------------------------------------- #
def test_resume_run_rejects_active_run(tmp_project_root) -> None:
    """A run with status="running" must not be resumable. resume_run
    raises ValueError; the FastAPI router maps that to 409."""
    from plato_dashboard.events.bus import EventBus
    from plato_dashboard.worker import run_manager

    project_id = "active_proj"
    prior = _seed_prior_run(project_id, status="running")

    async def _scenario() -> None:
        bus = EventBus()
        with pytest.raises(ValueError):
            await run_manager.resume_run(project_id, prior.id, bus)

    asyncio.run(_scenario())


# --------------------------------------------------------------------- #
# /resume endpoint
# --------------------------------------------------------------------- #
def test_resume_endpoint_404_when_run_missing(client, stub_start_run) -> None:
    pid = _create_project(client)
    resp = client.post(
        f"/api/v1/projects/{pid}/runs/run_does_not_exist/resume",
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "run_not_found"


def test_resume_endpoint_409_when_run_active(client, stub_start_run) -> None:
    pid = _create_project(client)
    prior = _seed_prior_run(pid, status="running")

    resp = client.post(
        f"/api/v1/projects/{pid}/runs/{prior.id}/resume",
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "run_not_resumable"


def test_resume_creates_new_run_id(client, stub_start_run) -> None:
    pid = _create_project(client)
    prior = _seed_prior_run(pid, status="failed")

    resp = client.post(
        f"/api/v1/projects/{pid}/runs/{prior.id}/resume",
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["id"].startswith("run_")
    assert body["id"] != prior.id


def test_resume_carries_resume_of_marker(client, stub_start_run) -> None:
    pid = _create_project(client)
    prior = _seed_prior_run(pid, status="failed")

    resp = client.post(
        f"/api/v1/projects/{pid}/runs/{prior.id}/resume",
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["config"]["resume_of"] == prior.id


def test_resume_inherits_prior_config(client, stub_start_run) -> None:
    pid = _create_project(client)
    prior_config = {
        "mode": "cmbagent",
        "models": {"llm": "gpt-4o"},
        "extra": {"foo": "bar"},
    }
    prior = _seed_prior_run(
        pid,
        stage="method",
        mode="cmbagent",
        status="cancelled",
        config=prior_config,
    )

    resp = client.post(
        f"/api/v1/projects/{pid}/runs/{prior.id}/resume",
    )
    assert resp.status_code == 202
    body = resp.json()
    # Stage + mode survive the round-trip.
    assert body["stage"] == "method"
    assert body["mode"] == "cmbagent"
    # Models dict (and any other extras the prior config carried) is
    # preserved verbatim alongside the new resume_of marker.
    assert body["config"]["models"] == {"llm": "gpt-4o"}
    assert body["config"]["extra"] == {"foo": "bar"}
    assert body["config"]["mode"] == "cmbagent"
    assert body["config"]["resume_of"] == prior.id
