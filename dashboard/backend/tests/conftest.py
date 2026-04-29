"""Pytest fixtures for the dashboard backend smoke tests.

The fixtures aim for fast, deterministic tests:

* ``tmp_project_root`` redirects ``Settings.project_root`` (and the keys
  store path) at a per-test temp directory via ``PLATO_*`` env vars.
* ``client`` builds a fresh FastAPI ``TestClient`` from ``create_app``.
* ``async_client`` returns an ``httpx.AsyncClient`` bound to the same app
  via ASGI transport — used by the SSE tests so we can read the stream
  in-process without spinning up uvicorn.
* ``_reset_runs`` (autouse) wipes the in-memory active-run / task tables
  between tests so the concurrency cap and run-list endpoints start
  clean every time.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator, Iterator

import httpx
import pytest

# Ensure src/ is importable when running ``pytest`` straight from the
# backend directory, in case the package wasn't installed editable.
import sys

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture
def tmp_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect Settings.project_root + keys_path to a temp directory.

    ``Settings`` reads env vars on every ``get_settings()`` call (no
    lru_cache), so setting ``PLATO_PROJECT_ROOT`` is enough.
    """
    proj_root = tmp_path / "projects"
    keys_path = tmp_path / "keys.json"
    proj_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PLATO_PROJECT_ROOT", str(proj_root))
    monkeypatch.setenv("PLATO_KEYS_PATH", str(keys_path))
    # Default each test to local mode — individual tests opt into demo.
    monkeypatch.delenv("PLATO_DEMO_MODE", raising=False)
    return proj_root


@pytest.fixture(autouse=True)
def _reset_runs() -> Iterator[None]:
    """Clear the in-memory run registry between tests."""
    from plato_dashboard.worker import run_manager

    run_manager._active_runs.clear()
    run_manager._run_tasks.clear()
    run_manager._subprocesses.clear()
    yield
    run_manager._active_runs.clear()
    run_manager._run_tasks.clear()
    run_manager._subprocesses.clear()


@pytest.fixture(autouse=True)
def _reset_event_bus() -> Iterator[None]:
    """Reset the global EventBus between tests so SSE channels are clean."""
    from plato_dashboard.events import bus as bus_mod

    bus_mod._bus = None
    yield
    bus_mod._bus = None


@pytest.fixture
def client(tmp_project_root: Path):
    """A synchronous ``TestClient`` over a freshly-built app."""
    from fastapi.testclient import TestClient
    from plato_dashboard.api.server import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def async_client(tmp_project_root: Path) -> AsyncIterator[httpx.AsyncClient]:
    """Async client wired via httpx.ASGITransport — no real socket needed."""
    from plato_dashboard.api.server import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
