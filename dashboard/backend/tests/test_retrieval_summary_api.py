"""Tests for the retrieval-summary endpoint.

We mount the router on a minimal FastAPI app rather than going through
``create_app()`` so the test exercises the endpoint in isolation —
``server.py`` doesn't yet wire the route, by design (other streams own
that integration).
"""
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
    from plato_dashboard.api.retrieval_summary import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as c:
        yield c, tmp_project_root


def test_returns_404_for_unknown_run(client) -> None:
    c, _ = client
    resp = c.get("/api/v1/runs/no-such-run/retrieval_summary")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "run_not_found"


def test_returns_empty_payload_when_no_data(client) -> None:
    c, root = client
    _make_run_dir(root, "run_empty")
    resp = c.get("/api/v1/runs/run_empty/retrieval_summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "by_adapter": [],
        "total_unique": 0,
        "total_returned": 0,
        "queries": [],
        "samples": [],
    }


def test_returns_payload_from_dedicated_file(client) -> None:
    c, root = client
    run_dir = _make_run_dir(root, "run_full")

    payload = {
        "by_adapter": [
            {"adapter": "arxiv", "count": 12, "deduped": 2},
            {"adapter": "openalex", "count": 25, "deduped": 5},
            {"adapter": "crossref", "count": 7, "deduped": 1},
            {"adapter": "ads", "count": 4, "deduped": 0},
            {"adapter": "pubmed", "count": 3, "deduped": 1},
            {"adapter": "semantic_scholar", "count": 9, "deduped": 2},
        ],
        "total_unique": 49,
        "total_returned": 60,
        "queries": ["dark energy", "Hubble tension"],
        "samples": [
            {"source_id": "10.1234/example", "title": "Sample paper", "adapter": "openalex"},
            {"source_id": "arxiv:2403.12345", "title": "Another", "adapter": "arxiv"},
        ],
    }
    (run_dir / "retrieval_summary.json").write_text(json.dumps(payload))

    resp = c.get("/api/v1/runs/run_full/retrieval_summary")
    assert resp.status_code == 200
    body = resp.json()
    # Sorted by count desc
    assert [r["adapter"] for r in body["by_adapter"]] == [
        "openalex", "arxiv", "semantic_scholar", "crossref", "ads", "pubmed",
    ]
    assert body["total_unique"] == 49
    assert body["total_returned"] == 60
    assert body["queries"] == ["dark energy", "Hubble tension"]
    assert len(body["samples"]) == 2


def test_falls_back_to_manifest_extra(client) -> None:
    c, root = client
    run_dir = _make_run_dir(root, "run_extra")

    manifest = {
        "run_id": "run_extra",
        "workflow": "get_idea_fast",
        "started_at": "2026-04-29T00:00:00Z",
        "extra": {
            "retrieval_log": {
                "by_adapter": [
                    {"adapter": "arxiv", "count": 5, "deduped": 1},
                    {"adapter": "openalex", "count": 3, "deduped": 0},
                ],
                "total_unique": 7,
                "total_returned": 8,
                "queries": ["q1"],
                "samples": [],
            }
        },
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest))

    resp = c.get("/api/v1/runs/run_extra/retrieval_summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_unique"] == 7
    assert body["total_returned"] == 8
    assert [r["adapter"] for r in body["by_adapter"]] == ["arxiv", "openalex"]


def test_dedicated_file_takes_precedence_over_manifest(client) -> None:
    c, root = client
    run_dir = _make_run_dir(root, "run_both")
    (run_dir / "retrieval_summary.json").write_text(
        json.dumps({"by_adapter": [{"adapter": "ads", "count": 2, "deduped": 0}], "total_returned": 2})
    )
    (run_dir / "manifest.json").write_text(
        json.dumps({"extra": {"retrieval_log": {"by_adapter": []}}})
    )
    resp = c.get("/api/v1/runs/run_both/retrieval_summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["by_adapter"] == [{"adapter": "ads", "count": 2, "deduped": 0}]


def test_drops_malformed_adapter_rows(client) -> None:
    c, root = client
    run_dir = _make_run_dir(root, "run_partial")
    (run_dir / "retrieval_summary.json").write_text(
        json.dumps(
            {
                "by_adapter": [
                    {"adapter": "arxiv", "count": 5, "deduped": 0},
                    {"adapter": "", "count": 1},  # empty adapter — drop
                    {"adapter": "openalex", "count": "nope"},  # bad count — drop
                    "scalar",  # not a dict — drop
                ],
                "total_returned": 5,
            }
        )
    )
    resp = c.get("/api/v1/runs/run_partial/retrieval_summary")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["by_adapter"]) == 1
    assert body["by_adapter"][0]["adapter"] == "arxiv"


def test_cross_tenant_returns_403_in_required_mode(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PLATO_DASHBOARD_AUTH_REQUIRED", "1")
    c, root = client
    run_dir = _make_run_dir(root, "run_other")
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "run_other", "user_id": "alice"})
    )
    (run_dir / "retrieval_summary.json").write_text(
        json.dumps({"by_adapter": [{"adapter": "arxiv", "count": 1, "deduped": 0}]})
    )

    resp = c.get(
        "/api/v1/runs/run_other/retrieval_summary",
        headers={"X-Plato-User": "bob"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "run_forbidden"

    # Owner can still see it.
    resp_owner = c.get(
        "/api/v1/runs/run_other/retrieval_summary",
        headers={"X-Plato-User": "alice"},
    )
    assert resp_owner.status_code == 200
