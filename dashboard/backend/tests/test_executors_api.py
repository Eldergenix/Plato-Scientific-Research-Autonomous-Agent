"""Tests for the GET /api/v1/executors catalogue endpoint."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app() -> FastAPI:
    """Mount just the executors router, isolated from the main app.

    The main ``create_app`` doesn't wire this router yet — the integration
    commit will. Building a tiny FastAPI shell here keeps the test focused
    on the route's behaviour.
    """
    from plato_dashboard.api.executors import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def client(tmp_project_root: Path):  # noqa: ARG001 — fixture forces env setup
    app = _make_app()
    with TestClient(app) as c:
        yield c


def test_lists_all_four_built_in_executors(client) -> None:
    resp = client.get("/api/v1/executors")
    assert resp.status_code == 200
    body = resp.json()
    assert body["default"] == "cmbagent"
    names = {e["name"] for e in body["executors"]}
    assert names == {"cmbagent", "local_jupyter", "modal", "e2b"}


def test_each_executor_has_required_fields(client) -> None:
    body = client.get("/api/v1/executors").json()
    for entry in body["executors"]:
        assert set(entry) == {"name", "available", "kind", "description"}
        assert entry["kind"] in {"real", "stub", "lazy"}
        assert isinstance(entry["available"], bool)
        assert isinstance(entry["description"], str) and entry["description"]


def test_modal_and_e2b_are_stubs_and_unavailable(client) -> None:
    body = client.get("/api/v1/executors").json()
    by_name = {e["name"]: e for e in body["executors"]}
    assert by_name["modal"]["kind"] == "stub"
    assert by_name["modal"]["available"] is False
    assert by_name["e2b"]["kind"] == "stub"
    assert by_name["e2b"]["available"] is False


def test_local_jupyter_is_lazy(client) -> None:
    body = client.get("/api/v1/executors").json()
    by_name = {e["name"]: e for e in body["executors"]}
    assert by_name["local_jupyter"]["kind"] == "lazy"
    # The kernel-execution loop isn't plumbed; surface "not available"
    # even when jupyter_client is importable so the UI can warn.
    assert by_name["local_jupyter"]["available"] is False


def test_cmbagent_kind_reflects_import_state(client, monkeypatch) -> None:
    """cmbagent should report 'real' when its package imports, 'lazy' otherwise."""
    import sys

    body = client.get("/api/v1/executors").json()
    by_name = {e["name"]: e for e in body["executors"]}

    if "cmbagent" in sys.modules or _can_import_cmbagent():
        assert by_name["cmbagent"]["kind"] == "real"
        assert by_name["cmbagent"]["available"] is True
    else:
        assert by_name["cmbagent"]["kind"] == "lazy"
        assert by_name["cmbagent"]["available"] is False


def _can_import_cmbagent() -> bool:
    try:
        import cmbagent  # noqa: F401
    except ImportError:
        return False
    return True
