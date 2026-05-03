"""Tests for ``GET /api/v1/telemetry/recent`` and ``/telemetry/status``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def telemetry_sink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``Path.home()`` so the collector reads from tmp.

    The endpoint instantiates ``TelemetryCollector()`` with no path,
    which resolves to ``~/.plato/telemetry.jsonl`` lazily — patching
    ``Path.home`` is the supported override (see plato/state/telemetry.py).
    """
    monkeypatch.delenv("PLATO_TELEMETRY_DISABLED", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    sink = tmp_path / ".plato" / "telemetry.jsonl"
    sink.parent.mkdir(parents=True, exist_ok=True)
    return sink


def _seed(sink: Path, rows: list[dict]) -> None:
    sink.write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n"
    )


# ---------------------------------------------------------------- /recent


def test_recent_returns_newest_first(client: TestClient, telemetry_sink: Path) -> None:
    _seed(
        telemetry_sink,
        [
            {"run_id": "old", "workflow": "wf", "status": "success"},
            {"run_id": "mid", "workflow": "wf", "status": "success"},
            {"run_id": "new", "workflow": "wf", "status": "success"},
        ],
    )

    resp = client.get("/api/v1/telemetry/recent")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert [r["run_id"] for r in body["items"]] == ["new", "mid", "old"]
    assert body["total"] == 3


def test_recent_limit_caps_response(client: TestClient, telemetry_sink: Path) -> None:
    rows = [
        {"run_id": f"r{i}", "workflow": "wf", "status": "success"}
        for i in range(5)
    ]
    _seed(telemetry_sink, rows)
    resp = client.get("/api/v1/telemetry/recent?limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    # Newest two — r4, r3.
    assert [r["run_id"] for r in body["items"]] == ["r4", "r3"]


def test_recent_invalid_limit_rejected(client: TestClient, telemetry_sink: Path) -> None:
    """Pydantic validates the ``ge=1, le=500`` bounds on the query."""
    resp = client.get("/api/v1/telemetry/recent?limit=0")
    assert resp.status_code == 422
    resp = client.get("/api/v1/telemetry/recent?limit=9999")
    assert resp.status_code == 422


def test_recent_empty_when_no_file(client: TestClient, telemetry_sink: Path) -> None:
    # The fixture only ensures the parent dir exists; the JSONL file
    # itself is absent until a row is written. That's the "fresh
    # install, telemetry never fired" case.
    telemetry_sink.unlink(missing_ok=True)
    resp = client.get("/api/v1/telemetry/recent")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0, "enabled": True}


def test_recent_filters_by_project_id(
    client: TestClient, telemetry_sink: Path
) -> None:
    _seed(
        telemetry_sink,
        [
            {"run_id": "a", "workflow": "wf", "status": "success", "project_id": "p1"},
            {"run_id": "b", "workflow": "wf", "status": "success", "project_id": "p2"},
            {"run_id": "c", "workflow": "wf", "status": "success", "project_id": "p1"},
        ],
    )
    resp = client.get("/api/v1/telemetry/recent?project_id=p1")
    assert resp.status_code == 200
    body = resp.json()
    # Newest-first: c, a (both p1).
    assert [r["run_id"] for r in body["items"]] == ["c", "a"]
    assert body["total"] == 2


def test_recent_skips_malformed_lines(
    client: TestClient, telemetry_sink: Path
) -> None:
    """A bad line in the JSONL must not 500 the endpoint."""
    telemetry_sink.write_text(
        '{"run_id":"a","workflow":"wf","status":"success"}\n'
        "garbage not json\n"
        '{"run_id":"b","workflow":"wf","status":"success"}\n'
    )
    resp = client.get("/api/v1/telemetry/recent")
    assert resp.status_code == 200
    body = resp.json()
    assert [r["run_id"] for r in body["items"]] == ["b", "a"]


def test_recent_reports_disabled_state(
    client: TestClient,
    telemetry_sink: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ``enabled`` flag in the response mirrors the kill switch.

    The endpoint still serves whatever's already on disk (the toggle
    only gates new writes), so existing rows remain visible.
    """
    monkeypatch.setenv("PLATO_TELEMETRY_DISABLED", "1")
    _seed(
        telemetry_sink,
        [{"run_id": "x", "workflow": "wf", "status": "success"}],
    )
    resp = client.get("/api/v1/telemetry/recent")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    # The on-disk row is still readable; only future writes are blocked.
    assert [r["run_id"] for r in body["items"]] == ["x"]


# ---------------------------------------------------------------- tenancy


def test_recent_filters_by_user_when_auth_required(
    client: TestClient,
    telemetry_sink: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLATO_DASHBOARD_AUTH_REQUIRED", "1")
    _seed(
        telemetry_sink,
        [
            {"run_id": "a", "workflow": "wf", "status": "success", "user_id": "alice"},
            {"run_id": "b", "workflow": "wf", "status": "success", "user_id": "bob"},
            {"run_id": "c", "workflow": "wf", "status": "success", "user_id": "alice"},
            # An untagged row from before tenant mode — must NOT leak.
            {"run_id": "legacy", "workflow": "wf", "status": "success"},
        ],
    )

    resp = client.get(
        "/api/v1/telemetry/recent",
        headers={"X-Plato-User": "alice"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [r["run_id"] for r in body["items"]] == ["c", "a"]
    assert body["total"] == 2

    # Bob sees only his own row.
    resp = client.get(
        "/api/v1/telemetry/recent",
        headers={"X-Plato-User": "bob"},
    )
    assert [r["run_id"] for r in resp.json()["items"]] == ["b"]


def test_recent_returns_401_when_required_mode_and_no_user_header(
    client: TestClient,
    telemetry_sink: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLATO_DASHBOARD_AUTH_REQUIRED", "1")
    _seed(
        telemetry_sink,
        [{"run_id": "a", "workflow": "wf", "status": "success"}],
    )
    resp = client.get("/api/v1/telemetry/recent")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "auth_required"


# ---------------------------------------------------------------- /status


def test_status_reports_record_count(
    client: TestClient, telemetry_sink: Path
) -> None:
    _seed(
        telemetry_sink,
        [
            {"run_id": "a", "workflow": "wf", "status": "success"},
            {"run_id": "b", "workflow": "wf", "status": "success"},
        ],
    )
    resp = client.get("/api/v1/telemetry/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is True
    assert body["record_count"] == 2
    assert body["storage_path"].endswith("telemetry.jsonl")


def test_status_zero_count_when_no_file(
    client: TestClient, telemetry_sink: Path
) -> None:
    telemetry_sink.unlink(missing_ok=True)
    resp = client.get("/api/v1/telemetry/status")
    assert resp.status_code == 200
    assert resp.json()["record_count"] == 0
