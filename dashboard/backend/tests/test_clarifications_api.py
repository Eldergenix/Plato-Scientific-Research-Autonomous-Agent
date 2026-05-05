"""Smoke tests for the clarifying-questions endpoints (Stream 3 / F2).

These tests stand the router up on its own FastAPI app so they don't
depend on Stream 1 wiring it into ``server.py``. The handlers read
``project_root`` from settings, which the ``tmp_project_root`` fixture
already redirects to a temp dir.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plato_dashboard.api.clarifications import router as clarifications_router


@pytest.fixture
def client(tmp_project_root: Path):  # noqa: ARG001 — fixture sets project_root
    """Iter-9: yield from a context manager so the ASGI lifespan startup
    fires (matching conftest.py's ``client`` fixture). The previous
    bare-return form skipped lifespan, leaving the app's startup
    side-effects (logger config, settings cache, etc.) un-initialised."""
    app = FastAPI()
    app.include_router(clarifications_router, prefix="/api/v1")
    with TestClient(app) as c:
        yield c


def _make_run(project_root: Path, run_id: str, project_id: str = "prj_a") -> Path:
    run_dir = project_root / project_id / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _write_clarifications(run_dir: Path, questions: list[str], needs: bool = True) -> None:
    (run_dir / "clarifications.json").write_text(
        json.dumps({"questions": questions, "needs_clarification": needs})
    )


def _write_manifest_extra(run_dir: Path, questions: list[str], needs: bool = True) -> None:
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "extra": {
                    "clarifying_questions": questions,
                    "needs_clarification": needs,
                },
            }
        )
    )


def test_get_unknown_run_returns_404(client: TestClient) -> None:
    resp = client.get("/api/v1/runs/run_does_not_exist/clarifications")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "run_not_found"


def test_get_returns_empty_when_no_clarifier_output(
    client: TestClient, tmp_project_root: Path
) -> None:
    """A run with no clarifications.json or manifest extras → empty payload."""
    _make_run(tmp_project_root, "run_silent")

    resp = client.get("/api/v1/runs/run_silent/clarifications")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "questions": [],
        "needs_clarification": False,
        "answers_submitted": False,
    }


def test_get_reads_clarifications_json(
    client: TestClient, tmp_project_root: Path
) -> None:
    run_dir = _make_run(tmp_project_root, "run_q1")
    _write_clarifications(run_dir, ["What's the dataset?", "Which detector?"])

    resp = client.get("/api/v1/runs/run_q1/clarifications")
    assert resp.status_code == 200
    body = resp.json()
    assert body["questions"] == ["What's the dataset?", "Which detector?"]
    assert body["needs_clarification"] is True
    assert body["answers_submitted"] is False


def test_get_falls_back_to_manifest_extra(
    client: TestClient, tmp_project_root: Path
) -> None:
    run_dir = _make_run(tmp_project_root, "run_q2")
    _write_manifest_extra(run_dir, ["What's the goal?"])

    resp = client.get("/api/v1/runs/run_q2/clarifications")
    assert resp.status_code == 200
    body = resp.json()
    assert body["questions"] == ["What's the goal?"]
    assert body["needs_clarification"] is True


def test_get_reports_answers_submitted_when_file_exists(
    client: TestClient, tmp_project_root: Path
) -> None:
    run_dir = _make_run(tmp_project_root, "run_done")
    _write_clarifications(run_dir, ["Q1"])
    (run_dir / "clarifications_answers.json").write_text(
        json.dumps({"answers": ["A1"], "submitted_at": "2026-01-01T00:00:00+00:00"})
    )

    body = client.get("/api/v1/runs/run_done/clarifications").json()
    assert body["answers_submitted"] is True


def test_post_validates_answer_count(
    client: TestClient, tmp_project_root: Path
) -> None:
    run_dir = _make_run(tmp_project_root, "run_q3")
    _write_clarifications(run_dir, ["Q1", "Q2", "Q3"])

    resp = client.post(
        "/api/v1/runs/run_q3/clarifications",
        json={"answers": ["only one"]},
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "answer_count_mismatch"
    assert detail["expected"] == 3
    assert detail["received"] == 1


def test_post_writes_answers_with_iso_timestamp(
    client: TestClient, tmp_project_root: Path
) -> None:
    run_dir = _make_run(tmp_project_root, "run_q4")
    _write_clarifications(run_dir, ["Q1", "Q2"])

    resp = client.post(
        "/api/v1/runs/run_q4/clarifications",
        json={"answers": ["A1", "A2"]},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "answers_count": 2}

    saved = json.loads((run_dir / "clarifications_answers.json").read_text())
    assert saved["answers"] == ["A1", "A2"]
    # Submitted at must parse as ISO-8601 with timezone info
    parsed = datetime.fromisoformat(saved["submitted_at"])
    assert parsed.tzinfo is not None


def test_post_rejects_non_string_answers(
    client: TestClient, tmp_project_root: Path
) -> None:
    run_dir = _make_run(tmp_project_root, "run_q5")
    _write_clarifications(run_dir, ["Q1"])

    resp = client.post(
        "/api/v1/runs/run_q5/clarifications",
        json={"answers": [123]},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_answers"


def test_post_unknown_run_returns_404(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/runs/run_nope/clarifications",
        json={"answers": []},
    )
    assert resp.status_code == 404


def test_cross_tenant_returns_404_in_per_user_layout(
    client: TestClient, tmp_project_root: Path
) -> None:
    """Iter-8: rewrite the iter-5 cross-tenant test against the real
    contract. The previous version wrote ``{"owner": "alice"}`` to
    ``meta.json`` and sent ``X-User-Id``, but neither field nor header
    matches what the router consults — the ownership check reads
    ``manifest.json#user_id`` and the auth header is ``X-Plato-User``,
    so the test was vacuously passing on a 404 produced by an unrelated
    code path. Rewritten to exercise the per-user namespace lookup
    that ``manifests._find_run_dir`` actually performs.
    """
    # Place the run under the per-user namespace for ``alice``.
    run_dir = (
        tmp_project_root / "users" / "alice" / "prj_a" / "runs" / "run_tenant"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_clarifications(run_dir, ["Q1"])
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "run_tenant", "user_id": "alice"})
    )

    # Bob looks for the run inside his own namespace and never sees
    # alice's run dir — 404 not 200.
    bob = client.get(
        "/api/v1/runs/run_tenant/clarifications",
        headers={"X-Plato-User": "bob"},
    )
    assert bob.status_code == 404

    # Alice resolves it.
    alice = client.get(
        "/api/v1/runs/run_tenant/clarifications",
        headers={"X-Plato-User": "alice"},
    )
    assert alice.status_code == 200
