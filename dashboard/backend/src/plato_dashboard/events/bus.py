"""Pluggable event bus with in-memory and Redis-backed implementations.

The dashboard ships an asyncio-Queue-based bus by default so a single-
worker `plato dashboard` install needs zero infrastructure. When the
deployment runs more than one uvicorn worker (or more than one arq
worker process), the in-memory bus drops events that originate in a
different process — SSE consumers attached to worker A miss anything
worker B publishes.

Iter-4: add a Redis-backed implementation that uses Redis Pub/Sub. It's
selected automatically when ``settings.redis_url`` is configured AND
``settings.use_fakeredis`` is false. The interface is the same in both
cases: ``publish(channel, event)`` and ``async for event in subscribe(channel)``.

Why Pub/Sub over Streams: Pub/Sub is fire-and-forget which matches our
SSE semantics (a late subscriber doesn't need backfill — they get the
next event). Streams would also work but require explicit XACK/XADD
plumbing we don't need yet.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import AsyncIterator, Optional, Protocol

_log = logging.getLogger(__name__)


class _Bus(Protocol):
    async def publish(self, channel: str, event: dict) -> None: ...
    def subscribe(self, channel: str) -> AsyncIterator[dict]: ...


class EventBus:
    """In-memory asyncio.Queue fan-out — single-process default."""

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


class RedisEventBus:
    """Redis Pub/Sub fan-out — survives multi-worker deploys.

    Lazy-imports redis so the in-memory default doesn't pull the
    optional dependency at import time. Failures during construction
    fall back to the in-memory bus rather than crashing app startup —
    we'd rather lose cross-worker fan-out temporarily than have the
    whole dashboard refuse to boot when Redis is briefly unreachable.
    """

    def __init__(self, redis_url: str) -> None:
        try:
            from redis import asyncio as redis_asyncio  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "redis>=5.0 is required for the RedisEventBus. "
                "Install with `pip install plato[dashboard]`."
            ) from exc
        self._client = redis_asyncio.from_url(
            redis_url, decode_responses=True, encoding="utf-8"
        )
        self._url = redis_url
        _log.info("RedisEventBus connected to %s", redis_url)

    async def publish(self, channel: str, event: dict) -> None:
        payload = json.dumps(event, default=str)
        try:
            await self._client.publish(channel, payload)
        except Exception:  # noqa: BLE001
            # Network blip — log and drop. Dashboards that need durable
            # delivery should switch to Redis Streams (out of scope here).
            _log.exception(
                "RedisEventBus publish failed; dropping event channel=%s",
                channel,
            )

    async def subscribe(self, channel: str) -> AsyncIterator[dict]:
        # Each subscriber gets its own pubsub object so close-on-cancel
        # only releases this caller's resources, not other subscribers'.
        pubsub = self._client.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8", errors="replace")
                if not isinstance(data, str):
                    continue
                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    _log.warning(
                        "RedisEventBus dropped non-JSON payload on %s",
                        channel,
                    )
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception:  # noqa: BLE001
                pass


_bus: Optional[EventBus | RedisEventBus] = None


def get_bus() -> EventBus | RedisEventBus:
    """Return the singleton bus, lazily constructed on first call.

    Selection order:
      1. ``settings.redis_url`` set + ``not settings.use_fakeredis``
         → RedisEventBus (multi-worker safe).
      2. Otherwise → in-memory ``EventBus`` (process-local).

    A construction failure on the Redis path falls back to the in-memory
    implementation rather than crashing — the failure is logged so
    operators can see the degradation in their dashboard.
    """
    global _bus
    if _bus is not None:
        return _bus

    # Lazy import to avoid a settings-import cycle when this module is
    # imported during app startup.
    from ..settings import get_settings

    settings = get_settings()
    redis_url = getattr(settings, "redis_url", None)
    use_fake = getattr(settings, "use_fakeredis", True)

    if redis_url and not use_fake:
        try:
            _bus = RedisEventBus(redis_url)
            return _bus
        except Exception:  # noqa: BLE001
            _log.exception(
                "Failed to construct RedisEventBus; falling back to in-memory"
            )

    _bus = EventBus()
    return _bus


def reset_bus_for_testing() -> None:
    """Drop the cached bus singleton.

    Test harnesses that monkeypatch settings need this so the next
    ``get_bus()`` call honours the patched values. Production code
    should never call this.
    """
    global _bus
    _bus = None
