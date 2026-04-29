"""Unit tests for :mod:`plato.retrieval.sources.openalex`."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plato.retrieval import list_adapters
from plato.retrieval.sources.openalex import (
    OpenAlexAdapter,
    _reconstruct_abstract,
)
from plato.state.models import Source


# ---------------------------------------------------------------------------
# Sample payload — a single OpenAlex 'work'
# ---------------------------------------------------------------------------

SAMPLE_PAYLOAD: dict[str, Any] = {
    "results": [
        {
            "id": "https://openalex.org/W2741809807",
            "doi": "https://doi.org/10.1038/S41586-021-03819-2",
            "title": "Highly accurate protein structure prediction with AlphaFold",
            "publication_year": 2021,
            "authorships": [
                {"author": {"display_name": "John Jumper"}},
                {"author": {"display_name": "Richard Evans"}},
            ],
            "abstract_inverted_index": {
                "Proteins": [0],
                "are": [1],
                "essential": [2],
                "to": [3, 5],
                "life": [4],
                "biology": [6],
            },
            "primary_location": {
                "source": {"display_name": "Nature"},
            },
            "open_access": {
                "oa_url": "https://example.org/alphafold.pdf",
            },
        }
    ],
    "meta": {"count": 1},
}


# ---------------------------------------------------------------------------
# Abstract reconstruction
# ---------------------------------------------------------------------------


def test_reconstruct_abstract_basic() -> None:
    inverted = {
        "Hello": [0],
        "world": [1],
    }
    assert _reconstruct_abstract(inverted) == "Hello world"


def test_reconstruct_abstract_word_appears_multiple_times() -> None:
    inverted = {
        "Proteins": [0],
        "are": [1],
        "essential": [2],
        "to": [3, 5],
        "life": [4],
        "biology": [6],
    }
    assert (
        _reconstruct_abstract(inverted)
        == "Proteins are essential to life to biology"
    )


@pytest.mark.parametrize("inverted", [None, {}, {"foo": []}])
def test_reconstruct_abstract_empty_returns_none(inverted: Any) -> None:
    assert _reconstruct_abstract(inverted) is None


# ---------------------------------------------------------------------------
# Adapter wiring
# ---------------------------------------------------------------------------


def test_openalex_adapter_is_registered() -> None:
    # Importing the module above triggered registration.
    assert "openalex" in list_adapters()


def test_openalex_adapter_name() -> None:
    assert OpenAlexAdapter.name == "openalex"


# ---------------------------------------------------------------------------
# search() with mocked httpx
# ---------------------------------------------------------------------------


def _build_mock_response(payload: dict[str, Any]) -> httpx.Response:
    request = httpx.Request("GET", "https://api.openalex.org/works")
    return httpx.Response(200, json=payload, request=request)


@pytest.mark.asyncio
async def test_search_maps_payload_to_source() -> None:
    adapter = OpenAlexAdapter()

    mock_response = _build_mock_response(SAMPLE_PAYLOAD)

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        sources = await adapter.search("alphafold", limit=5)

    assert len(sources) == 1
    src = sources[0]

    assert isinstance(src, Source)
    assert src.id == "openalex:W2741809807"
    assert src.openalex_id == "W2741809807"
    assert src.doi == "10.1038/s41586-021-03819-2"
    assert src.title == "Highly accurate protein structure prediction with AlphaFold"
    assert src.year == 2021
    assert src.authors == ["John Jumper", "Richard Evans"]
    assert src.venue == "Nature"
    assert src.pdf_url == "https://example.org/alphafold.pdf"
    assert src.retrieved_via == "openalex"
    assert src.fetched_at is not None
    # Abstract reconstructed from inverted index, in positional order
    assert src.abstract == "Proteins are essential to life to biology"


@pytest.mark.asyncio
async def test_search_empty_results() -> None:
    adapter = OpenAlexAdapter()
    mock_response = _build_mock_response({"results": [], "meta": {"count": 0}})

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        sources = await adapter.search("nothingness", limit=5)

    assert sources == []


@pytest.mark.asyncio
async def test_search_skips_works_missing_id_or_title() -> None:
    adapter = OpenAlexAdapter()
    payload = {
        "results": [
            {"id": "https://openalex.org/W1", "title": ""},  # blank title
            {"id": "", "title": "no id"},  # no id
            {
                "id": "https://openalex.org/W3",
                "title": "Valid one",
                "publication_year": 2020,
            },
        ]
    }
    mock_response = _build_mock_response(payload)

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        sources = await adapter.search("q", limit=5)

    assert len(sources) == 1
    assert sources[0].openalex_id == "W3"
    assert sources[0].title == "Valid one"


@pytest.mark.asyncio
async def test_search_handles_missing_optional_fields() -> None:
    adapter = OpenAlexAdapter()
    payload = {
        "results": [
            {
                "id": "https://openalex.org/W42",
                "title": "Minimal record",
            }
        ]
    }
    mock_response = _build_mock_response(payload)

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        sources = await adapter.search("q", limit=1)

    assert len(sources) == 1
    src = sources[0]
    assert src.openalex_id == "W42"
    assert src.title == "Minimal record"
    assert src.doi is None
    assert src.year is None
    assert src.venue is None
    assert src.abstract is None
    assert src.authors == []
    assert src.pdf_url is None
