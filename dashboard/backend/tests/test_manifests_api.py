"""Tests for the run-manifest / evidence-matrix / validation-report endpoints."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _make_run_dir(project_root: Path, run_id: str, project: str | None = None) -> Path:
    """Create a ``runs/<run_id>/`` dir under either flat or nested layout.

    Defaults to the nested ``<project_root>/<project>/runs/<run_id>/``
    layout so we exercise the multi-project scan path.
    """
    base = project_root / project if project else project_root
    run_dir = base / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


@pytest.fixture
def app_client(tmp_project_root: Path):
    from plato_dashboard.api.server import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c, tmp_project_root


def test_manifest_returns_404_for_unknown_run(app_client) -> None:
    client, _ = app_client
    resp = client.get("/api/v1/runs/does-not-exist/manifest")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "run_not_found"


def test_manifest_returns_404_when_run_dir_exists_but_file_missing(app_client) -> None:
    client, root = app_client
    _make_run_dir(root, "run_no_manifest", project="proj_a")
    resp = client.get("/api/v1/runs/run_no_manifest/manifest")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "manifest_not_found"


def test_manifest_returns_parsed_json(app_client) -> None:
    client, root = app_client
    run_dir = _make_run_dir(root, "run_ok", project="proj_a")
    payload = {
        "run_id": "run_ok",
        "workflow": "get_idea_fast",
        "started_at": "2026-04-29T00:00:00Z",
        "status": "success",
        "domain": "astro",
        "git_sha": "abc123",
        "models": {"idea_maker": "gemini-2.0-flash"},
        "tokens_in": 1200,
        "tokens_out": 800,
        "cost_usd": 0.04,
        "source_ids": ["src_1", "src_2"],
    }
    (run_dir / "manifest.json").write_text(json.dumps(payload))

    resp = client.get("/api/v1/runs/run_ok/manifest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "run_ok"
    assert body["workflow"] == "get_idea_fast"
    assert body["models"]["idea_maker"] == "gemini-2.0-flash"
    assert body["tokens_in"] == 1200


def test_manifest_works_with_flat_layout(app_client) -> None:
    """Flat ``<project_root>/runs/<id>/`` (single-project install)."""
    client, root = app_client
    run_dir = _make_run_dir(root, "run_flat", project=None)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "run_flat", "workflow": "get_paper", "started_at": "2026-04-29T00:00:00Z"})
    )
    resp = client.get("/api/v1/runs/run_flat/manifest")
    assert resp.status_code == 200
    assert resp.json()["run_id"] == "run_flat"


def test_evidence_matrix_parses_claims_and_links(app_client) -> None:
    client, root = app_client
    run_dir = _make_run_dir(root, "run_em", project="proj_a")

    claims = [
        {"id": "c1", "text": "Dark energy density is constant.", "source_id": "s1"},
        {"id": "c2", "text": "H0 tension is real.", "source_id": "s2"},
    ]
    links = [
        {"claim_id": "c1", "source_id": "s1", "support": "supports", "strength": "strong"},
        {"claim_id": "c2", "source_id": "s2", "support": "neutral", "strength": "weak"},
    ]
    with (run_dir / "evidence_matrix.jsonl").open("w") as fh:
        for record in (*claims, *links):
            fh.write(json.dumps(record) + "\n")

    resp = client.get("/api/v1/runs/run_em/evidence_matrix")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["claims"]) == 2
    assert {c["id"] for c in body["claims"]} == {"c1", "c2"}
    assert len(body["evidence_links"]) == 2
    assert {(l["claim_id"], l["support"]) for l in body["evidence_links"]} == {
        ("c1", "supports"),
        ("c2", "neutral"),
    }


def test_evidence_matrix_returns_empty_lists_when_no_files(app_client) -> None:
    client, root = app_client
    _make_run_dir(root, "run_empty", project="proj_a")
    resp = client.get("/api/v1/runs/run_empty/evidence_matrix")
    assert resp.status_code == 200
    assert resp.json() == {"claims": [], "evidence_links": []}


def test_evidence_matrix_skips_malformed_lines(app_client) -> None:
    client, root = app_client
    run_dir = _make_run_dir(root, "run_partial", project="proj_a")
    with (run_dir / "evidence_matrix.jsonl").open("w") as fh:
        fh.write(json.dumps({"id": "c1", "text": "claim"}) + "\n")
        fh.write("{not valid json\n")
        fh.write("\n")
        fh.write(json.dumps({"claim_id": "c1", "source_id": "s1", "support": "refutes", "strength": "moderate"}) + "\n")

    resp = client.get("/api/v1/runs/run_partial/evidence_matrix")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["claims"]) == 1
    assert len(body["evidence_links"]) == 1


def test_evidence_matrix_404_for_unknown_run(app_client) -> None:
    client, _ = app_client
    resp = client.get("/api/v1/runs/missing/evidence_matrix")
    assert resp.status_code == 404


def test_validation_report_returns_json(app_client) -> None:
    client, root = app_client
    run_dir = _make_run_dir(root, "run_vr", project="proj_a")
    report = {
        "validation_rate": 0.85,
        "total_references": 20,
        "verified_references": 17,
        "failures": [
            {"source_id": "s5", "reason": "doi_unresolvable"},
            {"source_id": "s12", "reason": "url_dead"},
        ],
    }
    (run_dir / "validation_report.json").write_text(json.dumps(report))

    resp = client.get("/api/v1/runs/run_vr/validation_report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["validation_rate"] == 0.85
    assert body["total_references"] == 20
    assert len(body["failures"]) == 2


def test_validation_report_404_when_missing(app_client) -> None:
    client, root = app_client
    _make_run_dir(root, "run_no_vr", project="proj_a")
    resp = client.get("/api/v1/runs/run_no_vr/validation_report")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "validation_report_not_found"
