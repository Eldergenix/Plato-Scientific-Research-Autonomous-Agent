"""Iter-27 — tests for /api/v1/projects/{pid}/approvals + run_stage gate.

Mirrors the iter-26 cost-cap test posture. Pin three contracts:

1. GET defaults to ``{per_stage: {}, auto_skip: false}`` for projects
   with no approvals configured.
2. PUT round-trips through ``meta.json``.
3. ``POST /projects/{pid}/stages/{stage}/run`` refuses with HTTP 403
   ``approval_required`` when an upstream gate (idea / literature /
   method) is "done" but un-approved AND the target stage is downstream
   of that gate.

Tenant scoping (cross-tenant 403s, missing X-Plato-User 401s) is
covered by ``test_project_tenant_security.py`` for every endpoint that
uses ``_enforce_project_tenant`` — including the new /approvals pair.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from plato_dashboard.api.server import create_app
from plato_dashboard.auth import AUTH_REQUIRED_ENV


@pytest.fixture
def authed_client(
    tmp_project_root: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(AUTH_REQUIRED_ENV, "1")
    app = create_app()
    with TestClient(app) as c:
        yield c


def _create_project(client: TestClient, user: str = "alice") -> str:
    resp = client.post(
        "/api/v1/projects",
        json={"name": "p"},
        headers={"X-Plato-User": user},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _mark_stage_done(
    project_root: Path, user: str, pid: str, stage: str
) -> None:
    """Patch meta.json to mark ``stage`` as done — needed so the
    iter-27 gate logic considers it a blocker (gates only block when
    they've actually run)."""
    meta_path = project_root / "users" / user / pid / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["stages"][stage]["status"] = "done"
    meta_path.write_text(json.dumps(meta))


# --- /approvals GET / PUT ---------------------------------------------------

def test_get_returns_default_empty_shape(authed_client: TestClient) -> None:
    pid = _create_project(authed_client)
    resp = authed_client.get(
        f"/api/v1/projects/{pid}/approvals",
        headers={"X-Plato-User": "alice"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"per_stage": {}, "auto_skip": False}


def test_put_then_get_round_trips_through_meta_json(
    authed_client: TestClient, tmp_project_root: Path
) -> None:
    pid = _create_project(authed_client)
    body = {
        "per_stage": {"idea": "approved", "literature": "rejected"},
        "auto_skip": False,
    }
    put_resp = authed_client.put(
        f"/api/v1/projects/{pid}/approvals",
        json=body,
        headers={"X-Plato-User": "alice"},
    )
    assert put_resp.status_code == 200
    assert put_resp.json() == body

    get_resp = authed_client.get(
        f"/api/v1/projects/{pid}/approvals",
        headers={"X-Plato-User": "alice"},
    )
    assert get_resp.json() == body

    # Verify on disk: the namespaced meta.json carries the approvals.
    meta_path = tmp_project_root / "users" / "alice" / pid / "meta.json"
    meta = json.loads(meta_path.read_text())
    assert meta["approvals"] == body


def test_put_rejects_invalid_state_value(authed_client: TestClient) -> None:
    """The Literal["pending","approved","rejected","skipped"] schema rejects
    bogus values at validation time."""
    pid = _create_project(authed_client)
    resp = authed_client.put(
        f"/api/v1/projects/{pid}/approvals",
        json={"per_stage": {"idea": "totally-invalid"}, "auto_skip": False},
        headers={"X-Plato-User": "alice"},
    )
    assert resp.status_code == 422


# --- run_stage approval gate -----------------------------------------------

def test_run_stage_blocks_downstream_when_idea_unapproved(
    authed_client: TestClient, tmp_project_root: Path
) -> None:
    """The CRITICAL one: idea is done but not approved → can't launch
    any of {literature, method, results, paper, referee}.

    This is the canonical "stale localStorage" attack the iter-27 gate
    blocks: a malicious client could clear localStorage and skip
    straight to results. The server now refuses regardless of client
    state.
    """
    pid = _create_project(authed_client)
    _mark_stage_done(tmp_project_root, "alice", pid, "idea")

    # No PUT to /approvals — the idea state defaults to "pending"
    # which means the gate fires.
    resp = authed_client.post(
        f"/api/v1/projects/{pid}/stages/results/run",
        json={"mode": "fast"},
        headers={"X-Plato-User": "alice"},
    )
    assert resp.status_code == 403, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "approval_required"
    assert detail["blocking_gate"] == "idea"
    assert detail["target_stage"] == "results"


def test_run_stage_allows_downstream_when_idea_approved(
    authed_client: TestClient, tmp_project_root: Path
) -> None:
    """Set idea=approved → idea no longer blocks. Other gates may still
    block (and that's fine — we just want NOT-budget_exceeded for the
    idea-specific case)."""
    pid = _create_project(authed_client)
    _mark_stage_done(tmp_project_root, "alice", pid, "idea")
    authed_client.put(
        f"/api/v1/projects/{pid}/approvals",
        json={"per_stage": {"idea": "approved"}, "auto_skip": False},
        headers={"X-Plato-User": "alice"},
    )

    resp = authed_client.post(
        f"/api/v1/projects/{pid}/stages/literature/run",
        json={"mode": "fast"},
        headers={"X-Plato-User": "alice"},
    )
    # Whatever else fails, it should NOT be the idea-approval gate.
    if resp.status_code == 403:
        detail = resp.json().get("detail", {})
        assert detail.get("blocking_gate") != "idea", (
            f"idea approval gate should not fire after idea=approved. "
            f"Detail: {detail}"
        )


def test_run_stage_skipped_state_is_treated_as_approved(
    authed_client: TestClient, tmp_project_root: Path
) -> None:
    """``skipped`` (user explicitly chose to bypass) clears the gate
    same as ``approved``."""
    pid = _create_project(authed_client)
    _mark_stage_done(tmp_project_root, "alice", pid, "idea")
    authed_client.put(
        f"/api/v1/projects/{pid}/approvals",
        json={"per_stage": {"idea": "skipped"}, "auto_skip": False},
        headers={"X-Plato-User": "alice"},
    )

    resp = authed_client.post(
        f"/api/v1/projects/{pid}/stages/results/run",
        json={"mode": "fast"},
        headers={"X-Plato-User": "alice"},
    )
    if resp.status_code == 403:
        detail = resp.json().get("detail", {})
        assert detail.get("code") != "approval_required"


def test_run_stage_auto_skip_bypasses_all_gates(
    authed_client: TestClient, tmp_project_root: Path
) -> None:
    """``auto_skip=True`` is the explicit escape hatch — no gate fires
    even when every upstream stage is unapproved."""
    pid = _create_project(authed_client)
    # Mark all three gates as done.
    for stage in ("idea", "literature", "method"):
        _mark_stage_done(tmp_project_root, "alice", pid, stage)
    authed_client.put(
        f"/api/v1/projects/{pid}/approvals",
        json={"per_stage": {}, "auto_skip": True},
        headers={"X-Plato-User": "alice"},
    )

    resp = authed_client.post(
        f"/api/v1/projects/{pid}/stages/paper/run",
        json={"mode": "fast"},
        headers={"X-Plato-User": "alice"},
    )
    if resp.status_code == 403:
        detail = resp.json().get("detail", {})
        assert detail.get("code") != "approval_required"


def test_run_stage_does_not_block_when_gate_not_done(
    authed_client: TestClient,
) -> None:
    """If idea hasn't run yet, it can't block downstream — the user is
    perfectly within their rights to launch literature with no idea."""
    pid = _create_project(authed_client)
    # Don't mark idea as done — its status stays "empty".

    resp = authed_client.post(
        f"/api/v1/projects/{pid}/stages/literature/run",
        json={"mode": "fast"},
        headers={"X-Plato-User": "alice"},
    )
    if resp.status_code == 403:
        detail = resp.json().get("detail", {})
        assert detail.get("code") != "approval_required"


def test_run_stage_blocks_method_when_literature_unapproved(
    authed_client: TestClient, tmp_project_root: Path
) -> None:
    """Second-tier gate: literature blocks {method, results, paper,
    referee}. Idea also blocks but the loop returns the FIRST blocking
    gate, so when idea=approved + literature=pending the response
    points at literature."""
    pid = _create_project(authed_client)
    _mark_stage_done(tmp_project_root, "alice", pid, "idea")
    _mark_stage_done(tmp_project_root, "alice", pid, "literature")
    authed_client.put(
        f"/api/v1/projects/{pid}/approvals",
        json={"per_stage": {"idea": "approved"}, "auto_skip": False},
        headers={"X-Plato-User": "alice"},
    )

    resp = authed_client.post(
        f"/api/v1/projects/{pid}/stages/method/run",
        json={"mode": "fast"},
        headers={"X-Plato-User": "alice"},
    )
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert detail["code"] == "approval_required"
    assert detail["blocking_gate"] == "literature"
