"""Iter-23 — tests for the /api/v1/projects/{pid}/idea_history endpoint.

The endpoint walks ``<project_root>/<pid>/runs/<run_id>/manifest.json``,
filters to ``workflow`` strings starting with ``get_idea``, and returns a
sorted list. These tests pin the contract via fabricated manifest files
on disk so the suite runs without hitting any LLM / kernel.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app() -> FastAPI:
    """Mount just the idea_history router for focused testing."""
    from plato_dashboard.api.idea_history import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def client(tmp_project_root: Path):  # noqa: ARG001 — fixture sets project_root
    app = _make_app()
    with TestClient(app) as c:
        yield c


def _write_manifest(
    project_root: Path,
    pid: str,
    run_id: str,
    *,
    workflow: str,
    started_offset_minutes: int = 0,
    duration_minutes: float | None = None,
    status: str = "success",
    models: dict[str, str] | None = None,
    user_id: str | None = None,
) -> Path:
    """Write a manifest.json for a fabricated run under ``<root>/<pid>/runs/<id>/``."""
    run_dir = project_root / pid / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc) - timedelta(minutes=started_offset_minutes)
    payload: dict[str, Any] = {
        "run_id": run_id,
        "workflow": workflow,
        "started_at": started.isoformat(),
        "status": status,
        "models": models or {},
        "tokens_in": 100,
        "tokens_out": 50,
        "cost_usd": 0.01,
    }
    if duration_minutes is not None:
        payload["ended_at"] = (started + timedelta(minutes=duration_minutes)).isoformat()
    if user_id is not None:
        payload["user_id"] = user_id
    (run_dir / "manifest.json").write_text(json.dumps(payload))
    return run_dir


def test_returns_empty_list_when_project_dir_missing(client) -> None:
    """Treat missing pid as empty history, not 404."""
    resp = client.get("/api/v1/projects/nonexistent_pid/idea_history")
    assert resp.status_code == 200
    assert resp.json() == {"entries": []}


def test_returns_empty_list_when_runs_dir_missing(
    client, tmp_project_root: Path
) -> None:
    (tmp_project_root / "pid_only_meta").mkdir()
    resp = client.get("/api/v1/projects/pid_only_meta/idea_history")
    assert resp.status_code == 200
    assert resp.json() == {"entries": []}


def test_lists_idea_runs_only(client, tmp_project_root: Path) -> None:
    """Only manifests with workflow starting with 'get_idea' should surface."""
    _write_manifest(
        tmp_project_root,
        "pid_filter",
        "run_idea_a",
        workflow="get_idea_fast",
        started_offset_minutes=10,
        duration_minutes=2.0,
        models={"idea_maker": "gpt-5"},
    )
    _write_manifest(
        tmp_project_root,
        "pid_filter",
        "run_idea_b",
        workflow="get_idea_cmagent",
        started_offset_minutes=20,
        duration_minutes=3.0,
        models={"idea_maker": "claude"},
    )
    # Non-idea workflows must be filtered out.
    _write_manifest(
        tmp_project_root,
        "pid_filter",
        "run_paper",
        workflow="get_paper",
        started_offset_minutes=5,
        duration_minutes=1.5,
    )
    _write_manifest(
        tmp_project_root,
        "pid_filter",
        "run_method",
        workflow="get_method_fast",
        started_offset_minutes=15,
    )

    resp = client.get("/api/v1/projects/pid_filter/idea_history")
    assert resp.status_code == 200
    body = resp.json()
    ids = [e["run_id"] for e in body["entries"]]
    assert sorted(ids) == ["run_idea_a", "run_idea_b"]


def test_entries_sorted_by_started_at_desc(client, tmp_project_root: Path) -> None:
    """Newest run first."""
    _write_manifest(
        tmp_project_root, "pid_sort", "run_old",
        workflow="get_idea_fast", started_offset_minutes=120,
    )
    _write_manifest(
        tmp_project_root, "pid_sort", "run_new",
        workflow="get_idea_fast", started_offset_minutes=5,
    )
    _write_manifest(
        tmp_project_root, "pid_sort", "run_middle",
        workflow="get_idea_fast", started_offset_minutes=30,
    )

    body = client.get("/api/v1/projects/pid_sort/idea_history").json()
    ids = [e["run_id"] for e in body["entries"]]
    assert ids == ["run_new", "run_middle", "run_old"]


def test_duration_seconds_computed_from_started_ended(
    client, tmp_project_root: Path
) -> None:
    _write_manifest(
        tmp_project_root, "pid_dur", "run_x",
        workflow="get_idea_fast",
        started_offset_minutes=10, duration_minutes=2.5,
    )
    body = client.get("/api/v1/projects/pid_dur/idea_history").json()
    entry = body["entries"][0]
    # Allow ±1s slack for any rounding inside iso<->datetime round-trip.
    assert abs(entry["duration_seconds"] - 150.0) < 1.0


def test_duration_seconds_null_when_run_unfinished(
    client, tmp_project_root: Path
) -> None:
    """A still-running manifest has no ended_at, so duration_seconds is null."""
    _write_manifest(
        tmp_project_root, "pid_unfin", "run_running",
        workflow="get_idea_fast",
        started_offset_minutes=2,
        duration_minutes=None,
        status="running",
    )
    body = client.get("/api/v1/projects/pid_unfin/idea_history").json()
    entry = body["entries"][0]
    assert entry["duration_seconds"] is None
    assert entry["status"] == "running"


def test_corrupt_manifest_is_skipped(
    client, tmp_project_root: Path
) -> None:
    """A run with a busted manifest.json should drop out of the list, not 500."""
    good = _write_manifest(
        tmp_project_root, "pid_corrupt", "run_good",
        workflow="get_idea_fast", started_offset_minutes=5,
    )
    bad_run = tmp_project_root / "pid_corrupt" / "runs" / "run_bad"
    bad_run.mkdir(parents=True, exist_ok=True)
    (bad_run / "manifest.json").write_text("{not valid json")

    resp = client.get("/api/v1/projects/pid_corrupt/idea_history")
    assert resp.status_code == 200
    ids = [e["run_id"] for e in resp.json()["entries"]]
    assert ids == ["run_good"]


def test_models_field_round_trips(client, tmp_project_root: Path) -> None:
    _write_manifest(
        tmp_project_root, "pid_models", "run_m",
        workflow="get_idea_fast",
        started_offset_minutes=5,
        models={
            "idea_maker": "gpt-5",
            "idea_hater": "o3-mini",
            "planner": "gpt-4.1",
        },
    )
    body = client.get("/api/v1/projects/pid_models/idea_history").json()
    entry = body["entries"][0]
    assert entry["models"]["idea_maker"] == "gpt-5"
    assert entry["models"]["idea_hater"] == "o3-mini"
    assert entry["models"]["planner"] == "gpt-4.1"
