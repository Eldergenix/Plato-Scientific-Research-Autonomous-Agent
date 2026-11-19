"""Async client for the Firecrawl v2 API: the Research Index, web search and scrape,
developer search and Alexandria tools.

Endpoints (https://api.firecrawl.dev/v2, ``Authorization: Bearer <key>``), as documented at
docs.firecrawl.dev/api-reference and implemented by the official SDKs
(firecrawl-py 4.57, @mendable/firecrawl-js 4.54):

Research Index (free; pricing page: "Research Index (papers): Free")
  * ``GET /search/research/papers``              search ~43M abstracts (PubMed, bioRxiv,
    medRxiv, arXiv): ``query``, ``k`` (1-500), ``authors``, ``categories``, ``from``, ``to``
  * ``GET /search/research/papers/{id}``         metadata, or in-body passages with ``query``
    (and ``k``, 1-50)
  * ``GET /search/research/papers/{id}/similar`` citation-graph neighbours re-ranked by
    ``intent``; ``mode`` similar | citers | references
  * ``GET /search/research/proteins``            UniProt entry: ``protein``, ``organism``

Billed in credits
  * ``POST /search``            web search (2 credits per 10 results; Alexandria tool
    discovery in the same call is free). The response reports ``creditsUsed``.
  * ``POST /scrape``            one page as markdown (1 credit, PDFs 1 credit per page; the
    response reports ``data.metadata.creditsUsed``), or Alexandria tool runs with an
    ``alexandria`` array (each tool's listed price; the response reports
    ``data.creditsCost``).
  * ``POST /search/developer``  developer docs, GitHub issues, pull requests and readmes.

Every response is untrusted third-party content: callers frame it before a model sees it.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import random
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Self
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_BASE_URL",
    "FirecrawlClient",
    "FirecrawlError",
    "Paid",
    "api_key",
    "configured",
    "search_credits",
]

DEFAULT_BASE_URL = "https://api.firecrawl.dev/v2"
_ORIGIN = "plato-scientist"
# Statuses worth one more try after a pause (rate limit, gateway and server errors).
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
# PDF pages one scrape may parse (each costs a credit).
SCRAPE_MAX_PDF_PAGES = 5
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")


def api_key(env: dict[str, str] | None = None) -> str | None:
    value = (
        (env if env is not None else os.environ).get("FIRECRAWL_API_KEY") or ""
    ).strip()
    return value or None


def configured(env: dict[str, str] | None = None) -> bool:
    return api_key(env) is not None


def search_credits(results: int) -> int:
    """Documented web search price: 2 credits per 10 results, rounded up."""
    return 2 * math.ceil(max(1, results) / 10)


class FirecrawlError(RuntimeError):
    def __init__(
        self, message: str, status: int | None = None, code: str | None = None
    ):
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass
class Paid:
    """A billed response: its JSON body and the credits Firecrawl charged for it."""

    body: dict[str, Any]
    credits: float
    reported: bool = field(default=False)  # True when the API stated the charge


def _error_message(response: httpx.Response) -> tuple[str, str | None]:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300] or response.reason_phrase, None
    if not isinstance(body, dict):
        return str(body)[:300], None
    message = (
        body.get("error")
        or body.get("detail")
        or body.get("title")
        or body.get("message")
    )
    code = body.get("code")
    return str(message or response.reason_phrase)[:300], (str(code) if code else None)


class FirecrawlClient:
    """Thin async wrapper over the endpoints above. Raises :class:`FirecrawlError` on any
    non-success response after one retry of a rate-limited or failed request."""

    def __init__(
        self,
        key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = 60.0,
        http: httpx.AsyncClient | None = None,
        retry_delay: float = 2.0,
    ) -> None:
        self._key = key if key is not None else api_key()
        if not self._key:
            raise FirecrawlError("FIRECRAWL_API_KEY is not set")
        self._base = (
            base_url or os.environ.get("FIRECRAWL_API_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self._own_http = http is None
        self._http = http or httpx.AsyncClient(timeout=timeout)
        self._retry_delay = retry_delay

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._own_http:
            await self._http.aclose()

    # ------------------------------------------------------------------ transport
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: list[tuple[str, Any]] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base}{path}"
        all_headers = {"Authorization": f"Bearer {self._key}", **(headers or {})}
        clean = [
            (k, str(v).lower() if isinstance(v, bool) else str(v))
            for k, v in params or []
        ]
        for attempt in range(2):
            try:
                response = await self._http.request(
                    method,
                    url,
                    params=clean or None,
                    json=json,
                    headers=all_headers,
                    **({"timeout": timeout} if timeout else {}),
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == 0:
                    await asyncio.sleep(self._retry_delay)
                    continue
                raise FirecrawlError(f"{method} {path}: {type(exc).__name__}") from exc
            if response.status_code in _RETRY_STATUSES and attempt == 0:
                retry_after = response.headers.get("retry-after", "")
                delay = (
                    float(retry_after) if retry_after.isdigit() else self._retry_delay
                )
                await asyncio.sleep(min(delay, 30.0) + random.uniform(0, 0.5))
                continue
            if response.status_code != 200:
                message, code = _error_message(response)
                raise FirecrawlError(
                    f"{method} {path} -> {response.status_code}: {message}",
                    response.status_code,
                    code,
                )
            try:
                body = response.json()
            except ValueError as exc:
                raise FirecrawlError(f"{method} {path}: response is not JSON") from exc
            if not isinstance(body, dict) or body.get("success") is False:
                message = body.get("error") if isinstance(body, dict) else None
                raise FirecrawlError(
                    f"{method} {path}: {message or 'request failed'}", 200
                )
            return body
        raise AssertionError("unreachable")  # pragma: no cover

    # ------------------------------------------------------------------ research index (free)
    async def search_papers(
        self,
        query: str,
        *,
        k: int = 10,
        authors: list[str] | None = None,
        categories: list[str] | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict[str, Any]]:
        if not query.strip():
            raise ValueError("query cannot be empty")
        params: list[tuple[str, Any]] = [
            ("query", query),
            ("k", max(1, min(int(k), 500))),
        ]
        params += [("authors", a) for a in authors or []]
        params += [("categories", c) for c in categories or []]
        if from_date:
            params.append(("from", from_date))
        if to_date:
            params.append(("to", to_date))
        params.append(("origin", _ORIGIN))
        body = await self._request("GET", "/search/research/papers", params=params)
        return [r for r in body.get("results") or [] if isinstance(r, dict)]

    async def get_paper(
        self, paper_id: str, *, query: str | None = None, k: int | None = None
    ) -> dict[str, Any]:
        """Metadata (``paper``) or, with ``query``, also the best in-body ``passages``."""
        if not paper_id.strip():
            raise ValueError("paper id cannot be empty")
        params: list[tuple[str, Any]] = []
        if query:
            params.append(("query", query))
            if k is not None:
                params.append(("k", max(1, min(int(k), 50))))
        params.append(("origin", _ORIGIN))
        return await self._request(
            "GET", f"/search/research/papers/{quote(paper_id, safe='')}", params=params
        )

    async def related_papers(
        self,
        paper_id: str,
        intent: str,
        *,
        mode: str = "similar",
        k: int = 10,
        rerank: bool | None = None,
        anchors: list[str] | None = None,
    ) -> dict[str, Any]:
        if mode not in ("similar", "citers", "references"):
            raise ValueError("mode must be similar, citers or references")
        if not intent.strip():
            raise ValueError("intent cannot be empty")
        params: list[tuple[str, Any]] = [
            ("intent", intent),
            ("mode", mode),
            ("k", max(1, min(int(k), 500))),
        ]
        if rerank is not None:
            params.append(("rerank", rerank))
        params += [("anchor", a) for a in anchors or []]
        params.append(("origin", _ORIGIN))
        return await self._request(
            "GET",
            f"/search/research/papers/{quote(paper_id, safe='')}/similar",
            params=params,
        )

    async def protein(
        self, protein: str, *, organism: str | None = None
    ) -> dict[str, Any]:
        """UniProt entry by accession, entry name, gene symbol or exact name. ``match`` is
        found, ambiguous (``candidates``) or not_found."""
        protein = protein.strip()
        if not 1 <= len(protein) <= 200:
            raise ValueError("protein must be 1 to 200 characters")
        params: list[tuple[str, Any]] = [("protein", protein)]
        if organism and organism.strip():
            params.append(("organism", organism.strip()))
        params.append(("origin", _ORIGIN))
        return await self._request("GET", "/search/research/proteins", params=params)

    # ------------------------------------------------------------------ billed endpoints
    async def developer_search(
        self,
        query: str,
        *,
        k: int = 5,
        types: list[str] | None = None,
        passages: int = 1,
        language: str | None = None,
        repos: list[str] | None = None,
    ) -> dict[str, Any]:
        if not query.strip():
            raise ValueError("query cannot be empty")
        payload: dict[str, Any] = {
            "query": query,
            "k": max(1, min(int(k), 100)),
            "passages": max(1, min(int(passages), 5)),
            "origin": _ORIGIN,
        }
        if types:
            allowed = {"doc", "issue", "pull_request", "readme"}
            payload["types"] = [t for t in types if t in allowed] or None
        if language:
            payload["language"] = language
        if repos:
            payload["repos"] = repos[:20]
        payload = {k_: v for k_, v in payload.items() if v is not None}
        return await self._request("POST", "/search/developer", json=payload)

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        sources: list[str] | None = None,
        categories: list[str] | None = None,
        tbs: str | None = None,
        tool_detail: str | None = None,
    ) -> Paid:
        """Web search (snippets only, never scrapes). With ``"alexandria"`` in ``sources``
        it also returns matching Alexandria tools (free)."""
        if not query.strip():
            raise ValueError("query cannot be empty")
        limit = max(1, min(int(limit), 100))
        payload: dict[str, Any] = {
            "query": query[:500],
            "limit": limit,
            "sources": sources or ["web"],
            "origin": _ORIGIN,
        }
        if categories:
            payload["categories"] = categories
        if tbs:
            payload["tbs"] = tbs
        if tool_detail:
            payload["toolDetail"] = tool_detail
        body = await self._request("POST", "/search", json=payload)
        reported = body.get("creditsUsed")
        if isinstance(reported, (int, float)) and reported >= 0:
            return Paid(body, float(reported), True)
        web = "web" in payload["sources"]
        return Paid(body, float(search_credits(limit)) if web else 0.0)

    async def scrape(self, url: str, *, timeout_ms: int = 45_000) -> Paid:
        """One page as main-content markdown. PDFs are capped at SCRAPE_MAX_PDF_PAGES pages."""
        if not re.match(r"^https?://", url or "", re.IGNORECASE):
            raise ValueError("url must be http(s)")
        payload = {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
            "parsers": [{"type": "pdf", "maxPages": SCRAPE_MAX_PDF_PAGES}],
            "timeout": timeout_ms,
            "origin": _ORIGIN,
        }
        body = await self._request(
            "POST", "/scrape", json=payload, timeout=timeout_ms / 1000 + 15
        )
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        reported = meta.get("creditsUsed")
        if isinstance(reported, (int, float)) and reported >= 0:
            return Paid(body, float(reported), True)
        return Paid(
            body, float(1 + min(int(meta.get("numPages") or 0), SCRAPE_MAX_PDF_PAGES))
        )

    async def run_tool(
        self,
        provider: str,
        capability: str,
        options: dict[str, Any] | None = None,
        *,
        listed_credits: float = 0.0,
        timeout_ms: int = 60_000,
    ) -> Paid:
        """Run one Alexandria tool. Billed at the tool's listed price (``listed_credits``
        stands in when the response does not state the charge)."""
        if not provider.strip() or not capability.strip():
            raise ValueError("provider and capability are required")
        call: dict[str, Any] = {
            "provider": provider.strip(),
            "capability": capability.strip(),
        }
        if options:
            call["options"] = options
        request_id = str(uuid.uuid4())
        assert _SAFE_REQUEST_ID.fullmatch(request_id)
        body = await self._request(
            "POST",
            "/scrape",
            json={"alexandria": [call], "timeout": timeout_ms, "origin": _ORIGIN},
            timeout=timeout_ms / 1000 + 30,
            headers={"x-request-id": request_id},
        )
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        cost = data.get("creditsCost")
        if isinstance(cost, (int, float)) and cost >= 0:
            return Paid(body, float(cost), True)
        return Paid(body, float(listed_credits))
