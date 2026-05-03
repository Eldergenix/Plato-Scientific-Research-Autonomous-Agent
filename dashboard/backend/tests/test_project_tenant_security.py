"""Iter-24 security tests: cross-tenant project access is refused.

These tests pin the contract added in iter-24:

1. ``Project.user_id`` is set on creation from ``X-Plato-User``.
2. Every project-level endpoint refuses cross-tenant reads/writes via
   ``_enforce_project_tenant``:
   - ``GET /projects/{pid}``
   - ``DELETE /projects/{pid}``
   - ``GET /projects/{pid}/state/{stage}``
   - ``PUT /projects/{pid}/state/{stage}``
   - ``POST /projects/{pid}/stages/{stage}/run``
   - ``GET /projects/{pid}/runs``
   - ``GET /projects/{pid}/plots``
   - ``GET /projects/{pid}/files/{relpath}``
3. ``get_file`` rejects path-prefix-collision attacks (``/foo/12``
   prefix-matching ``/foo/123``) by using ``Path.relative_to`` instead
   of ``str.startswith``.

The suite runs with ``PLATO_DASHBOARD_AUTH_REQUIRED=1`` so the strict
matrix is exercised; legacy single-user mode is covered by the
existing dashboard test suite.
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
    """Spin up a TestClient with PLATO_DASHBOARD_AUTH_REQUIRED=1."""
    monkeypatch.setenv(AUTH_REQUIRED_ENV, "1")
    app = create_app()
    with TestClient(app) as c:
        yield c


def _create_project_as(client: TestClient, user: str, name: str = "p") -> str:
    resp = client.post(
        "/api/v1/projects",
        json={"name": name},
        headers={"X-Plato-User": user},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user_id"] == user, "Project must record the creator's user_id"
    return body["id"]


# --- Project bind / read ---------------------------------------------------

def test_create_project_writes_user_id(authed_client: TestClient) -> None:
    pid = _create_project_as(authed_client, "alice")
    # Read it back as alice to confirm the user_id round-trips.
    resp = authed_client.get(f"/api/v1/projects/{pid}", headers={"X-Plato-User": "alice"})
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "alice"


def test_get_project_refuses_cross_tenant(authed_client: TestClient) -> None:
    pid = _create_project_as(authed_client, "alice")
    resp = authed_client.get(f"/api/v1/projects/{pid}", headers={"X-Plato-User": "bob"})
    assert resp.status_code in (403, 404)


def test_delete_project_refuses_cross_tenant(authed_client: TestClient) -> None:
    pid = _create_project_as(authed_client, "alice")
    resp = authed_client.delete(
        f"/api/v1/projects/{pid}", headers={"X-Plato-User": "bob"}
    )
    assert resp.status_code in (403, 404)


# --- Stage IO --------------------------------------------------------------

def test_read_stage_refuses_cross_tenant(authed_client: TestClient) -> None:
    pid = _create_project_as(authed_client, "alice")
    resp = authed_client.get(
        f"/api/v1/projects/{pid}/state/idea", headers={"X-Plato-User": "bob"}
    )
    assert resp.status_code in (403, 404)


def test_write_stage_refuses_cross_tenant(authed_client: TestClient) -> None:
    pid = _create_project_as(authed_client, "alice")
    resp = authed_client.put(
        f"/api/v1/projects/{pid}/state/idea",
        json={"markdown": "evil"},
        headers={"X-Plato-User": "bob"},
    )
    assert resp.status_code in (403, 404)


# --- Run lifecycle ---------------------------------------------------------

def test_run_stage_refuses_cross_tenant(authed_client: TestClient) -> None:
    """The CRITICAL one: alice can't launch a run inside bob's project."""
    pid = _create_project_as(authed_client, "alice")
    resp = authed_client.post(
        f"/api/v1/projects/{pid}/stages/idea/run",
        json={"mode": "fast"},
        headers={"X-Plato-User": "bob"},
    )
    assert resp.status_code in (403, 404), (
        f"run_stage must reject cross-tenant launches; got {resp.status_code} {resp.text}"
    )


def test_list_runs_refuses_cross_tenant(authed_client: TestClient) -> None:
    pid = _create_project_as(authed_client, "alice")
    resp = authed_client.get(
        f"/api/v1/projects/{pid}/runs", headers={"X-Plato-User": "bob"}
    )
    assert resp.status_code in (403, 404)


def test_list_plots_refuses_cross_tenant(authed_client: TestClient) -> None:
    pid = _create_project_as(authed_client, "alice")
    resp = authed_client.get(
        f"/api/v1/projects/{pid}/plots", headers={"X-Plato-User": "bob"}
    )
    assert resp.status_code in (403, 404)


# --- get_file: tenant + path traversal ------------------------------------

def test_get_file_refuses_cross_tenant(authed_client: TestClient) -> None:
    pid = _create_project_as(authed_client, "alice")
    resp = authed_client.get(
        f"/api/v1/projects/{pid}/files/meta.json",
        headers={"X-Plato-User": "bob"},
    )
    assert resp.status_code in (403, 404)


def test_get_file_rejects_path_traversal(authed_client: TestClient) -> None:
    """``../`` segments must be blocked even when alice owns the project."""
    pid = _create_project_as(authed_client, "alice")
    resp = authed_client.get(
        f"/api/v1/projects/{pid}/files/../../etc/passwd",
        headers={"X-Plato-User": "alice"},
    )
    # The 403 / 404 split depends on whether the ``..`` resolves to a
    # path that exists outside the project root; either is acceptable
    # so long as the file is not served.
    assert resp.status_code in (403, 404)
    assert b"root:" not in resp.content


def test_get_file_rejects_path_prefix_collision(
    authed_client: TestClient, tmp_project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Iter-24: ``str.startswith`` would have allowed ``proj_12`` to read
    ``proj_123``'s files because ``"proj_123/foo".startswith("proj_12")``
    is True. ``Path.relative_to`` correctly distinguishes them.

    Set up: alice owns ``proj_12`` AND ``proj_123``. She legitimately
    queries her own ``proj_12`` for a path that happens to look like
    ``../proj_123/foo`` — the resolved target is outside ``proj_12``,
    so the response must NOT serve ``proj_123``'s file.
    """
    pid_short = _create_project_as(authed_client, "alice", name="short")
    pid_long = _create_project_as(authed_client, "alice", name="long")

    # Plant a file in the long project that the short-project handler
    # would return if the prefix-collision bug were present.
    long_user_root = tmp_project_root.parent / "users" / "alice" / pid_long
    long_user_root.mkdir(parents=True, exist_ok=True)
    secret = long_user_root / "secret.txt"
    secret.write_text("this should never leak across projects")

    # The handler resolves to ``<users/alice>/<pid_short>``. A relpath
    # of ``../<pid_long>/secret.txt`` resolves to the long project's
    # secret.txt — outside ``pid_short``'s root.
    resp = authed_client.get(
        f"/api/v1/projects/{pid_short}/files/../{pid_long}/secret.txt",
        headers={"X-Plato-User": "alice"},
    )
    assert resp.status_code in (403, 404)
    assert b"this should never leak" not in resp.content


# --- legacy un-tenanted projects ------------------------------------------

def test_legacy_project_without_user_id_is_403_in_required_mode(
    authed_client: TestClient, tmp_project_root: Path
) -> None:
    """A pre-iter-24 project (meta.json without user_id) must fail-closed
    in required-mode — we can't prove ownership."""
    legacy_dir = tmp_project_root / "users" / "alice" / "legacy_project"
    legacy_dir.mkdir(parents=True)
    meta = {
        "id": "legacy_project",
        "name": "pre-iter-24 project",
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
        "journal": "NONE",
        "stages": {
            "data": {"id": "data", "label": "Data", "status": "empty"},
            "idea": {"id": "idea", "label": "Idea", "status": "empty"},
            "literature": {"id": "literature", "label": "Lit", "status": "empty"},
            "method": {"id": "method", "label": "Method", "status": "empty"},
            "results": {"id": "results", "label": "Results", "status": "empty"},
            "paper": {"id": "paper", "label": "Paper", "status": "empty"},
            "referee": {"id": "referee", "label": "Referee", "status": "empty"},
        },
        # NB: no user_id field — legacy shape.
    }
    (legacy_dir / "meta.json").write_text(json.dumps(meta))

    resp = authed_client.get(
        "/api/v1/projects/legacy_project", headers={"X-Plato-User": "alice"}
    )
    # In required-mode (set by the fixture), no user_id is fail-closed.
    assert resp.status_code == 403
