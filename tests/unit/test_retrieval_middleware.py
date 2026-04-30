"""
Phase 5 (R8) — unit tests for ``plato.retrieval.middleware``.

The middleware composes three primitives — exponential backoff, ETag
conditional-GET, and a circuit breaker — behind a drop-in ``httpx``
context-manager. These tests pin the behavior of each primitive in
isolation and then verify the composition is transparent for the happy
path callers (a 200 response flows through untouched).

All network is mocked. Sleeps are mocked too so the suite stays fast.
"""
from __future__ import annotations

import asyncio
from email.utils import format_datetime
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from plato.retrieval import middleware as mw
from plato.retrieval.middleware import (
    CircuitBreaker,
    CircuitOpenError,
    ETagCache,
    RateLimitBackoff,
    RetrievalClient,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resp(status: int, body: str = "", headers: dict[str, str] | None = None) -> httpx.Response:
    request = httpx.Request("GET", "https://example.test/x")
    return httpx.Response(
        status_code=status,
        content=body.encode("utf-8"),
        headers=headers or {},
        request=request,
    )


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Capture sleeps without actually waiting."""
    captured: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        captured.append(seconds)

    monkeypatch.setattr(mw.asyncio, "sleep", fake_sleep)
    return captured


# ---------------------------------------------------------------------------
# RateLimitBackoff
# ---------------------------------------------------------------------------


class TestRateLimitBackoff:
    @pytest.mark.asyncio
    async def test_passes_through_on_success(self, no_sleep: list[float]) -> None:
        backoff = RateLimitBackoff(max_retries=3, base_delay=0.1, max_delay=1.0)
        ok = _resp(200, "fine")

        async def request() -> httpx.Response:
            return ok

        out = await backoff.execute(request)
        assert out is ok
        assert no_sleep == []

    @pytest.mark.asyncio
    async def test_retries_on_429_then_succeeds(self, no_sleep: list[float]) -> None:
        backoff = RateLimitBackoff(max_retries=3, base_delay=0.5, max_delay=2.0)
        responses = [_resp(429), _resp(200, "ok")]
        calls = {"n": 0}

        async def request() -> httpx.Response:
            r = responses[calls["n"]]
            calls["n"] += 1
            return r

        out = await backoff.execute(request)
        assert out.status_code == 200
        assert calls["n"] == 2
        assert len(no_sleep) == 1
        assert 0 < no_sleep[0] <= 2.0

    @pytest.mark.asyncio
    async def test_retries_on_503(self, no_sleep: list[float]) -> None:
        backoff = RateLimitBackoff(max_retries=2, base_delay=0.1, max_delay=1.0)
        responses = [_resp(503), _resp(503), _resp(200, "ok")]
        calls = {"n": 0}

        async def request() -> httpx.Response:
            r = responses[calls["n"]]
            calls["n"] += 1
            return r

        out = await backoff.execute(request)
        assert out.status_code == 200
        assert calls["n"] == 3
        assert len(no_sleep) == 2

    @pytest.mark.asyncio
    async def test_honors_numeric_retry_after(self, no_sleep: list[float]) -> None:
        backoff = RateLimitBackoff(max_retries=2, base_delay=10.0, max_delay=30.0)
        responses = [_resp(429, headers={"Retry-After": "7"}), _resp(200)]
        calls = {"n": 0}

        async def request() -> httpx.Response:
            r = responses[calls["n"]]
            calls["n"] += 1
            return r

        await backoff.execute(request)
        assert no_sleep == [7.0]

    @pytest.mark.asyncio
    async def test_honors_http_date_retry_after(
        self, no_sleep: list[float], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Pin time.time so the HTTP-date arithmetic is deterministic.
        fixed_now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        monkeypatch.setattr(mw.time, "time", lambda: fixed_now.timestamp())

        retry_at = fixed_now + timedelta(seconds=12)
        http_date = format_datetime(retry_at, usegmt=True)

        backoff = RateLimitBackoff(max_retries=1, base_delay=0.1, max_delay=60.0)
        responses = [_resp(429, headers={"Retry-After": http_date}), _resp(200)]
        calls = {"n": 0}

        async def request() -> httpx.Response:
            r = responses[calls["n"]]
            calls["n"] += 1
            return r

        await backoff.execute(request)
        assert len(no_sleep) == 1
        # 12s ± a tiny amount of clock-skew slack from formatting.
        assert 11.0 <= no_sleep[0] <= 13.0

    @pytest.mark.asyncio
    async def test_caps_retry_after_at_max_delay(self, no_sleep: list[float]) -> None:
        backoff = RateLimitBackoff(max_retries=1, base_delay=0.1, max_delay=5.0)
        responses = [_resp(429, headers={"Retry-After": "9999"}), _resp(200)]
        calls = {"n": 0}

        async def request() -> httpx.Response:
            r = responses[calls["n"]]
            calls["n"] += 1
            return r

        await backoff.execute(request)
        assert no_sleep == [5.0]

    @pytest.mark.asyncio
    async def test_gives_up_after_max_retries(self, no_sleep: list[float]) -> None:
        backoff = RateLimitBackoff(max_retries=2, base_delay=0.1, max_delay=1.0)
        # Always 429 — we should see exactly 2 sleeps then return the last 429.
        async def request() -> httpx.Response:
            return _resp(429)

        out = await backoff.execute(request)
        assert out.status_code == 429
        assert len(no_sleep) == 2

    def test_invalid_args_raise(self) -> None:
        with pytest.raises(ValueError):
            RateLimitBackoff(max_retries=-1)
        with pytest.raises(ValueError):
            RateLimitBackoff(base_delay=0)
        with pytest.raises(ValueError):
            RateLimitBackoff(base_delay=10.0, max_delay=1.0)


# ---------------------------------------------------------------------------
# ETagCache
# ---------------------------------------------------------------------------


class _StubClient:
    """Pretends to be an ``httpx.AsyncClient`` for cache tests."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        **_: Any,
    ) -> httpx.Response:
        self.calls.append((url, dict(headers or {})))
        return self._responses.pop(0)


class TestETagCache:
    @pytest.mark.asyncio
    async def test_first_get_is_a_miss_and_stores_etag(self, tmp_path) -> None:
        cache = ETagCache(cache_dir=tmp_path)
        client = _StubClient([
            _resp(200, "hello", headers={"ETag": "v1", "Content-Type": "text/plain"})
        ])

        out = await cache.get(client, "https://example.test/x")
        assert out.status_code == 200
        assert out.text == "hello"
        # No conditional headers on the first call.
        assert "If-None-Match" not in client.calls[0][1]
        # Stats reflect a miss.
        assert cache.stats()["misses"] == 1
        assert cache.stats()["hits"] == 0
        assert cache.stats()["size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_second_get_sends_if_none_match_and_returns_cached_on_304(
        self, tmp_path
    ) -> None:
        cache = ETagCache(cache_dir=tmp_path)
        first = _resp(200, "hello", headers={"ETag": "v1"})
        second = _resp(304, headers={"ETag": "v1"})

        # First request populates the cache.
        client = _StubClient([first])
        await cache.get(client, "https://example.test/x")

        # Second client returns 304 — cache must replay "hello".
        client2 = _StubClient([second])
        out = await cache.get(client2, "https://example.test/x")

        assert out.status_code == 200  # replayed body status
        assert out.text == "hello"
        # The conditional header should have been sent on the 2nd request.
        assert client2.calls[0][1].get("If-None-Match") == "v1"
        assert cache.stats()["hits"] == 1

    @pytest.mark.asyncio
    async def test_last_modified_path(self, tmp_path) -> None:
        cache = ETagCache(cache_dir=tmp_path)
        first = _resp(
            200, "world", headers={"Last-Modified": "Wed, 21 Oct 2015 07:28:00 GMT"}
        )
        second = _resp(304)

        client = _StubClient([first])
        await cache.get(client, "https://example.test/y")

        client2 = _StubClient([second])
        out = await cache.get(client2, "https://example.test/y")

        assert out.text == "world"
        assert (
            client2.calls[0][1].get("If-Modified-Since")
            == "Wed, 21 Oct 2015 07:28:00 GMT"
        )

    @pytest.mark.asyncio
    async def test_no_validators_no_caching(self, tmp_path) -> None:
        cache = ETagCache(cache_dir=tmp_path)
        # No ETag, no Last-Modified — must not be cached.
        first = _resp(200, "uncacheable")
        client = _StubClient([first])
        await cache.get(client, "https://example.test/z")

        # Second request should also miss (because nothing was stored).
        second = _resp(200, "uncacheable", headers={})
        client2 = _StubClient([second])
        await cache.get(client2, "https://example.test/z")
        assert "If-None-Match" not in client2.calls[0][1]
        assert "If-Modified-Since" not in client2.calls[0][1]

    @pytest.mark.asyncio
    async def test_clear_resets_state(self, tmp_path) -> None:
        cache = ETagCache(cache_dir=tmp_path)
        client = _StubClient([_resp(200, "x", headers={"ETag": "e"})])
        await cache.get(client, "https://example.test/a")
        assert cache.stats()["size_bytes"] > 0

        cache.clear()
        assert cache.stats() == {"hits": 0, "misses": 0, "size_bytes": 0}


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def test_closed_initially(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10.0)
        assert cb.is_open is False

    def test_opens_after_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is False
        cb.record_failure()
        assert cb.is_open is True

    def test_resets_on_success(self) -> None:
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=10.0)
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        assert cb.is_open is False  # streak was reset

    def test_cooldown_closes_breaker(self) -> None:
        # Use a fake clock to step past the cooldown deterministically.
        clock = {"t": 0.0}
        cb = CircuitBreaker(
            failure_threshold=2,
            cooldown_seconds=5.0,
            clock=lambda: clock["t"],
        )
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is True

        clock["t"] = 4.99
        assert cb.is_open is True

        clock["t"] = 5.0
        assert cb.is_open is False
        # And after re-closing, fresh failures need to hit the threshold again.
        cb.record_failure()
        assert cb.is_open is False

    def test_invalid_args(self) -> None:
        with pytest.raises(ValueError):
            CircuitBreaker(failure_threshold=0)
        with pytest.raises(ValueError):
            CircuitBreaker(cooldown_seconds=0)


# ---------------------------------------------------------------------------
# RetrievalClient — composition
# ---------------------------------------------------------------------------


class TestRetrievalClient:
    @pytest.mark.asyncio
    async def test_happy_path_passes_through(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Stub httpx.AsyncClient so we don't touch the network. The stub
        # behaves as an async context manager and exposes ``.get``.
        body = "hello"

        class _FakeAsyncClient:
            def __init__(self, **_: Any) -> None:
                pass

            async def __aenter__(self) -> "_FakeAsyncClient":
                return self

            async def __aexit__(self, *_: Any) -> None:
                return None

            async def get(self, url: str, **_: Any) -> httpx.Response:
                return _resp(200, body)

        monkeypatch.setattr(mw.httpx, "AsyncClient", _FakeAsyncClient)

        async with RetrievalClient(cache_dir=tmp_path) as client:
            response = await client.get("https://example.test/x")

        assert response.status_code == 200
        assert response.text == body

    @pytest.mark.asyncio
    async def test_retries_on_429_through_full_stack(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_sleep(_: float) -> None:
            return None

        monkeypatch.setattr(mw.asyncio, "sleep", fake_sleep)

        responses = [_resp(429), _resp(200, "ok")]

        class _FakeAsyncClient:
            def __init__(self, **_: Any) -> None:
                pass

            async def __aenter__(self) -> "_FakeAsyncClient":
                return self

            async def __aexit__(self, *_: Any) -> None:
                return None

            async def get(self, url: str, **_: Any) -> httpx.Response:
                return responses.pop(0)

        monkeypatch.setattr(mw.httpx, "AsyncClient", _FakeAsyncClient)

        async with RetrievalClient(cache_dir=tmp_path) as client:
            response = await client.get("https://example.test/y")

        assert response.status_code == 200
        assert response.text == "ok"
        assert responses == []

    @pytest.mark.asyncio
    async def test_open_breaker_short_circuits_get(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Pre-tripped breaker must refuse the call.
        breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)
        breaker.record_failure()
        assert breaker.is_open

        class _FakeAsyncClient:
            def __init__(self, **_: Any) -> None:
                pass

            async def __aenter__(self) -> "_FakeAsyncClient":
                return self

            async def __aexit__(self, *_: Any) -> None:
                return None

            async def get(self, url: str, **_: Any) -> httpx.Response:
                raise AssertionError("should not be reached")

        monkeypatch.setattr(mw.httpx, "AsyncClient", _FakeAsyncClient)

        async with RetrievalClient(breaker=breaker, cache_dir=tmp_path) as client:
            with pytest.raises(CircuitOpenError):
                await client.get("https://example.test/dead")

    @pytest.mark.asyncio
    async def test_get_outside_context_raises(self, tmp_path) -> None:
        client = RetrievalClient(cache_dir=tmp_path)
        with pytest.raises(RuntimeError):
            await client.get("https://example.test/oops")

    @pytest.mark.asyncio
    async def test_5xx_records_breaker_failure(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_sleep(_: float) -> None:
            return None

        monkeypatch.setattr(mw.asyncio, "sleep", fake_sleep)

        # 500 isn't in the retry list — falls straight through and counts
        # against the breaker.
        class _FakeAsyncClient:
            def __init__(self, **_: Any) -> None:
                pass

            async def __aenter__(self) -> "_FakeAsyncClient":
                return self

            async def __aexit__(self, *_: Any) -> None:
                return None

            async def get(self, url: str, **_: Any) -> httpx.Response:
                return _resp(500)

        monkeypatch.setattr(mw.httpx, "AsyncClient", _FakeAsyncClient)

        breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=60.0)

        async with RetrievalClient(breaker=breaker, cache_dir=tmp_path) as client:
            await client.get("https://example.test/sick")
            assert breaker.is_open is False
            await client.get("https://example.test/sick")
            assert breaker.is_open is True
