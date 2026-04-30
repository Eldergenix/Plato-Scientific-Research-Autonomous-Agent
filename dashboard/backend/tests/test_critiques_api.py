"""Tests for the reviewer-panel critique endpoint."""
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
def critiques_app(tmp_project_root: Path) -> tuple[TestClient, Path]:
    """Mount the critiques router on a bare FastAPI app.

    We don't use ``create_app`` here because the integration commit is what
    wires the router into ``server.py``. Tests for the router itself should
    exercise it in isolation — that way we catch a router regression even
    if server.py wires it up wrong.
    """
    from plato_dashboard.api.critiques import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as client:
        yield client, tmp_project_root


def test_critiques_404_for_unknown_run(critiques_app) -> None:
    client, _ = critiques_app
    resp = client.get("/api/v1/runs/does-not-exist/critiques")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "run_not_found"


def test_critiques_returns_empty_payload_when_no_critiques_written(critiques_app) -> None:
    client, root = critiques_app
    _make_run_dir(root, "run_empty")
    resp = client.get("/api/v1/runs/run_empty/critiques")
    assert resp.status_code == 200
    assert resp.json() == {"critiques": {}, "digest": None, "revision_state": None}


def test_critiques_reads_sidecar_happy_path(critiques_app) -> None:
    client, root = critiques_app
    run_dir = _make_run_dir(root, "run_full")
    payload = {
        "critiques": {
            "methodology": {
                "severity": 3,
                "rationale": "Sample size justification missing.",
                "issues": [
                    {
                        "section": "methods",
                        "issue": "n=12 is underpowered",
                        "fix": "Run a power analysis or expand the cohort.",
                    }
                ],
            },
            "statistics": {
                "severity": 2,
                "rationale": "Multiple-comparisons correction unclear.",
                "issues": [],
            },
            "novelty": {
                "severity": 1,
                "rationale": "Modest delta over Smith 2024.",
                "issues": [],
            },
            "writing": {
                "severity": 0,
                "rationale": "Clear prose throughout.",
                "issues": [],
            },
        },
        "digest": {
            "max_severity": 3,
            "issues": [
                {
                    "reviewer": "methodology",
                    "section": "methods",
                    "issue": "n=12 is underpowered",
                }
            ],
            "iteration": 2,
        },
        "revision_state": {"iteration": 2, "max_iterations": 3},
    }
    (run_dir / "critiques.json").write_text(json.dumps(payload))

    resp = client.get("/api/v1/runs/run_full/critiques")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["critiques"].keys()) == {"methodology", "statistics", "novelty", "writing"}
    assert body["critiques"]["methodology"]["severity"] == 3
    assert body["critiques"]["writing"]["severity"] == 0
    assert body["digest"]["max_severity"] == 3
    assert body["digest"]["iteration"] == 2
    assert body["revision_state"] == {"iteration": 2, "max_iterations": 3}


def test_critiques_falls_back_to_manifest_extra(critiques_app) -> None:
    client, root = critiques_app
    run_dir = _make_run_dir(root, "run_legacy")
    manifest = {
        "run_id": "run_legacy",
        "workflow": "get_paper",
        "started_at": "2026-04-29T00:00:00Z",
        "extra": {
            "critiques": {
                "methodology": {
                    "severity": 4,
                    "rationale": "Confounders unaddressed.",
                    "issues": [],
                }
            },
            "revision_state": {"iteration": 1, "max_iterations": 3},
        },
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest))

    resp = client.get("/api/v1/runs/run_legacy/critiques")
    assert resp.status_code == 200
    body = resp.json()
    assert body["critiques"]["methodology"]["severity"] == 4
    # Missing axes are normalised to None so the UI grid stays 2x2.
    assert body["critiques"]["statistics"] is None
    assert body["critiques"]["novelty"] is None
    assert body["critiques"]["writing"] is None
    assert body["revision_state"] == {"iteration": 1, "max_iterations": 3}
    assert body["digest"] is None


def test_critiques_sidecar_takes_precedence_over_manifest(critiques_app) -> None:
    """If both sources exist, the sidecar wins."""
    client, root = critiques_app
    run_dir = _make_run_dir(root, "run_both")
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "extra": {
                    "critiques": {"methodology": {"severity": 9, "rationale": "stale", "issues": []}}
                }
            }
        )
    )
    (run_dir / "critiques.json").write_text(
        json.dumps(
            {
                "critiques": {
                    "methodology": {"severity": 1, "rationale": "fresh", "issues": []}
                }
            }
        )
    )

    resp = client.get("/api/v1/runs/run_both/critiques")
    assert resp.status_code == 200
    assert resp.json()["critiques"]["methodology"]["severity"] == 1


def test_critiques_403_cross_tenant_in_required_mode(
    critiques_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When PLATO_AUTH=enabled, requester must own the run."""
    monkeypatch.setenv("PLATO_AUTH", "enabled")

    client, root = critiques_app
    run_dir = _make_run_dir(root, "run_owned")
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "run_owned", "user_id": "alice"})
    )
    (run_dir / "critiques.json").write_text(
        json.dumps({"critiques": {"methodology": {"severity": 1, "rationale": "x", "issues": []}}})
    )

    # Wrong user → 403.
    resp = client.get(
        "/api/v1/runs/run_owned/critiques",
        headers={"X-Plato-User": "bob"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "run_forbidden"

    # Correct user → 200.
    resp = client.get(
        "/api/v1/runs/run_owned/critiques",
        headers={"X-Plato-User": "alice"},
    )
    assert resp.status_code == 200
    assert resp.json()["critiques"]["methodology"]["severity"] == 1


def test_critiques_missing_manifest_in_required_mode_is_403(
    critiques_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No manifest under the requester namespace → fail closed in required-mode."""
    monkeypatch.setenv("PLATO_AUTH", "enabled")

    client, root = critiques_app
    _make_run_dir(root, "run_no_manifest")  # run dir exists, but no manifest.json

    resp = client.get(
        "/api/v1/runs/run_no_manifest/critiques",
        headers={"X-Plato-User": "alice"},
    )
    assert resp.status_code == 403


def test_critiques_legacy_run_no_user_id_passes_in_optional_mode(critiques_app) -> None:
    """Legacy mode (auth disabled): no header → no tenant check."""
    client, root = critiques_app
    run_dir = _make_run_dir(root, "run_legacy_optional")
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "run_legacy_optional"})  # no user_id field
    )
    resp = client.get("/api/v1/runs/run_legacy_optional/critiques")
    assert resp.status_code == 200
