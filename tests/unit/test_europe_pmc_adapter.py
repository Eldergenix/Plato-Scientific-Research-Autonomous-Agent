"""Unit tests for :mod:`plato.retrieval.sources.europe_pmc`."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plato.retrieval import list_adapters
from plato.retrieval.sources.europe_pmc import EuropePMCAdapter
from plato.state.models import Source


SAMPLE_PAYLOAD: dict[str, Any] = {
    "version": "6.9",
    "hitCount": 1,
    "resultList": {
        "result": [
            {
                "id": "PMC13099841",
                "source": "PMC",
                "pmcid": "PMC13099841",
                "doi": "10.3389/frai.2026.1234567",
                "title": "The transformative impact of AI-enabled AlphaFold 3",
                "authorList": {
                    "author": [
                        {"fullName": "Chakraborty C"},
                        {"firstName": "Manojit", "lastName": "Bhattacharya"},
                    ]
                },
                "journalInfo": {
                    "yearOfPublication": 2026,
                    "journal": {"title": "Frontiers in artificial intelligence"},
                },
                "abstractText": "AlphaFold 3 changed structural biology workflows.",
                "fullTextUrlList": {
                    "fullTextUrl": [
                        {
                            "documentStyle": "html",
                            "url": "https://europepmc.org/articles/PMC13099841",
                        },
                        {
                            "documentStyle": "pdf",
                            "url": "https://europepmc.org/articles/PMC13099841?pdf=render",
                        },
                    ]
                },
            }
        ]
    },
}


def _build_response(payload: dict[str, Any]) -> httpx.Response:
    request = httpx.Request(
        "GET",
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
    )
    return httpx.Response(200, json=payload, request=request)


def test_europe_pmc_adapter_is_registered() -> None:
    assert "europe_pmc" in list_adapters()


def test_europe_pmc_adapter_name() -> None:
    assert EuropePMCAdapter.name == "europe_pmc"


@pytest.mark.asyncio
async def test_search_maps_payload_to_source() -> None:
    adapter = EuropePMCAdapter()

    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(return_value=_build_response(SAMPLE_PAYLOAD)),
    ):
        sources = await adapter.search("alphafold", limit=10)

    assert len(sources) == 1
    src = sources[0]
    assert isinstance(src, Source)
    assert src.id == "europe_pmc:PMC:PMC13099841"
    assert src.doi == "10.3389/frai.2026.1234567"
    assert src.title == "The transformative impact of AI-enabled AlphaFold 3"
    assert src.authors == ["Chakraborty C", "Manojit Bhattacharya"]
    assert src.year == 2026
    assert src.venue == "Frontiers in artificial intelligence"
    assert src.abstract == "AlphaFold 3 changed structural biology workflows."
    assert src.url == "https://europepmc.org/articles/PMC13099841"
    assert src.pdf_url == "https://europepmc.org/articles/PMC13099841?pdf=render"
    assert src.retrieved_via == "europe_pmc"
    assert src.fetched_at is not None


@pytest.mark.asyncio
async def test_search_skips_unusable_rows() -> None:
    adapter = EuropePMCAdapter()
    payload = {
        "resultList": {
            "result": [
                {"id": "1", "source": "MED"},  # missing title
                {"title": "No stable identifier"},  # missing id/source/doi
                {"id": "2", "source": "MED", "title": "Valid"},
            ]
        }
    }

    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(return_value=_build_response(payload)),
    ):
        sources = await adapter.search("q", limit=10)

    assert len(sources) == 1
    assert sources[0].id == "europe_pmc:MED:2"
    assert sources[0].title == "Valid"


@pytest.mark.asyncio
async def test_search_empty_payload() -> None:
    adapter = EuropePMCAdapter()

    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(return_value=_build_response({"resultList": {"result": []}})),
    ):
        sources = await adapter.search("nothing", limit=5)

    assert sources == []
