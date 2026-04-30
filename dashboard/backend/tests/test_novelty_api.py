"""Tests for the novelty-score endpoint."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_run_dir(project_root: Path, run_id: str, project: str | None = "proj_a") -> Path:
    base = project_root / project if project else project_root
    run_dir = base / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


@pytest.fixture
def client(tmp_project_root: Path):
    from plato_dashboard.api.novelty import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as c:
        yield c, tmp_project_root


def test_returns_404_for_unknown_run(client) -> None:
    c, _ = client
    resp = c.get("/api/v1/runs/missing/novelty")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "run_not_found"


def test_returns_all_null_when_not_computed(client) -> None:
    c, root = client
    _make_run_dir(root, "run_pending")
    resp = c.get("/api/v1/runs/run_pending/novelty")
    assert resp.status_code == 200
    assert resp.json() == {
        "score": None,
        "max_similarity": None,
        "nearest_source_id": None,
        "llm_score": None,
        "embedding_score": None,
        "agreement": None,
    }


def test_returns_full_payload_from_dedicated_file(client) -> None:
    c, root = client
    run_dir = _make_run_dir(root, "run_scored")
    (run_dir / "novelty.json").write_text(
        json.dumps(
            {
                "score": 0.74,
                "max_similarity": 0.31,
                "nearest_source_id": "10.1234/related-work",
                "llm_score": 0.7,
                "embedding_score": 0.78,
                "agreement": True,
            }
        )
    )
    resp = c.get("/api/v1/runs/run_scored/novelty")
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"] == pytest.approx(0.74)
    assert body["max_similarity"] == pytest.approx(0.31)
    assert body["nearest_source_id"] == "10.1234/related-work"
    assert body["llm_score"] == pytest.approx(0.7)
    assert body["embedding_score"] == pytest.approx(0.78)
    assert body["agreement"] is True


def test_falls_back_to_manifest_extra(client) -> None:
    c, root = client
    run_dir = _make_run_dir(root, "run_via_manifest")
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "run_via_manifest",
                "extra": {
                    "novelty": {
                        "score": 0.5,
                        "llm_score": 0.4,
                        "embedding_score": 0.6,
                        "agreement": False,
                    }
                },
            }
        )
    )
    resp = c.get("/api/v1/runs/run_via_manifest/novelty")
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"] == pytest.approx(0.5)
    assert body["llm_score"] == pytest.approx(0.4)
    assert body["embedding_score"] == pytest.approx(0.6)
    assert body["agreement"] is False
    assert body["max_similarity"] is None  # not provided


def test_dedicated_file_takes_precedence(client) -> None:
    c, root = client
    run_dir = _make_run_dir(root, "run_both")
    (run_dir / "novelty.json").write_text(json.dumps({"score": 0.9}))
    (run_dir / "manifest.json").write_text(
        json.dumps({"extra": {"novelty": {"score": 0.1}}})
    )
    resp = c.get("/api/v1/runs/run_both/novelty")
    assert resp.status_code == 200
    assert resp.json()["score"] == pytest.approx(0.9)


def test_clamps_out_of_range_values(client) -> None:
    c, root = client
    run_dir = _make_run_dir(root, "run_oob")
    (run_dir / "novelty.json").write_text(
        json.dumps({"score": 1.5, "embedding_score": -0.4, "llm_score": "oops"})
    )
    resp = c.get("/api/v1/runs/run_oob/novelty")
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"] == pytest.approx(1.0)
    assert body["embedding_score"] == pytest.approx(0.0)
    assert body["llm_score"] is None  # non-numeric → null


def test_cross_tenant_returns_403_in_required_mode(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PLATO_DASHBOARD_AUTH_REQUIRED", "1")
    c, root = client
    run_dir = _make_run_dir(root, "run_alice")
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "run_alice", "user_id": "alice"})
    )
    (run_dir / "novelty.json").write_text(json.dumps({"score": 0.6}))

    resp = c.get(
        "/api/v1/runs/run_alice/novelty",
        headers={"X-Plato-User": "bob"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "run_forbidden"

    resp_owner = c.get(
        "/api/v1/runs/run_alice/novelty",
        headers={"X-Plato-User": "alice"},
    )
    assert resp_owner.status_code == 200
    assert resp_owner.json()["score"] == pytest.approx(0.6)
