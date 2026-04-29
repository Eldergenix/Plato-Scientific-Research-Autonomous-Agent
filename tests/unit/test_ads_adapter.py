"""Unit tests for ``plato.retrieval.sources.ads.ADSAdapter``.

Tests must never make real network calls — :mod:`httpx.AsyncClient.get` is
patched on each test that exercises the request path. Token state is
controlled per-test via ``monkeypatch``.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from plato.retrieval import ADAPTER_REGISTRY, get_adapter
from plato.retrieval.sources.ads import ADSAdapter
from plato.state.models import Source


_SAMPLE_ADS_JSON = json.dumps(
    {
        "responseHeader": {"status": 0, "QTime": 12},
        "response": {
            "numFound": 1,
            "start": 0,
            "docs": [
                {
                    "bibcode": "2024ApJ...999..123X",
                    "title": ["Dark Matter and the Cosmic Web"],
                    "author": ["Doe, J.", "Smith, A.", "Lee, K."],
                    "year": "2024",
                    "doi": ["10.3847/1538-4357/ABCDEF"],
                    "abstract": "We measure the dark-matter halo distribution.",
                    "pub": "The Astrophysical Journal",
                    "arxiv_class": ["astro-ph.CO"],
                    "identifier": [
                        "2024ApJ...999..123X",
                        "arXiv:2401.12345",
                        "10.3847/1538-4357/abcdef",
                    ],
                }
            ],
        },
    }
)


def test_adapter_in_registry_after_import():
    """Importing the adapter module should auto-register ``"ads"``."""
    assert "ads" in ADAPTER_REGISTRY
    assert isinstance(get_adapter("ads"), ADSAdapter)


@pytest.mark.asyncio
async def test_search_parses_sample_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """With a token set and a mocked httpx client, search yields a correct Source."""
    monkeypatch.setenv("ADS_API_KEY", "fake-token-for-tests")
    monkeypatch.delenv("ADS_DEV_KEY", raising=False)

    captured: dict[str, Any] = {}

    async def fake_get(self: httpx.AsyncClient, url: str, headers: dict[str, str] | None = None):
        captured["url"] = url
        captured["headers"] = headers or {}
        request = httpx.Request("GET", url)
        return httpx.Response(200, content=_SAMPLE_ADS_JSON.encode(), request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    adapter = ADSAdapter()
    results = await adapter.search("dark matter", limit=5)

    assert len(results) == 1
    src = results[0]
    assert isinstance(src, Source)
    assert src.id == "ads:2024ApJ...999..123X"
    assert src.title == "Dark Matter and the Cosmic Web"
    assert src.authors == ["Doe, J.", "Smith, A.", "Lee, K."]
    assert src.year == 2024
    # DOI must be normalized lowercase per spec.
    assert src.doi == "10.3847/1538-4357/abcdef"
    assert src.abstract == "We measure the dark-matter halo distribution."
    assert src.venue == "The Astrophysical Journal"
    assert src.arxiv_id == "2401.12345"
    assert src.retrieved_via == "ads"
    assert src.fetched_at.tzinfo is not None

    # Outgoing request should carry bearer token + spec'd query params.
    assert captured["headers"].get("Authorization") == "Bearer fake-token-for-tests"
    assert "q=dark+matter" in captured["url"] or "q=dark%20matter" in captured["url"]
    assert "rows=5" in captured["url"]
    assert "bibcode" in captured["url"]
    assert captured["url"].startswith("https://api.adsabs.harvard.edu/v1/search/query?")


@pytest.mark.asyncio
async def test_search_without_token_returns_empty_and_warns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a token, search must return ``[]`` and emit a RuntimeWarning."""
    monkeypatch.delenv("ADS_API_KEY", raising=False)
    monkeypatch.delenv("ADS_DEV_KEY", raising=False)

    # Guard: any attempt to hit the network should fail loudly so we know the
    # no-op path was actually taken.
    async def boom(*args: Any, **kwargs: Any):
        raise AssertionError("network should not be touched without a token")

    monkeypatch.setattr(httpx.AsyncClient, "get", boom)

    adapter = ADSAdapter()
    with pytest.warns(RuntimeWarning, match="ADS_API_KEY not set"):
        results = await adapter.search("anything", limit=10)

    assert results == []
