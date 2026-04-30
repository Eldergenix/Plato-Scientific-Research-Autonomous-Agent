"""Tests for the counter-evidence + research-gap router.

The router exposes two read-only endpoints under
``/api/v1/runs/{run_id}/{counter_evidence,gaps}``. They reuse
``manifests._find_run_dir`` so the layout discovery rules are identical
to the manifest endpoint.

We mount the router directly in a tiny FastAPI app instead of relying on
``create_app`` — that way the suite passes whether or not the main
server has wired the router yet (the router is owned by Stream 2; the
mount happens in a different stream).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    """Build a TestClient with the research-signals router mounted under /api/v1."""
    proj_root = tmp_path / "projects"
    proj_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PLATO_PROJECT_ROOT", str(proj_root))
    monkeypatch.setenv("PLATO_KEYS_PATH", str(tmp_path / "keys.json"))
    monkeypatch.delenv("PLATO_DEMO_MODE", raising=False)

    from plato_dashboard.api.research_signals import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def _make_run_dir(tmp_path: Path, project: str, run_id: str) -> Path:
    run_dir = tmp_path / "projects" / project / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def test_counter_evidence_404_when_run_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _build_client(monkeypatch, tmp_path)
    resp = client.get("/api/v1/runs/run_does_not_exist/counter_evidence")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "run_not_found"


def test_gaps_404_when_run_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _build_client(monkeypatch, tmp_path)
    resp = client.get("/api/v1/runs/run_does_not_exist/gaps")
    assert resp.status_code == 404


def test_counter_evidence_empty_payload_when_no_signals(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Run dir exists but no counter_evidence.json or manifest.extra → empty 200."""
    _make_run_dir(tmp_path, "p1", "run_alpha")
    client = _build_client(monkeypatch, tmp_path)
    resp = client.get("/api/v1/runs/run_alpha/counter_evidence")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"sources": [], "queries_used": []}


def test_gaps_empty_payload_when_no_signals(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _make_run_dir(tmp_path, "p1", "run_alpha")
    client = _build_client(monkeypatch, tmp_path)
    resp = client.get("/api/v1/runs/run_alpha/gaps")
    assert resp.status_code == 200
    assert resp.json() == {"gaps": []}


def test_counter_evidence_reads_dedicated_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_dir = _make_run_dir(tmp_path, "p1", "run_beta")
    payload = {
        "sources": [
            {
                "id": "src_1",
                "title": "Failed replication of foo",
                "venue": "Nature",
                "year": 2024,
                "doi": "10.1000/foo",
                "arxiv_id": None,
                "url": None,
            },
            {
                "id": "src_2",
                "title": "Null result for bar",
                "venue": None,
                "year": 2023,
                "doi": None,
                "arxiv_id": "2403.12345",
                "url": None,
            },
        ],
        "queries_used": ["x fail to replicate", "x null result"],
    }
    (run_dir / "counter_evidence.json").write_text(json.dumps(payload))

    client = _build_client(monkeypatch, tmp_path)
    resp = client.get("/api/v1/runs/run_beta/counter_evidence")
    assert resp.status_code == 200
    body = resp.json()
    assert body["queries_used"] == ["x fail to replicate", "x null result"]
    assert len(body["sources"]) == 2
    assert body["sources"][0]["title"] == "Failed replication of foo"
    assert body["sources"][0]["doi"] == "10.1000/foo"
    assert body["sources"][1]["arxiv_id"] == "2403.12345"


def test_gaps_falls_back_to_manifest_extra(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_dir = _make_run_dir(tmp_path, "p1", "run_gamma")
    manifest = {
        "run_id": "run_gamma",
        "extra": {
            "gaps": [
                {
                    "kind": "contradiction",
                    "description": "claim X has both supports and refutes",
                    "severity": 4,
                    "evidence": ["src_1", "src_2"],
                },
                {
                    "kind": "coverage",
                    "description": "keyword 'foo' appears in 0 sources",
                    "severity": 4,
                    "evidence": ["foo"],
                },
            ]
        },
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest))

    client = _build_client(monkeypatch, tmp_path)
    resp = client.get("/api/v1/runs/run_gamma/gaps")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["gaps"]) == 2
    assert body["gaps"][0]["kind"] == "contradiction"
    assert body["gaps"][0]["severity"] == 4
    assert body["gaps"][1]["evidence"] == ["foo"]


def test_counter_evidence_403_cross_tenant_when_auth_required(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When auth is enabled and the run's user_id differs from the caller, 403."""
    monkeypatch.setenv("PLATO_AUTH", "enabled")
    run_dir = _make_run_dir(tmp_path, "p1", "run_delta")
    manifest = {"run_id": "run_delta", "user_id": "alice", "extra": {}}
    (run_dir / "manifest.json").write_text(json.dumps(manifest))

    client = _build_client(monkeypatch, tmp_path)
    resp = client.get(
        "/api/v1/runs/run_delta/counter_evidence",
        headers={"X-Plato-User": "mallory"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "cross_tenant"

    # And the rightful owner gets 200 with the empty payload.
    ok = client.get(
        "/api/v1/runs/run_delta/counter_evidence",
        headers={"X-Plato-User": "alice"},
    )
    assert ok.status_code == 200
