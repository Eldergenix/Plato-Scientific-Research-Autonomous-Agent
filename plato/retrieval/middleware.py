"""
Phase 5 (R8) — middleware for retrieval HTTP clients.

Adapters in :mod:`plato.retrieval.sources` used to call ``httpx.AsyncClient``
directly, which left them exposed to three failure modes the orchestrator
hits in production:

1. Bursts of 429 / 503 responses from rate-limited APIs (Crossref, OpenAlex,
   Semantic Scholar, NCBI) that should be retried with backoff and respect
   the server's ``Retry-After`` hint.
2. Repeat GETs of the same query in a single run wasting bandwidth and
   tripping rate limits — most of these endpoints emit ``ETag`` /
   ``Last-Modified`` and would happily return ``304 Not Modified`` if we
   asked.
3. A single dead host (e.g. ADS unreachable) blocking every fan-out call
   for its full timeout — a circuit breaker turns the second + third
   attempts into instant failures so the orchestrator can move on.

This module composes those three concerns behind one drop-in client:

    async with RetrievalClient(timeout=15.0) as client:
        response = await client.get(url, headers=...)

``RetrievalClient`` wraps ``httpx.AsyncClient`` rather than replacing it.
Adapter tests that monkeypatch ``httpx.AsyncClient.get`` continue to work
because every request still flows through the underlying httpx client.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import time
from collections.abc import Awaitable, Callable
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


__all__ = [
    "RateLimitBackoff",
    "ETagCache",
    "CircuitBreaker",
    "RetrievalClient",
    "CircuitOpenError",
]


# ---------------------------------------------------------------------------
# Rate-limit backoff
# ---------------------------------------------------------------------------


def _parse_retry_after(value: str | None) -> float | None:
    """Convert a ``Retry-After`` header into seconds.

    Per RFC 7231 the header may be an integer (delta-seconds) or an HTTP-date
    string. Returns ``None`` for missing / unparseable values so the caller
    can fall back to its own backoff schedule.
    """
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    delta = when.timestamp() - time.time()
    return max(0.0, delta)


class RateLimitBackoff:
    """Async exponential-backoff helper that respects ``Retry-After``.

    Retries on HTTP 429 and 503. The ``Retry-After`` header (if present) is
    honored verbatim; otherwise the delay is ``base_delay * 2**attempt``
    capped at ``max_delay`` with a small jitter to avoid thundering-herd.
    """

    _RETRYABLE_STATUS = {429, 503}

    def __init__(
        self,
        max_retries: int = 4,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if base_delay <= 0:
            raise ValueError("base_delay must be > 0")
        if max_delay < base_delay:
            raise ValueError("max_delay must be >= base_delay")
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def _compute_delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(retry_after, self.max_delay)
        # Decorrelated jitter — keeps the bound tight without becoming periodic.
        backoff = min(self.base_delay * (2 ** attempt), self.max_delay)
        return backoff * (0.5 + random.random() / 2)

    async def execute(
        self,
        request: Callable[[], Awaitable[httpx.Response]],
    ) -> httpx.Response:
        """Run ``request`` with retry-on-429/503 semantics."""
        attempt = 0
        while True:
            response = await request()
            if response.status_code not in self._RETRYABLE_STATUS:
                return response
            if attempt >= self.max_retries:
                return response
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            delay = self._compute_delay(attempt, retry_after)
            logger.info(
                "RateLimitBackoff: status=%s attempt=%s delay=%.2fs",
                response.status_code,
                attempt + 1,
                delay,
            )
            await asyncio.sleep(delay)
            attempt += 1


# ---------------------------------------------------------------------------
# ETag conditional-GET cache
# ---------------------------------------------------------------------------


def _default_cache_dir() -> Path:
    return Path.home() / ".plato" / "cache" / "retrieval"


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


class ETagCache:
    """Filesystem-backed conditional-GET cache keyed by URL hash.

    Each entry stores ``{etag, last_modified, body, status, content_type}``
    so we can both replay a cached body on ``304 Not Modified`` and reissue
    the conditional headers (``If-None-Match`` / ``If-Modified-Since``) on
    the next request.
    """

    def __init__(self, cache_dir: Path | str | None = None) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir is not None else _default_cache_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._hits = 0
        self._misses = 0

    def _meta_path(self, url: str) -> Path:
        return self.cache_dir / f"{_hash_url(url)}.json"

    def _load(self, url: str) -> dict[str, Any] | None:
        path = self._meta_path(url)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("ETagCache: failed to load %s: %s", path, exc)
            return None

    def _store(self, url: str, entry: dict[str, Any]) -> None:
        path = self._meta_path(url)
        try:
            with path.open("w", encoding="utf-8") as fh:
                json.dump(entry, fh)
        except OSError as exc:
            logger.warning("ETagCache: failed to write %s: %s", path, exc)

    async def get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: Any | None = None,
    ) -> httpx.Response:
        """GET ``url`` through ``client``, returning a cached body on 304.

        Outgoing headers are merged with conditional-request headers built
        from the cached entry (if any). On a 200 response with an ETag /
        Last-Modified, the response body is persisted for next time. On 304
        the cached body is returned with status 200 to keep call sites
        oblivious to the cache.
        """
        out_headers = dict(headers) if headers else {}
        cached = self._load(url)
        if cached:
            etag = cached.get("etag")
            last_mod = cached.get("last_modified")
            if etag and "If-None-Match" not in out_headers:
                out_headers["If-None-Match"] = etag
            if last_mod and "If-Modified-Since" not in out_headers:
                out_headers["If-Modified-Since"] = last_mod

        kwargs: dict[str, Any] = {"headers": out_headers} if out_headers else {}
        if params is not None:
            kwargs["params"] = params
        response = await client.get(url, **kwargs)

        if response.status_code == 304 and cached:
            self._hits += 1
            request = httpx.Request("GET", url)
            replayed = httpx.Response(
                status_code=cached.get("status", 200),
                headers=cached.get("response_headers") or {},
                content=cached["body"].encode("utf-8") if isinstance(cached.get("body"), str) else b"",
                request=request,
            )
            return replayed

        self._misses += 1
        if response.status_code == 200:
            try:
                etag = response.headers.get("ETag")
                last_mod = response.headers.get("Last-Modified")
            except (AttributeError, TypeError):
                etag = last_mod = None
            # Skip caching if the response doesn't carry validators OR the
            # validator values aren't real strings (test Mock objects show
            # up as truthy non-strings that would silently corrupt the cache).
            if (isinstance(etag, str) and etag) or (
                isinstance(last_mod, str) and last_mod
            ):
                try:
                    body = response.text
                except Exception:  # noqa: BLE001
                    body = ""
                if isinstance(body, str):
                    response_headers: dict[str, str] = {}
                    try:
                        for k, v in response.headers.items():
                            if isinstance(k, str) and isinstance(v, str) and k.lower() in {
                                "content-type",
                                "etag",
                                "last-modified",
                            }:
                                response_headers[k] = v
                    except (AttributeError, TypeError):
                        response_headers = {}
                    self._store(
                        url,
                        {
                            "etag": etag if isinstance(etag, str) else None,
                            "last_modified": last_mod if isinstance(last_mod, str) else None,
                            "body": body,
                            "status": 200,
                            "response_headers": response_headers,
                        },
                    )
        return response

    def clear(self) -> None:
        for entry in self.cache_dir.glob("*.json"):
            try:
                entry.unlink()
            except OSError as exc:
                logger.debug("ETagCache.clear: %s: %s", entry, exc)
        self._hits = 0
        self._misses = 0

    def stats(self) -> dict[str, int]:
        size = 0
        for entry in self.cache_dir.glob("*.json"):
            try:
                size += entry.stat().st_size
            except OSError:
                continue
        return {"hits": self._hits, "misses": self._misses, "size_bytes": size}


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class CircuitOpenError(RuntimeError):
    """Raised when a request is short-circuited by an open breaker."""


class CircuitBreaker:
    """Per-host circuit breaker with a single closed/open state.

    After ``failure_threshold`` consecutive failures the breaker opens; while
    open, ``is_open`` is True until ``cooldown_seconds`` have elapsed since
    the last failure, at which point it transitions back to closed.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 60.0,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be > 0")
        if cooldown_seconds <= 0:
            raise ValueError("cooldown_seconds must be > 0")
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failures = 0
        self._opened_at: float | None = None
        self._clock = clock

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = self._clock()

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if self._clock() - self._opened_at >= self.cooldown_seconds:
            self._failures = 0
            self._opened_at = None
            return False
        return True


# ---------------------------------------------------------------------------
# Composed client
# ---------------------------------------------------------------------------


class RetrievalClient:
    """Drop-in async context manager wrapping ``httpx.AsyncClient``.

    Wires :class:`RateLimitBackoff`, :class:`ETagCache` and
    :class:`CircuitBreaker` around a single underlying ``httpx.AsyncClient``
    so every adapter gets the same defenses without copying boilerplate.

    Constructor arguments mirror ``httpx.AsyncClient`` for the common case
    (``timeout``, ``headers``); pass ``cache=False`` or ``breaker=False`` to
    disable the corresponding middleware.
    """

    def __init__(
        self,
        *,
        timeout: float | httpx.Timeout = 15.0,
        headers: dict[str, str] | None = None,
        cache: bool | ETagCache = True,
        breaker: bool | CircuitBreaker = True,
        backoff: bool | RateLimitBackoff = True,
        cache_dir: Path | str | None = None,
    ) -> None:
        self._timeout = timeout
        self._init_headers = headers
        self._client: httpx.AsyncClient | None = None
        self._cm: httpx.AsyncClient | None = None

        if isinstance(cache, ETagCache):
            self._cache: ETagCache | None = cache
        elif cache:
            # The on-disk cache is opt-out for tests that don't want
            # hidden state; honor PLATO_DISABLE_RETRIEVAL_CACHE for the
            # same reason.
            if os.environ.get("PLATO_DISABLE_RETRIEVAL_CACHE"):
                self._cache = None
            else:
                self._cache = ETagCache(cache_dir=cache_dir)
        else:
            self._cache = None

        if isinstance(breaker, CircuitBreaker):
            self._breaker: CircuitBreaker | None = breaker
        elif breaker:
            self._breaker = CircuitBreaker()
        else:
            self._breaker = None

        if isinstance(backoff, RateLimitBackoff):
            self._backoff: RateLimitBackoff | None = backoff
        elif backoff:
            self._backoff = RateLimitBackoff()
        else:
            self._backoff = None

    async def __aenter__(self) -> "RetrievalClient":
        kwargs: dict[str, Any] = {"timeout": self._timeout}
        if self._init_headers:
            kwargs["headers"] = self._init_headers
        # Construct via the live ``httpx.AsyncClient`` reference so test
        # patches at ``plato.retrieval.sources.<name>.httpx.AsyncClient``
        # (which mutate the shared httpx module) still take effect.
        self._cm = httpx.AsyncClient(**kwargs)
        # Use the value returned by ``__aenter__`` rather than the context
        # manager itself — patched ``AsyncClient`` mocks in tests bind their
        # ``.get`` to ``__aenter__.return_value``.
        self._client = await self._cm.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        cm = getattr(self, "_cm", None)
        if cm is not None:
            try:
                await cm.__aexit__(exc_type, exc, tb)
            finally:
                self._cm = None
                self._client = None

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: Any | None = None,
    ) -> httpx.Response:
        """Issue a GET through the composed middleware stack."""
        if self._client is None:
            raise RuntimeError(
                "RetrievalClient must be used as an async context manager"
            )
        if self._breaker is not None and self._breaker.is_open:
            raise CircuitOpenError(f"circuit open for {url}")

        async def do_request() -> httpx.Response:
            if self._cache is not None:
                return await self._cache.get(
                    self._client,  # type: ignore[arg-type]
                    url,
                    headers=headers,
                    params=params,
                )
            kwargs: dict[str, Any] = {}
            if headers:
                kwargs["headers"] = headers
            if params is not None:
                kwargs["params"] = params
            return await self._client.get(url, **kwargs)  # type: ignore[union-attr]

        try:
            if self._backoff is not None:
                response = await self._backoff.execute(do_request)
            else:
                response = await do_request()
        except (httpx.HTTPError, asyncio.TimeoutError):
            if self._breaker is not None:
                self._breaker.record_failure()
            raise

        if self._breaker is not None:
            status = response.status_code
            if isinstance(status, int) and status >= 500:
                self._breaker.record_failure()
            else:
                # Unknown / non-integer (e.g. test mocks) is treated as success.
                self._breaker.record_success()
        return response
