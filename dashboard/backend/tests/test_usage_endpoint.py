"""Smoke tests for the /usage endpoints.

Covers the project-level aggregation endpoint and the live per-run
ledger endpoint surfaced by ``server.py``.
"""

from __future__ import annotations

import pytest

from plato_dashboard.worker.token_tracker import clear_run_ledger


@pytest.fixture(autouse=True)
def _reset_ledger():
    clear_run_ledger()
    yield
    clear_run_ledger()


def test_project_usage_returns_zero_shape_when_no_llm_calls(client) -> None:
    """A freshly-created project has no LLM_calls.txt yet — aggregation
    should still return 200 with the canonical zero-valued shape."""
    pid = client.post("/api/v1/projects", json={"name": "UsageZero"}).json()["id"]

    resp = client.get(f"/api/v1/projects/{pid}/usage")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Canonical keys, all zeroed out.
    assert body["total_input"] == 0
    assert body["total_output"] == 0
    assert body["total_cost_cents"] == 0
    assert body["by_stage"] == {}
    assert body["by_model"] == {}
    assert body["by_run"] == []


def test_project_usage_404_for_unknown_project(client) -> None:
    resp = client.get("/api/v1/projects/prj_does_not_exist/usage")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "project_not_found"


def test_run_usage_404_for_untracked_run(client) -> None:
    """A run id that has never streamed a tokens.delta event isn't in
    the live ledger — endpoint should 404 with run_not_tracked."""
    resp = client.get("/api/v1/runs/nonexistent/usage")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "run_not_tracked"
