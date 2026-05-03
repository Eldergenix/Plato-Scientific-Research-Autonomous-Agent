"""End-to-end coverage for the live log-streaming pipeline.

Wave 5 wired ``run_manager`` → ``EventBus`` → SSE
(``GET /projects/{pid}/runs/{run_id}/events``). Existing tests cover the
slices in isolation (``test_sse.py`` for the transport,
``test_run_manager.py`` for the supervisor). This module drives the
whole stack from a real client so we catch breakage that only shows up
at the boundary — fan-out ordering, subscriber cleanup on disconnect,
queue-full backpressure, run-id validation, and the multi-tenant gate
guarding the SSE endpoint.

Two transports are used:

* ``TestClient`` (synchronous, ASGI in-process) for happy-path,
  backpressure, invalid-run-id, and tenant-boundary tests. We publish
  into the EventBus on TestClient's loop via
  ``client.portal.call(...)`` — the bus's ``asyncio.Queue`` instances
  are loop-bound, so a bare ``asyncio.run`` from the test thread would
  push onto a queue no subscriber is awaiting on.

* A real ``uvicorn`` server in a background thread for the
  client-disconnect test. ``ASGITransport`` does NOT propagate transport
  closure to the SSE generator, so the only way to verify subscriber
  cleanup on abrupt disconnect is over a real socket. This mirrors the
  pattern already established in ``test_sse.py``.

Each test caps real wall time well under 2s. We yield control between
publishes with ``asyncio.sleep(0)``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import threading
import time
from pathlib import Path
from typing import Iterator

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from plato_dashboard.events.bus import EventBus, get_bus


# --------------------------------------------------------------------------- #
# Helpers — TestClient transport
# --------------------------------------------------------------------------- #
def _create_project(client: TestClient, name: str = "E2E") -> str:
    return client.post("/api/v1/projects", json={"name": name}).json()["id"]


def _publish_via_portal(client: TestClient, channel: str, event: dict) -> None:
    """Publish onto the EventBus on TestClient's loop.

    The SSE handler subscribes on the FastAPI worker loop. ``get_bus()`` is a
    process-global singleton, but the asyncio queues inside it are bound to
    the loop that called ``put_nowait``. Crossing threads with bare
    ``asyncio.run`` would create a fresh loop and the publish would land on
    a queue that no subscriber is waiting on, so events would silently
    vanish. ``client.portal.call`` schedules the coroutine on the live
    loop, which is the only place that works.
    """

    async def _do() -> None:
        bus: EventBus = get_bus()
        await bus.publish(channel, event)
        # Yield once so the SSE generator's ``await q.get()`` sees the
        # item before the test checks for it.
        await asyncio.sleep(0)

    client.portal.call(_do)


def _read_data_frames(stream_resp, max_events: int, timeout: float) -> list[dict]:
    """Drain SSE ``data:`` frames off ``stream_resp`` up to a max count.

    Stops early when the server closes the stream (``stage.finished``
    triggers that server-side). ``timeout`` bounds wall time so a hung
    stream doesn't wedge pytest.
    """
    out: list[dict] = []
    deadline = time.monotonic() + timeout
    for raw in stream_resp.iter_lines():
        if time.monotonic() > deadline:
            raise AssertionError(
                f"timed out after {timeout}s with {len(out)}/{max_events} events"
            )
        if not raw or raw.startswith(": "):
            # Blank line or SSE comment frame (initial ``: connected`` heartbeat).
            continue
        if raw.startswith("data: "):
            out.append(json.loads(raw[len("data: "):]))
            if len(out) >= max_events:
                break
    return out


@pytest.fixture
def channel_count(client: TestClient) -> "ChannelCounter":
    """Snapshot subscriber-count helpers for the singleton bus."""
    return ChannelCounter(client)


class ChannelCounter:
    """Inspect ``EventBus._channels`` from the test thread via the loop."""

    def __init__(self, client: TestClient) -> None:
        self._client = client

    def count(self, channel: str) -> int:
        async def _do() -> int:
            bus = get_bus()
            async with bus._lock:  # noqa: SLF001 — test introspection
                return len(bus._channels.get(channel, []))  # noqa: SLF001
        return self._client.portal.call(_do)


# --------------------------------------------------------------------------- #
# Helpers — real-uvicorn transport (only used by the disconnect test)
# --------------------------------------------------------------------------- #
def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _BackgroundServer:
    """Run uvicorn on a background thread; expose its chosen port.

    Mirrors the helper in ``test_sse.py``. We need a real socket here
    because Starlette only signals SSE-generator cancellation on actual
    transport-close events; ``ASGITransport`` (used by ``TestClient``)
    skips that path.
    """

    def __init__(self, app) -> None:
        self.port = _free_port()
        config = uvicorn.Config(
            app, host="127.0.0.1", port=self.port, log_level="warning", lifespan="on"
        )
        self.server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> None:
        self._thread.start()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if self.server.started:
                return
            time.sleep(0.05)
        raise RuntimeError("uvicorn failed to start within 5s")

    def stop(self) -> None:
        self.server.should_exit = True
        self._thread.join(timeout=5.0)


@contextlib.contextmanager
def _live_server(tmp_project_root: Path):
    """Boot ``create_app()`` in a background uvicorn thread."""
    from plato_dashboard.api.server import create_app

    app = create_app()
    bg = _BackgroundServer(app)
    bg.start()
    try:
        yield bg
    finally:
        bg.stop()


# --------------------------------------------------------------------------- #
# Test cases
# --------------------------------------------------------------------------- #
def test_happy_path_full_event_pipeline(
    client: TestClient, channel_count: ChannelCounter
) -> None:
    """Mixed event stream traverses the bus and arrives in order on SSE.

    Publishes 3 ``stage.started`` + 5 ``log.line`` + 3 ``stage.finished``
    events on the same channel. The SSE handler closes the stream after
    the first ``stage.finished`` (see ``server.py`` —
    ``if evt.get("kind") == "stage.finished": return``), so the client
    receives the 3 + 5 + 1 = 9-event prefix in order. The other two
    ``stage.finished`` payloads are still successfully dispatched onto
    the bus (no exception raised), but their subscriber has unsubscribed
    by the time they land — which is the documented lifecycle.
    """
    pid = _create_project(client)
    run_id = "run_happy"
    channel = f"run:{run_id}"
    url = f"/api/v1/projects/{pid}/runs/{run_id}/events"

    received: list[dict] = []
    err: list[BaseException] = []

    def consumer() -> None:
        try:
            with client.stream("GET", url, timeout=2.0) as resp:
                assert resp.status_code == 200
                assert resp.headers["content-type"].startswith("text/event-stream")
                received.extend(_read_data_frames(resp, max_events=9, timeout=2.0))
        except BaseException as exc:  # noqa: BLE001
            err.append(exc)

    t = threading.Thread(target=consumer, daemon=True)
    t.start()

    # Wait for the subscriber to register on the bus before we publish.
    deadline = time.monotonic() + 2.0
    while channel_count.count(channel) == 0:
        if time.monotonic() > deadline:
            raise AssertionError("subscriber never registered on EventBus")
        time.sleep(0.02)

    published: list[dict] = []
    for i in range(3):
        evt = {"kind": "stage.started", "stage": f"stage_{i}", "run_id": run_id}
        published.append(evt)
        _publish_via_portal(client, channel, evt)
    for i in range(5):
        evt = {"kind": "log.line", "text": f"line {i}", "run_id": run_id}
        published.append(evt)
        _publish_via_portal(client, channel, evt)
    for i in range(3):
        evt = {
            "kind": "stage.finished",
            "stage": f"stage_{i}",
            "status": "succeeded",
            "run_id": run_id,
        }
        published.append(evt)
        _publish_via_portal(client, channel, evt)

    t.join(timeout=2.0)
    assert not t.is_alive(), "consumer thread did not finish in time"
    assert not err, f"consumer raised: {err[0]!r}"

    # Server closes after the first stage.finished → 3 + 5 + 1 = 9 events.
    assert len(received) == 9, f"expected 9 events before close, got {len(received)}"
    assert [e["kind"] for e in received[:3]] == ["stage.started"] * 3
    assert [e["kind"] for e in received[3:8]] == ["log.line"] * 5
    assert received[8]["kind"] == "stage.finished"
    # FIFO ordering: the first stage.finished received is for stage_0.
    assert received[8]["stage"] == "stage_0"
    assert len(published) == 11  # we did push all 11; only 9 made it pre-close


@pytest.mark.asyncio
async def test_client_disconnect_cleans_up_subscriber(tmp_project_root: Path) -> None:
    """Closing the connection mid-stream removes the queue from the bus.

    ``EventBus.subscribe`` registers a queue on entry and unregisters it
    in a ``finally:`` block when the generator exits. Verify that an
    abrupt client disconnect — followed by one wake-up publish — runs
    that finally and the channel's subscriber list returns to empty.

    Why a real uvicorn server: ``TestClient`` / ``ASGITransport`` does
    NOT propagate transport-close to the SSE generator. The only
    reliable way to test disconnect-cleanup in-process is over a real
    socket. The async-test + uvicorn pattern matches ``test_sse.py``.
    """
    with _live_server(tmp_project_root) as bg:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{bg.port}", timeout=5.0
        ) as client:
            pid = (
                await client.post("/api/v1/projects", json={"name": "Disco"})
            ).json()["id"]

            run_id = "run_disco"
            channel = f"run:{run_id}"
            url = f"/api/v1/projects/{pid}/runs/{run_id}/events"

            received: list[dict] = []
            async with client.stream("GET", url) as resp:
                assert resp.status_code == 200

                # Wait for the bus subscription to land. The bus singleton is
                # process-global; the SSE handler subscribes from uvicorn's
                # loop, but introspecting the channel list from this loop is
                # safe because ``len(list)`` is a snapshot.
                bus = get_bus()
                deadline = time.monotonic() + 2.0
                while True:
                    if bus._channels.get(channel):  # noqa: SLF001
                        break
                    if time.monotonic() > deadline:
                        raise AssertionError("subscriber never registered")
                    await asyncio.sleep(0.02)

                # Publish 3 events and read them off the wire.
                for i in range(3):
                    await bus.publish(
                        channel,
                        {"kind": "log.line", "text": f"x{i}", "run_id": run_id},
                    )

                buf = b""
                async for chunk in resp.aiter_bytes():
                    buf += chunk
                    while b"\n\n" in buf:
                        block, buf = buf.split(b"\n\n", 1)
                        for line in block.split(b"\n"):
                            if line.startswith(b"data: "):
                                received.append(json.loads(line[len(b"data: "):]))
                    if len(received) >= 3:
                        break
                # Exiting the ``async with client.stream`` block tears down the
                # response. httpx will release the connection on next use; the
                # surrounding ``async with httpx.AsyncClient`` (below, when we
                # exit it) closes the underlying socket, which uvicorn detects
                # as a disconnect and propagates as cancellation to the SSE
                # generator's task — that runs the finally block in
                # ``EventBus.subscribe``.

        # AsyncClient is now closed → underlying TCP socket closed →
        # uvicorn dispatches an ``http.disconnect`` ASGI message →
        # Starlette cancels the SSE generator → finally unsubscribes.
        # Wait for that to ripple through.
        bus = get_bus()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if not bus._channels.get(channel):  # noqa: SLF001
                break
            await asyncio.sleep(0.05)

        assert len(received) == 3
        remaining = len(bus._channels.get(channel, []))  # noqa: SLF001
        assert remaining == 0, (
            f"subscriber queue not removed after disconnect (still {remaining})"
        )


def test_slow_client_backpressure_drops_overflow(client: TestClient) -> None:
    """``EventBus.publish`` drops events when a subscriber's queue is full.

    The bus uses a bounded ``asyncio.Queue(maxsize=2048)`` per subscriber
    and silently discards on ``QueueFull`` so a slow consumer can't
    block the publisher (see ``events/bus.py``). We attach a tiny queue
    directly, fill it past the cap, and confirm ``publish`` returns
    cleanly without raising and that excess events are dropped.
    """

    async def _runner() -> tuple[int, asyncio.Queue]:
        bus = get_bus()
        ch = "run:run_backpressure"

        # Manually mimic EventBus.subscribe()'s queue registration.
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=4)
        async with bus._lock:  # noqa: SLF001
            bus._channels[ch].append(q)  # noqa: SLF001
        try:
            published_without_error = 0
            for i in range(20):
                await bus.publish(ch, {"kind": "log.line", "n": i})
                published_without_error += 1
                await asyncio.sleep(0)
            return published_without_error, q
        finally:
            async with bus._lock:  # noqa: SLF001
                if q in bus._channels.get(ch, []):  # noqa: SLF001
                    bus._channels[ch].remove(q)  # noqa: SLF001

    published, q = client.portal.call(_runner)

    # publish() never raises even when the queue is full.
    assert published == 20
    # Queue capped at 4 → at most 4 events landed; the rest were dropped.
    assert q.qsize() == 4


def test_invalid_run_id_subscribes_but_closes_quickly(
    client: TestClient, channel_count: ChannelCounter
) -> None:
    """Subscribing to a non-existent run id is allowed (SSE is fire-and-forget).

    In legacy single-user mode the SSE endpoint doesn't validate that
    the run exists in the in-memory registry — it just opens a channel
    and waits. This is by design: the worker publishes the first
    ``stage.started`` event before the run record is fully persisted,
    so the subscribe-before-start pattern needs to work for any run id.

    We confirm:

    1. The endpoint returns ``200`` (not 404 — that would break the
       subscribe-before-start pattern).
    2. Publishing a synthetic ``stage.finished`` causes the server to
       close the stream promptly, which is the documented exit
       condition.

    The spec allows either ``404`` or quick close; we assert the actual
    behaviour rather than fight it.
    """
    pid = _create_project(client)
    bogus_run = "run_does_not_exist_anywhere"
    channel = f"run:{bogus_run}"
    url = f"/api/v1/projects/{pid}/runs/{bogus_run}/events"

    received: list[dict] = []
    closed_at: list[float] = []

    def consumer() -> None:
        with client.stream("GET", url, timeout=2.0) as resp:
            assert resp.status_code == 200
            received.extend(_read_data_frames(resp, max_events=1, timeout=2.0))
        closed_at.append(time.monotonic())

    t = threading.Thread(target=consumer, daemon=True)
    t.start()

    deadline = time.monotonic() + 2.0
    while channel_count.count(channel) == 0:
        if time.monotonic() > deadline:
            raise AssertionError("subscriber never registered")
        time.sleep(0.02)

    started = time.monotonic()
    _publish_via_portal(
        client,
        channel,
        {"kind": "stage.finished", "status": "succeeded", "run_id": bogus_run},
    )
    t.join(timeout=2.0)
    assert not t.is_alive()
    assert len(received) == 1
    assert received[0]["kind"] == "stage.finished"
    assert closed_at and closed_at[0] - started < 2.0


def test_tenant_boundary_blocks_cross_user_subscribe(
    tmp_project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Required-mode auth: bob can't subscribe to alice's run stream.

    Mirrors the cross-tenant pattern from ``test_artifacts.py``. Alice's
    per-user project root contains the run manifest with
    ``user_id=alice``. Bob presents his own header, so
    ``_enforce_run_tenant`` walks his per-user namespace, finds no
    manifest, and rejects with 403 ``run_forbidden``.

    This proves the SSE endpoint goes through the same tenant gate as
    the rest of the run-scoped routes — without it the EventBus would
    leak cross-tenant events.
    """
    monkeypatch.setenv("PLATO_DASHBOARD_AUTH_REQUIRED", "1")

    from plato_dashboard.api.server import create_app

    app = create_app()
    with TestClient(app) as c:
        # Alice creates the project.
        pid = c.post(
            "/api/v1/projects",
            json={"name": "Alice'sRun"},
            headers={"X-Plato-User": "alice"},
        ).json()["id"]

        # Seed a manifest claiming alice owns the run.
        alice_root = tmp_project_root.parent / "users" / "alice"
        run_dir = alice_root / pid / "runs" / "run_alice_only"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "manifest.json").write_text(
            json.dumps({"run_id": "run_alice_only", "user_id": "alice"})
        )

        # Bob attempts to subscribe to alice's run.
        resp = c.get(
            f"/api/v1/projects/{pid}/runs/run_alice_only/events",
            headers={"X-Plato-User": "bob"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "run_forbidden"

        # And the un-authed probe (no header) is rejected by the same dependency
        # chain — auth_required() means missing header → 401 from _get_store.
        unauth = c.get(
            f"/api/v1/projects/{pid}/runs/run_alice_only/events",
        )
        assert unauth.status_code == 401
        assert unauth.json()["detail"]["code"] == "auth_required"


# --------------------------------------------------------------------------- #
# Module-level autouse: keep singleton bus pristine across this file
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _reset_event_bus_local() -> Iterator[None]:
    """Belt-and-braces — conftest already does this, but be explicit here."""
    from plato_dashboard.events import bus as bus_mod

    bus_mod._bus = None
    yield
    bus_mod._bus = None
