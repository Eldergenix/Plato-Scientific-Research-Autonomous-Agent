"""
Phase 5 (R8) — sanity test that the migrated adapters actually run through
``RetrievalClient`` and benefit from the middleware.

The Crossref adapter is a good representative target: it has a clear JSON
contract and was previously hitting ``httpx.AsyncClient`` directly. We
monkeypatch ``httpx.AsyncClient.get`` to deliver one 429 followed by a
valid 200 payload and confirm the adapter returns the mapped Source after
the backoff fires — proving the middleware is in the call path.
"""
from __future__ import annotations

from typing import Any

import httpx
import pytest

from plato.retrieval import middleware as mw
from plato.retrieval.sources.crossref import CrossrefAdapter


_CROSSREF_PAYLOAD: dict[str, Any] = {
    "status": "ok",
    "message": {
        "items": [
            {
                "DOI": "10.1234/abc",
                "title": ["Backed off and retried"],
                "author": [{"given": "Ada", "family": "Lovelace"}],
                "issued": {"date-parts": [[2024]]},
                "container-title": ["Journal of Tests"],
                "URL": "https://doi.org/10.1234/abc",
            }
        ]
    },
}


@pytest.mark.asyncio
async def test_adapter_retries_through_middleware_on_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One 429 then a 200 — the middleware must turn that into a single Source."""

    # Skip the real backoff sleep so the test runs instantly.
    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(mw.asyncio, "sleep", fake_sleep)

    calls: list[str] = []
    responses: list[httpx.Response] = [
        httpx.Response(
            429,
            request=httpx.Request("GET", "https://api.crossref.org/works"),
            headers={"Retry-After": "0"},
        ),
        httpx.Response(
            200,
            request=httpx.Request("GET", "https://api.crossref.org/works"),
            json=_CROSSREF_PAYLOAD,
        ),
    ]

    async def fake_get(self: httpx.AsyncClient, url: str, **_: Any) -> httpx.Response:
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    adapter = CrossrefAdapter()
    sources = await adapter.search("anything", limit=5)

    assert len(calls) == 2, "expected one retry after the initial 429"
    assert len(sources) == 1
    assert sources[0].doi == "10.1234/abc"
    assert sources[0].title == "Backed off and retried"
    assert sources[0].retrieved_via == "crossref"
