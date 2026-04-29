"""Unit tests for :mod:`plato.retrieval.sources.crossref`."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plato.retrieval import list_adapters
from plato.retrieval.sources.crossref import CrossrefAdapter
from plato.state.models import Source


# ---------------------------------------------------------------------------
# Sample Crossref payload
# ---------------------------------------------------------------------------

SAMPLE_PAYLOAD: dict[str, Any] = {
    "status": "ok",
    "message-type": "work-list",
    "message": {
        "items": [
            {
                "DOI": "10.1038/S41586-021-03819-2",
                "title": [
                    "Highly accurate protein structure prediction with AlphaFold"
                ],
                "author": [
                    {"given": "John", "family": "Jumper"},
                    {"given": "Richard", "family": "Evans"},
                    # Edge case: family-only entry
                    {"family": "Pritzel"},
                ],
                "issued": {"date-parts": [[2021, 7, 15]]},
                "container-title": ["Nature"],
                "URL": "https://doi.org/10.1038/s41586-021-03819-2",
            }
        ]
    },
}


# ---------------------------------------------------------------------------
# Adapter wiring
# ---------------------------------------------------------------------------


def test_crossref_adapter_is_registered() -> None:
    assert "crossref" in list_adapters()


def test_crossref_adapter_name() -> None:
    assert CrossrefAdapter.name == "crossref"


# ---------------------------------------------------------------------------
# search() with mocked httpx
# ---------------------------------------------------------------------------


def _build_mock_response(payload: dict[str, Any]) -> httpx.Response:
    request = httpx.Request("GET", "https://api.crossref.org/works")
    return httpx.Response(200, json=payload, request=request)


@pytest.mark.asyncio
async def test_search_maps_payload_to_source() -> None:
    adapter = CrossrefAdapter()
    mock_response = _build_mock_response(SAMPLE_PAYLOAD)

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        sources = await adapter.search("alphafold", limit=10)

    assert len(sources) == 1
    src = sources[0]
    assert isinstance(src, Source)
    # DOI lowercased & used as suffix
    assert src.doi == "10.1038/s41586-021-03819-2"
    assert src.id == "crossref:10.1038/s41586-021-03819-2"
    assert src.title == "Highly accurate protein structure prediction with AlphaFold"
    assert src.authors == ["John Jumper", "Richard Evans", "Pritzel"]
    assert src.year == 2021
    assert src.venue == "Nature"
    assert src.url == "https://doi.org/10.1038/s41586-021-03819-2"
    assert src.retrieved_via == "crossref"
    assert src.fetched_at is not None


@pytest.mark.asyncio
async def test_search_skips_items_without_doi_or_title() -> None:
    adapter = CrossrefAdapter()
    payload = {
        "message": {
            "items": [
                {"DOI": "10.1234/no-title"},  # missing title
                {"title": ["No DOI"]},  # missing DOI
                {
                    "DOI": "10.1234/valid",
                    "title": ["The valid one"],
                },
            ]
        }
    }
    mock_response = _build_mock_response(payload)

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        sources = await adapter.search("q", limit=10)

    assert len(sources) == 1
    assert sources[0].doi == "10.1234/valid"
    assert sources[0].title == "The valid one"


@pytest.mark.asyncio
async def test_search_handles_missing_optional_fields() -> None:
    adapter = CrossrefAdapter()
    payload = {
        "message": {
            "items": [
                {
                    "DOI": "10.5555/min",
                    "title": ["Bare-bones"],
                }
            ]
        }
    }
    mock_response = _build_mock_response(payload)

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        sources = await adapter.search("q", limit=1)

    assert len(sources) == 1
    src = sources[0]
    assert src.doi == "10.5555/min"
    assert src.title == "Bare-bones"
    assert src.authors == []
    assert src.year is None
    assert src.venue is None
    # When URL is missing, we synthesize one from the DOI
    assert src.url == "https://doi.org/10.5555/min"


@pytest.mark.asyncio
async def test_search_empty_payload() -> None:
    adapter = CrossrefAdapter()
    mock_response = _build_mock_response({"message": {"items": []}})

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        sources = await adapter.search("nothingness", limit=10)

    assert sources == []
