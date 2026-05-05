"""In-memory event bus with optional Redis backend.

For Phase 1 we ship a process-local fan-out using ``asyncio.Queue`` so the
dev experience is zero-dep (no Redis required for `plato dashboard`).
The interface matches what we'll swap in later for Redis Streams.
"""

from __future__ import annotations
import asyncio
import itertools
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import AsyncIterator, Optional


logger = logging.getLogger(__name__)


_subscriber_ids = itertools.count(1)


@dataclass
class _Subscriber:
    id: int
    channel: str
    queue: asyncio.Queue[str]
    dropped: int = 0


class EventBus:
    def __init__(self) -> None:
        self._channels: dict[str, list[_Subscriber]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, channel: str, event: dict) -> None:
        payload = json.dumps(event, default=str)
        async with self._lock:
            subs = list(self._channels.get(channel, ()))
        for sub in subs:
            self._deliver(sub, payload)

    def _deliver(self, sub: _Subscriber, payload: str) -> None:
        try:
            sub.queue.put_nowait(payload)
            return
        except asyncio.QueueFull:
            pass
        # Slow consumer: drop the oldest queued event so the freshest
        # one (e.g. stage.finished) still reaches the client.
        try:
            sub.queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            sub.queue.put_nowait(payload)
            sub.dropped += 1
            logger.warning(
                "event-bus drop oldest channel=%s subscriber=%s dropped=%d",
                sub.channel,
                sub.id,
                sub.dropped,
            )
        except asyncio.QueueFull:
            sub.dropped += 1
            logger.warning(
                "event-bus drop newest channel=%s subscriber=%s dropped=%d",
                sub.channel,
                sub.id,
                sub.dropped,
            )

    async def subscribe(self, channel: str) -> AsyncIterator[dict]:
        sub = _Subscriber(
            id=next(_subscriber_ids),
            channel=channel,
            queue=asyncio.Queue(maxsize=2048),
        )
        async with self._lock:
            self._channels[channel].append(sub)
        try:
            while True:
                payload = await sub.queue.get()
                yield json.loads(payload)
        finally:
            async with self._lock:
                if sub in self._channels.get(channel, []):
                    self._channels[channel].remove(sub)


_bus: Optional[EventBus] = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
