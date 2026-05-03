"""Loop-control API smoke tests.

We never let the real :class:`ResearchLoop` touch git or write a runs.tsv —
the loop builder is monkeypatched to produce a tiny stub that exposes the
counters the snapshot logic reads. Tests stay sub-second.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class _FakeLoop:
    """Stand-in for ResearchLoop.

    Mirrors the interface ``LoopRecord.snapshot`` reads (``_iter``,
    ``_kept``, ``_discarded``, ``_best_composite``, ``project_dir``,
    ``tsv_path``) and offers a ``run`` coroutine the supervisor can
    cancel cleanly.
    """

    def __init__(self, *, project_dir: str, tsv_path: Path):
        self.project_dir = Path(project_dir)
        self.tsv_path = tsv_path
        self._iter = 0
        self._kept = 0
        self._discarded = 0
        self._best_composite = float("-inf")
        self.run_calls = 0

    async def run(self, _factory, _score_fn):
        self.run_calls += 1
        # Sleep long enough that tests can observe "running" before the
        # coroutine returns naturally.
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        return {
            "iterations": self._iter,
            "kept": self._kept,
            "discarded": self._discarded,
            "best_composite": 0.0,
            "tsv_path": str(self.tsv_path),
        }


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def loop_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """Build a minimal FastAPI app with only the loop router mounted.

    The test app stays decoupled from server.py so the spec's "do not
    modify api/server.py" constraint holds. We also patch ``_build_loop``
    to return our :class:`_FakeLoop`, keyed off the project_dir so each
    test can find its loop without leaking state between tests.
    """
    from plato_dashboard.api import loop_control

    loop_control.reset_registry()

    def _fake_build(req):
        # Use a per-request tsv path so multiple loops in one test don't collide.
        tsv = tmp_path / f"runs-{req.project_dir.replace('/', '_')}.tsv"
        return _FakeLoop(project_dir=req.project_dir, tsv_path=tsv)

    monkeypatch.setattr(loop_control, "_build_loop", _fake_build)

    app = FastAPI()
    app.include_router(loop_control.router)

    # Make sure tests run in local mode unless they opt into auth.
    monkeypatch.delenv("PLATO_AUTH", raising=False)
    monkeypatch.delenv("PLATO_DEMO_MODE", raising=False)

    yield app
    loop_control.reset_registry()


@pytest.fixture
def client(loop_app: FastAPI) -> TestClient:
    with TestClient(loop_app) as c:
        yield c


@pytest.fixture
async def async_client(loop_app: FastAPI):
    transport = httpx.ASGITransport(app=loop_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def _start_payload(project_dir: str = "/tmp/plato-fake") -> dict:
    return {
        "project_dir": project_dir,
        "max_iters": 3,
        "time_budget_hours": 1.0,
        "max_cost_usd": 5.0,
        "branch_prefix": "plato-runs",
    }


def test_start_returns_loop_id_and_running(client: TestClient) -> None:
    resp = client.post("/api/v1/loop/start", json=_start_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert isinstance(body["loop_id"], str)
    assert len(body["loop_id"]) == 12  # uuid.uuid4().hex[:12]
    assert body["status"] == "running"
    assert body["iterations"] == 0


async def test_start_schedules_research_loop(
    async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The supervisor must actually call ``ResearchLoop.run``."""
    from plato_dashboard.api import loop_control

    captured: list[_FakeLoop] = []

    def _capturing_build(req):
        loop = _FakeLoop(
            project_dir=req.project_dir,
            tsv_path=Path("/tmp/_unused.tsv"),
        )
        captured.append(loop)
        return loop

    monkeypatch.setattr(loop_control, "_build_loop", _capturing_build)

    resp = await async_client.post("/api/v1/loop/start", json=_start_payload())
    assert resp.status_code == 201

    # Yield once so the supervisor task can enter `await loop.run`.
    await asyncio.sleep(0.01)
    assert len(captured) == 1
    assert captured[0].run_calls == 1


def test_status_before_completion_returns_running(client: TestClient) -> None:
    started = client.post("/api/v1/loop/start", json=_start_payload()).json()
    resp = client.get(f"/api/v1/loop/{started['loop_id']}/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["loop_id"] == started["loop_id"]
    assert body["status"] == "running"


def test_stop_cancels_task_and_returns_stopped(client: TestClient) -> None:
    started = client.post("/api/v1/loop/start", json=_start_payload()).json()
    resp = client.post(f"/api/v1/loop/{started['loop_id']}/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"


def test_stop_is_idempotent(client: TestClient) -> None:
    started = client.post("/api/v1/loop/start", json=_start_payload()).json()
    first = client.post(f"/api/v1/loop/{started['loop_id']}/stop").json()
    second = client.post(f"/api/v1/loop/{started['loop_id']}/stop").json()
    assert first["status"] == "stopped"
    assert second["status"] == "stopped"
    assert first["loop_id"] == second["loop_id"]


def test_status_unknown_loop_404(client: TestClient) -> None:
    resp = client.get("/api/v1/loop/does-not-exist/status")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "loop_not_found"


def test_stop_unknown_loop_404(client: TestClient) -> None:
    resp = client.post("/api/v1/loop/nope/stop")
    assert resp.status_code == 404


def test_tsv_unknown_loop_404(client: TestClient) -> None:
    resp = client.get("/api/v1/loop/nope/tsv")
    assert resp.status_code == 404


def test_tsv_returns_empty_rows_when_file_missing(client: TestClient) -> None:
    started = client.post("/api/v1/loop/start", json=_start_payload()).json()
    resp = client.get(f"/api/v1/loop/{started['loop_id']}/tsv")
    assert resp.status_code == 200
    assert resp.json() == {"rows": []}


def test_tsv_returns_parsed_rows(client: TestClient, tmp_path: Path) -> None:
    """When the loop has written a runs.tsv, /tsv must parse and return it."""
    started = client.post("/api/v1/loop/start", json=_start_payload()).json()

    # Reach into the registry and write a tsv at the loop's tsv_path.
    from plato_dashboard.api import loop_control

    record = loop_control._LOOPS[started["loop_id"]]
    tsv = Path(record.loop.tsv_path)
    tsv.parent.mkdir(parents=True, exist_ok=True)
    tsv.write_text(
        "iter\ttimestamp\tcomposite\tstatus\tdescription\n"
        "1\t2026-04-29T00:00:00+00:00\t0.5\tkeep\tcomposite improved\n"
        "2\t2026-04-29T00:01:00+00:00\t0.3\tdiscard\tcomposite worse\n"
    )

    resp = client.get(f"/api/v1/loop/{started['loop_id']}/tsv")
    assert resp.status_code == 200
    rows = resp.json()["rows"]
    assert len(rows) == 2
    assert rows[0] == {
        "iter": 1,
        "timestamp": "2026-04-29T00:00:00+00:00",
        "composite": 0.5,
        "status": "keep",
        "description": "composite improved",
    }
    assert rows[1]["status"] == "discard"


def test_list_returns_started_loops(client: TestClient) -> None:
    a = client.post("/api/v1/loop/start", json=_start_payload("/tmp/a")).json()
    b = client.post("/api/v1/loop/start", json=_start_payload("/tmp/b")).json()

    resp = client.get("/api/v1/loop")
    assert resp.status_code == 200
    ids = {row["loop_id"] for row in resp.json()}
    assert {a["loop_id"], b["loop_id"]} <= ids


def test_auth_required_blocks_missing_header(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """In auth-required mode, every endpoint requires X-Plato-User."""
    monkeypatch.setenv("PLATO_AUTH", "enabled")

    # Rebuild the app inside the auth-required env.
    from plato_dashboard.api import loop_control

    loop_control.reset_registry()
    monkeypatch.setattr(
        loop_control,
        "_build_loop",
        lambda req: _FakeLoop(project_dir=req.project_dir, tsv_path=tmp_path / "r.tsv"),
    )
    app = FastAPI()
    app.include_router(loop_control.router)

    with TestClient(app) as c:
        resp = c.post("/api/v1/loop/start", json=_start_payload())
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "auth_required"

        # With the header it goes through.
        resp_ok = c.post(
            "/api/v1/loop/start",
            json=_start_payload(),
            headers={"X-Plato-User": "alice"},
        )
        assert resp_ok.status_code == 201

    loop_control.reset_registry()


def test_auth_required_blocks_other_tenants_loops(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Bob can't see or stop a loop alice started."""
    monkeypatch.setenv("PLATO_AUTH", "enabled")

    from plato_dashboard.api import loop_control

    loop_control.reset_registry()
    monkeypatch.setattr(
        loop_control,
        "_build_loop",
        lambda req: _FakeLoop(project_dir=req.project_dir, tsv_path=tmp_path / "r.tsv"),
    )
    app = FastAPI()
    app.include_router(loop_control.router)

    with TestClient(app) as c:
        started = c.post(
            "/api/v1/loop/start",
            json=_start_payload(),
            headers={"X-Plato-User": "alice"},
        ).json()

        resp = c.get(
            f"/api/v1/loop/{started['loop_id']}/status",
            headers={"X-Plato-User": "bob"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "loop_not_owned"

    loop_control.reset_registry()
