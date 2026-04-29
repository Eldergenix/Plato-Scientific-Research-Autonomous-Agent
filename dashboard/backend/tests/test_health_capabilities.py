"""Smoke tests for ``GET /api/v1/health`` and ``GET /api/v1/capabilities``."""

from __future__ import annotations

import pytest


def test_health_local_default(client) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"ok": True, "demo_mode": False}


def test_capabilities_local_returns_all_seven_stages(client) -> None:
    resp = client.get("/api/v1/capabilities")
    assert resp.status_code == 200
    caps = resp.json()
    assert caps["is_demo"] is False
    assert sorted(caps["allowed_stages"]) == sorted(
        ["data", "idea", "literature", "method", "results", "paper", "referee"]
    )
    # Local mode → no budget cap
    assert caps["session_budget_cents"] is None
    assert caps["max_concurrent_runs"] >= 1


def test_capabilities_demo_locks_to_four_stages(
    monkeypatch: pytest.MonkeyPatch, tmp_project_root
) -> None:
    """In demo mode the four "safe" stages are exposed and a budget cap is set."""
    monkeypatch.setenv("PLATO_DEMO_MODE", "enabled")

    # Build a demo-mode app fresh (settings are read on every request, but the
    # app instance was created outside the env-var window so we rebuild it).
    from fastapi.testclient import TestClient
    from plato_dashboard.api.server import create_app

    app = create_app()
    with TestClient(app) as c:
        health = c.get("/api/v1/health").json()
        assert health == {"ok": True, "demo_mode": True}

        caps = c.get("/api/v1/capabilities").json()
        assert caps["is_demo"] is True
        assert caps["allowed_stages"] == ["data", "idea", "method", "literature"]
        assert caps["session_budget_cents"] is not None
        assert caps["max_concurrent_runs"] >= 1
