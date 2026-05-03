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


def test_modal_and_e2b_kind_reflects_sdk_presence(client) -> None:
    """Iter-21: modal/e2b are real implementations now. Their kind
    reflects whether the host SDK is importable in the current env —
    "real" when present, "lazy" when not. Either way, never "stub" for
    a shipped backend.
    """
    import importlib.util

    body = client.get("/api/v1/executors").json()
    by_name = {e["name"]: e for e in body["executors"]}

    for name, sdk in (("modal", "modal"), ("e2b", "e2b_code_interpreter")):
        entry = by_name[name]
        sdk_present = importlib.util.find_spec(sdk) is not None
        expected_kind = "real" if sdk_present else "lazy"
        assert (
            entry["kind"] == expected_kind
        ), f"{name} kind mismatch: got {entry['kind']!r}, expected {expected_kind!r}"
        assert entry["available"] is sdk_present
        assert entry["kind"] != "stub", (
            f"{name} should never report kind=stub after iter-20 — "
            "the real impl is shipped, only SDK installation is optional."
        )


def test_local_jupyter_kind_reflects_jupyter_client_presence(client) -> None:
    """Iter-21: LocalJupyter is a real impl too. Its kind tracks
    jupyter_client importability in the active env."""
    import importlib.util

    body = client.get("/api/v1/executors").json()
    by_name = {e["name"]: e for e in body["executors"]}
    entry = by_name["local_jupyter"]
    sdk_present = importlib.util.find_spec("jupyter_client") is not None
    assert entry["kind"] == ("real" if sdk_present else "lazy")
    assert entry["available"] is sdk_present


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
