"""In-memory event bus with optional Redis backend.

For Phase 1 we ship a process-local fan-out using ``asyncio.Queue`` so the
dev experience is zero-dep (no Redis required for `plato dashboard`).
The interface matches what we'll swap in later for Redis Streams.
"""

from __future__ import annotations
import asyncio
import json
from collections import defaultdict
from typing import AsyncIterator, Optional


class EventBus:
    def __init__(self) -> None:
        self._channels: dict[str, list[asyncio.Queue[str]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, channel: str, event: dict) -> None:
        payload = json.dumps(event, default=str)
        # Snapshot the subscribers under lock; deliver outside lock.
        async with self._lock:
            queues = list(self._channels.get(channel, ()))
        for q in queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # Drop slow consumers; they'll see the next event.
                pass

    async def subscribe(self, channel: str) -> AsyncIterator[dict]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=2048)
        async with self._lock:
            self._channels[channel].append(q)
        try:
            while True:
                payload = await q.get()
                yield json.loads(payload)
        finally:
            async with self._lock:
                if q in self._channels.get(channel, []):
                    self._channels[channel].remove(q)


_bus: Optional[EventBus] = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
