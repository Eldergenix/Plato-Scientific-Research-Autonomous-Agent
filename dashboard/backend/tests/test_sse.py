"""SSE transport tests.

We exercise the ``GET /api/v1/projects/{pid}/runs/{run_id}/events``
endpoint by directly publishing into the singleton ``EventBus`` rather
than triggering a real run — we want to test the transport, not the
executor.

httpx's ``ASGITransport`` buffers the entire response body before
returning, so we can't stream-test through it. Instead each test boots
a uvicorn server in a background thread on an ephemeral port and
connects via real HTTP.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import threading
import time
from typing import AsyncIterator

import httpx
import pytest
import uvicorn


pytestmark = pytest.mark.asyncio


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _BackgroundServer:
    """Run uvicorn on a background thread; expose the chosen port."""

    def __init__(self, app) -> None:
        self.port = _free_port()
        config = uvicorn.Config(
            app, host="127.0.0.1", port=self.port, log_level="warning", lifespan="on"
        )
        self.server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> None:
        self._thread.start()
        # Wait for uvicorn to start accepting connections.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if self.server.started:
                return
            time.sleep(0.05)
        raise RuntimeError("uvicorn failed to start within 5s")

    def stop(self) -> None:
        self.server.should_exit = True
        self._thread.join(timeout=5.0)


@contextlib.asynccontextmanager
async def _running_app(tmp_project_root) -> AsyncIterator[_BackgroundServer]:
    """Boot a fresh ``create_app()`` in a background uvicorn thread."""
    from plato_dashboard.api.server import create_app

    app = create_app()
    bg = _BackgroundServer(app)
    bg.start()
    try:
        yield bg
    finally:
        bg.stop()


async def _read_event(byte_iter) -> dict:
    """Read one ``data:`` line off an SSE stream and return the parsed event."""
    buf = b""
    async for chunk in byte_iter:
        buf += chunk
        while b"\n\n" in buf:
            block, buf = buf.split(b"\n\n", 1)
            for line in block.split(b"\n"):
                if line.startswith(b"data: "):
                    return json.loads(line[len(b"data: "):])
    raise AssertionError("stream closed before any data: event")


async def test_sse_publishes_arbitrary_events_to_subscriber(
    tmp_project_root,
) -> None:
    async with _running_app(tmp_project_root) as bg:
        pid = "prj_dummy"
        run_id = "run_sse_a"
        url = f"http://127.0.0.1:{bg.port}/api/v1/projects/{pid}/runs/{run_id}/events"

        async with httpx.AsyncClient(timeout=5.0) as client:
            async with client.stream("GET", url) as resp:
                assert resp.status_code == 200
                assert resp.headers["content-type"].startswith("text/event-stream")

                # Give the server's bus.subscribe() a tick to register itself
                # before we publish.
                await asyncio.sleep(0.2)

                # Publish via the same singleton bus the server is using.
                from plato_dashboard.events.bus import get_bus
                bus = get_bus()
                await bus.publish(
                    f"run:{run_id}",
                    {"kind": "log.line", "text": "hello", "run_id": run_id},
                )
                await bus.publish(
                    f"run:{run_id}",
                    {"kind": "stage.finished", "status": "succeeded", "run_id": run_id},
                )

                first = await asyncio.wait_for(
                    _read_event(resp.aiter_bytes()), timeout=3.0
                )
                assert first["kind"] == "log.line"
                assert first["text"] == "hello"


async def test_sse_stream_closes_after_stage_finished(
    tmp_project_root,
) -> None:
    """After publishing ``stage.finished`` the server should end the stream."""
    async with _running_app(tmp_project_root) as bg:
        pid = "prj_dummy"
        run_id = "run_sse_b"
        url = f"http://127.0.0.1:{bg.port}/api/v1/projects/{pid}/runs/{run_id}/events"

        async with httpx.AsyncClient(timeout=5.0) as client:
            async with client.stream("GET", url) as resp:
                assert resp.status_code == 200

                await asyncio.sleep(0.2)
                from plato_dashboard.events.bus import get_bus
                bus = get_bus()
                await bus.publish(
                    f"run:{run_id}",
                    {"kind": "stage.finished", "status": "succeeded", "run_id": run_id},
                )

                async def _drain() -> int:
                    count = 0
                    async for chunk in resp.aiter_bytes():
                        count += len(chunk)
                    return count

                # If the server didn't auto-close on stage.finished, this hangs.
                await asyncio.wait_for(_drain(), timeout=3.0)
