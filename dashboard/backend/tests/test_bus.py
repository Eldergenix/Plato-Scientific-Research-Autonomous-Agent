"""Unit tests for the in-memory EventBus drop-oldest backpressure policy."""

from __future__ import annotations

import asyncio

import pytest

from plato_dashboard.events.bus import EventBus, _Subscriber


pytestmark = pytest.mark.asyncio


async def test_drop_oldest_keeps_latest_events():
    bus = EventBus()
    # Manually attach a tiny-queue subscriber so we can drive the drop path.
    sub = _Subscriber(id=999, channel="run:1", queue=asyncio.Queue(maxsize=2))
    async with bus._lock:
        bus._channels["run:1"].append(sub)

    await bus.publish("run:1", {"n": 1})
    await bus.publish("run:1", {"n": 2})
    await bus.publish("run:1", {"n": 3})  # forces drop of n=1

    assert sub.queue.qsize() == 2
    assert sub.dropped == 1

    import json

    first = json.loads(sub.queue.get_nowait())
    second = json.loads(sub.queue.get_nowait())
    assert first == {"n": 2}
    assert second == {"n": 3}


async def test_normal_publish_no_drops():
    bus = EventBus()
    sub = _Subscriber(id=1, channel="c", queue=asyncio.Queue(maxsize=8))
    async with bus._lock:
        bus._channels["c"].append(sub)

    for i in range(5):
        await bus.publish("c", {"i": i})

    assert sub.dropped == 0
    assert sub.queue.qsize() == 5
