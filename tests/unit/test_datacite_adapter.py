"""Unit tests for :mod:`plato.retrieval.sources.datacite`."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plato.retrieval import list_adapters
from plato.retrieval.sources.datacite import DataCiteAdapter
from plato.state.models import Source


SAMPLE_PAYLOAD: dict[str, Any] = {
    "data": [
        {
            "id": "10.5281/zenodo.12345",
            "type": "dois",
            "attributes": {
                "doi": "10.5281/ZENODO.12345",
                "creators": [{"name": "Doe, Ada"}, {"givenName": "Grace", "familyName": "Hopper"}],
                "titles": [{"title": "A reproducible benchmark dataset"}],
                "publisher": "Zenodo",
                "publicationYear": 2025,
                "types": {"resourceTypeGeneral": "Dataset"},
                "descriptions": [
                    {"description": "General note", "descriptionType": "Other"},
                    {"description": "Benchmark data for method validation.", "descriptionType": "Abstract"},
                ],
                "url": "https://zenodo.org/records/12345",
                "contentUrl": "https://zenodo.org/records/12345/files/paper.pdf",
            },
        }
    ]
}


def _build_response(payload: dict[str, Any]) -> httpx.Response:
    request = httpx.Request("GET", "https://api.datacite.org/dois")
    return httpx.Response(200, json=payload, request=request)


def test_datacite_adapter_is_registered() -> None:
    assert "datacite" in list_adapters()


def test_datacite_adapter_name() -> None:
    assert DataCiteAdapter.name == "datacite"


@pytest.mark.asyncio
async def test_search_maps_payload_to_source() -> None:
    adapter = DataCiteAdapter()

    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(return_value=_build_response(SAMPLE_PAYLOAD)),
    ):
        sources = await adapter.search("benchmark", limit=10)

    assert len(sources) == 1
    src = sources[0]
    assert isinstance(src, Source)
    assert src.id == "datacite:10.5281/zenodo.12345"
    assert src.doi == "10.5281/zenodo.12345"
    assert src.title == "A reproducible benchmark dataset"
    assert src.authors == ["Doe, Ada", "Grace Hopper"]
    assert src.year == 2025
    assert src.venue == "Zenodo"
    assert src.abstract == "Benchmark data for method validation."
    assert src.pdf_url == "https://zenodo.org/records/12345/files/paper.pdf"
    assert src.url == "https://zenodo.org/records/12345"
    assert src.retrieved_via == "datacite"


@pytest.mark.asyncio
async def test_search_skips_records_without_doi_or_title() -> None:
    adapter = DataCiteAdapter()
    payload = {
        "data": [
            {"attributes": {"doi": "10.1234/no-title"}},
            {"attributes": {"titles": [{"title": "No DOI"}]}},
            {
                "attributes": {
                    "doi": "10.1234/valid",
                    "titles": [{"title": "Valid record"}],
                }
            },
        ]
    }

    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(return_value=_build_response(payload)),
    ):
        sources = await adapter.search("q", limit=10)

    assert len(sources) == 1
    assert sources[0].doi == "10.1234/valid"
    assert sources[0].title == "Valid record"


@pytest.mark.asyncio
async def test_search_empty_payload() -> None:
    adapter = DataCiteAdapter()

    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(return_value=_build_response({"data": []})),
    ):
        sources = await adapter.search("nothing", limit=5)

    assert sources == []
