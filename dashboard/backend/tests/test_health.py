"""Smoke tests for root-level ``GET /health`` and ``GET /ready``.

These exist for k8s/ops liveness and readiness probes. They sit outside
``/api/v1`` on purpose so infra can hit them without an auth header and
without picking a tenant namespace.
"""

from __future__ import annotations

import pytest


def test_health_returns_200(client) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_payload_shape(client) -> None:
    resp = client.get("/health")
    body = resp.json()
    assert body == {
        "status": "ok",
        "service": "plato-dashboard-api",
        "version": "1.0.1",
    }


def test_health_works_without_auth_headers(
    monkeypatch: pytest.MonkeyPatch, tmp_project_root
) -> None:
    """In auth-required mode, /health must still answer with no headers."""
    monkeypatch.setenv("PLATO_DASHBOARD_AUTH_REQUIRED", "1")

    from fastapi.testclient import TestClient
    from plato_dashboard.api.server import create_app

    app = create_app()
    with TestClient(app) as c:
        # No X-Plato-User header — /api/v1 endpoints would 401 here, but
        # /health is tenant-agnostic and must stay reachable.
        resp = c.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Sanity: a tenant-scoped endpoint should 401 in this mode, so
        # we know the auth gate is actually engaged.
        guarded = c.get("/api/v1/projects")
        assert guarded.status_code == 401


def test_ready_returns_200_in_normal_state(client) -> None:
    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["plato_dir"] is True
    assert body["checks"]["langgraph_import"] is True
