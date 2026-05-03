"""Iter-26 — tests for the /api/v1/projects/{pid}/cost_caps endpoint
+ the run_stage budget_exceeded gate.

Pin three contracts:

1. GET defaults to ``{budget_cents: null, stop_on_exceed: false}`` for
   projects with no cap configured.
2. PUT round-trips through ``meta.json`` so the next GET returns the
   stored shape.
3. ``POST /projects/{pid}/stages/{stage}/run`` refuses with 403
   ``budget_exceeded`` when ``stop_on_exceed=True`` AND
   ``project.total_cost_cents >= budget_cents``.

Tenant scoping (cross-tenant 403s, missing-X-Plato-User 401s) is
covered by the iter-24 ``test_project_tenant_security.py`` suite for
every endpoint that uses ``_enforce_project_tenant`` — including this
one. We keep the cost-cap suite focused on the cap-specific contract.
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
    tmp_project_root: Path,  # noqa: ARG001 — fixture sets project_root
    monkeypatch: pytest.MonkeyPatch,
):
    """TestClient with PLATO_DASHBOARD_AUTH_REQUIRED=1."""
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


def test_get_returns_default_no_cap_shape_for_fresh_project(
    authed_client: TestClient,
) -> None:
    pid = _create_project(authed_client)
    resp = authed_client.get(
        f"/api/v1/projects/{pid}/cost_caps", headers={"X-Plato-User": "alice"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"budget_cents": None, "stop_on_exceed": False}


def test_put_then_get_round_trips_through_meta_json(
    authed_client: TestClient, tmp_project_root: Path
) -> None:
    pid = _create_project(authed_client)
    # PUT a cap.
    put_resp = authed_client.put(
        f"/api/v1/projects/{pid}/cost_caps",
        json={"budget_cents": 5000, "stop_on_exceed": True},
        headers={"X-Plato-User": "alice"},
    )
    assert put_resp.status_code == 200
    assert put_resp.json() == {"budget_cents": 5000, "stop_on_exceed": True}

    # GET reads it back.
    get_resp = authed_client.get(
        f"/api/v1/projects/{pid}/cost_caps", headers={"X-Plato-User": "alice"}
    )
    assert get_resp.json() == {"budget_cents": 5000, "stop_on_exceed": True}

    # And it's actually on disk in meta.json — tenant-namespaced under
    # users/alice/<pid>/.
    meta_path = tmp_project_root / "users" / "alice" / pid / "meta.json"
    assert meta_path.is_file()
    meta = json.loads(meta_path.read_text())
    assert meta["cost_caps"] == {"budget_cents": 5000, "stop_on_exceed": True}


def test_put_with_null_budget_clears_the_cap(
    authed_client: TestClient,
) -> None:
    pid = _create_project(authed_client)
    authed_client.put(
        f"/api/v1/projects/{pid}/cost_caps",
        json={"budget_cents": 1000, "stop_on_exceed": True},
        headers={"X-Plato-User": "alice"},
    )
    # Then clear.
    resp = authed_client.put(
        f"/api/v1/projects/{pid}/cost_caps",
        json={"budget_cents": None, "stop_on_exceed": False},
        headers={"X-Plato-User": "alice"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"budget_cents": None, "stop_on_exceed": False}


def test_put_rejects_negative_budget(authed_client: TestClient) -> None:
    """Pydantic ge=0 on budget_cents must reject negatives at the schema layer."""
    pid = _create_project(authed_client)
    resp = authed_client.put(
        f"/api/v1/projects/{pid}/cost_caps",
        json={"budget_cents": -100, "stop_on_exceed": False},
        headers={"X-Plato-User": "alice"},
    )
    # Pydantic validation error → 422 from FastAPI.
    assert resp.status_code == 422


def test_run_stage_blocks_when_budget_exceeded_and_stop_on_exceed(
    authed_client: TestClient, tmp_project_root: Path
) -> None:
    """The CRITICAL one: run_stage refuses to launch when the project
    is already at-or-above budget AND stop_on_exceed is True."""
    pid = _create_project(authed_client)

    # Set a cap, then bump total_cost_cents on disk to simulate the
    # project having already burned its budget.
    authed_client.put(
        f"/api/v1/projects/{pid}/cost_caps",
        json={"budget_cents": 1000, "stop_on_exceed": True},
        headers={"X-Plato-User": "alice"},
    )
    meta_path = tmp_project_root / "users" / "alice" / pid / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["total_cost_cents"] = 1500  # over the 1000-cent cap
    meta_path.write_text(json.dumps(meta))

    resp = authed_client.post(
        f"/api/v1/projects/{pid}/stages/idea/run",
        json={"mode": "fast"},
        headers={"X-Plato-User": "alice"},
    )
    assert resp.status_code == 403, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "budget_exceeded"
    assert detail["spent_cents"] == 1500
    assert detail["budget_cents"] == 1000


def test_run_stage_allows_launch_when_under_budget(
    authed_client: TestClient, tmp_project_root: Path
) -> None:
    """When stop_on_exceed=True AND spend < budget, the gate must NOT fire."""
    pid = _create_project(authed_client)
    authed_client.put(
        f"/api/v1/projects/{pid}/cost_caps",
        json={"budget_cents": 1000, "stop_on_exceed": True},
        headers={"X-Plato-User": "alice"},
    )
    meta_path = tmp_project_root / "users" / "alice" / pid / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["total_cost_cents"] = 800  # under budget
    meta_path.write_text(json.dumps(meta))

    resp = authed_client.post(
        f"/api/v1/projects/{pid}/stages/idea/run",
        json={"mode": "fast"},
        headers={"X-Plato-User": "alice"},
    )
    # The downstream worker may fail (no Plato install, missing keys),
    # but it must NOT fail with budget_exceeded — that's the iter-26
    # gate's contract. Anything other than 403 budget_exceeded is fine.
    if resp.status_code == 403:
        detail = resp.json().get("detail", {})
        assert detail.get("code") != "budget_exceeded", (
            f"run_stage incorrectly fired budget_exceeded when spend ({800}) "
            f"< budget ({1000}). Detail: {detail}"
        )


def test_run_stage_allows_launch_when_stop_on_exceed_false(
    authed_client: TestClient, tmp_project_root: Path
) -> None:
    """``stop_on_exceed=False`` is monitor-only: spend > budget must NOT block."""
    pid = _create_project(authed_client)
    authed_client.put(
        f"/api/v1/projects/{pid}/cost_caps",
        json={"budget_cents": 1000, "stop_on_exceed": False},
        headers={"X-Plato-User": "alice"},
    )
    meta_path = tmp_project_root / "users" / "alice" / pid / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["total_cost_cents"] = 5000  # way over
    meta_path.write_text(json.dumps(meta))

    resp = authed_client.post(
        f"/api/v1/projects/{pid}/stages/idea/run",
        json={"mode": "fast"},
        headers={"X-Plato-User": "alice"},
    )
    if resp.status_code == 403:
        detail = resp.json().get("detail", {})
        assert detail.get("code") != "budget_exceeded", (
            "stop_on_exceed=False must be monitor-only; budget_exceeded "
            "must NOT fire."
        )


def test_run_stage_allows_launch_when_no_cap_configured(
    authed_client: TestClient,
) -> None:
    """No cost_caps on the project = no gate."""
    pid = _create_project(authed_client)
    # No PUT to /cost_caps — cap stays None.
    resp = authed_client.post(
        f"/api/v1/projects/{pid}/stages/idea/run",
        json={"mode": "fast"},
        headers={"X-Plato-User": "alice"},
    )
    if resp.status_code == 403:
        detail = resp.json().get("detail", {})
        assert detail.get("code") != "budget_exceeded"
