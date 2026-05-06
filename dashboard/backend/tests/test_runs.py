"""Run-lifecycle smoke tests.

We never let the real subprocess executor spawn — the worker is mocked
out so tests stay sub-second. The friendly "Plato is not installed"
fallback path is covered by an integration suite, not these unit tests.
"""

from __future__ import annotations

import json

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

    async def _fake_start_run(project_id, stage, config, bus, project_dir=None):  # noqa: ARG001
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
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return _fake_start_run


def test_post_run_requires_llm_key(client, monkeypatch: pytest.MonkeyPatch) -> None:
    for env_var in (
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "PERPLEXITY_API_KEY",
    ):
        monkeypatch.delenv(env_var, raising=False)
    pid = _create_project(client)
    resp = client.post(
        f"/api/v1/projects/{pid}/stages/idea/run",
        json={"mode": "fast", "models": {}, "extra": {}},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "missing_llm_key"


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


def test_list_runs_and_events_history_replay_persisted_run(
    client, tmp_project_root
) -> None:
    pid = _create_project(client)
    run_id = "run_history123"
    run_dir = tmp_project_root / pid / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "project_id": pid,
                "stage": "results",
                "status": "succeeded",
                "started_at": "2026-05-06T04:26:49.319580+00:00",
                "finished_at": "2026-05-06T04:27:03.018564+00:00",
                "pid": 12345,
                "error": None,
                "token_input": 7,
                "token_output": 11,
            }
        ),
        encoding="utf-8",
    )
    events = [
        {
            "kind": "stage.started",
            "run_id": run_id,
            "project_id": pid,
            "stage": "results",
            "config": {"mode": "fast", "extra": {"executor": "sklearn_synthetic"}},
        },
        {
            "kind": "code.execute",
            "run_id": run_id,
            "project_id": pid,
            "stage": "results",
            "index": 0,
            "source": "print('hello')",
            "stdout": "hello\n",
            "stderr": "",
            "executor": "sklearn_synthetic",
        },
    ]
    (run_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(evt) for evt in events),
        encoding="utf-8",
    )

    runs = client.get(f"/api/v1/projects/{pid}/runs")
    assert runs.status_code == 200
    body = runs.json()
    assert body[0]["id"] == run_id
    assert body[0]["stage"] == "results"
    assert body[0]["status"] == "succeeded"
    assert body[0]["config"]["extra"]["executor"] == "sklearn_synthetic"

    status = client.get(f"/api/v1/projects/{pid}/runs/{run_id}")
    assert status.status_code == 200
    assert status.json()["id"] == run_id

    history = client.get(f"/api/v1/projects/{pid}/runs/{run_id}/events/history")
    assert history.status_code == 200
    assert history.json()[1]["kind"] == "code.execute"
    assert history.json()[1]["stdout"] == "hello\n"


def test_project_file_route_supports_head(client, tmp_project_root) -> None:
    pid = _create_project(client)
    paper_dir = tmp_project_root / pid / "paper"
    paper_dir.mkdir(parents=True)
    (paper_dir / "main.pdf").write_bytes(b"%PDF-1.5\n")

    resp = client.head(f"/api/v1/projects/{pid}/files/paper/main.pdf")

    assert resp.status_code == 200


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
