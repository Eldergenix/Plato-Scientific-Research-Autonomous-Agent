"""Unit tests for :mod:`plato.retrieval.sources.opencitations`."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plato.retrieval import list_adapters
from plato.retrieval.sources.opencitations import OpenCitationsAdapter
from plato.state.models import Source


SAMPLE_PAYLOAD: list[dict[str, Any]] = [
    {
        "id": "doi:10.1038/s41586-021-03819-2 openalex:W3177828909 pmid:34265844",
        "title": "Highly Accurate Protein Structure Prediction With AlphaFold",
        "author": (
            "Jumper, John [orcid:0000-0001-6169-6580]; "
            "Evans, Richard; Pritzel, Alexander"
        ),
        "pub_date": "2021-07-15",
        "venue": "Nature [issn:0028-0836]",
        "type": "journal article",
        "publisher": "Springer Science And Business Media Llc [crossref:297]",
    }
]


def _build_response(payload: list[dict[str, Any]]) -> httpx.Response:
    request = httpx.Request(
        "GET",
        "https://api.opencitations.net/meta/v1/metadata/doi:10.1038/s41586-021-03819-2",
    )
    return httpx.Response(200, json=payload, request=request)


def test_opencitations_adapter_is_registered() -> None:
    assert "opencitations" in list_adapters()


def test_opencitations_adapter_name() -> None:
    assert OpenCitationsAdapter.name == "opencitations"


@pytest.mark.asyncio
async def test_search_without_doi_returns_empty_without_network() -> None:
    adapter = OpenCitationsAdapter()

    with patch("httpx.AsyncClient.get", new=AsyncMock()) as get:
        sources = await adapter.search("alphafold", limit=10)

    assert sources == []
    get.assert_not_called()


@pytest.mark.asyncio
async def test_search_maps_doi_metadata_to_source() -> None:
    adapter = OpenCitationsAdapter()

    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(return_value=_build_response(SAMPLE_PAYLOAD)),
    ):
        sources = await adapter.search("doi:10.1038/s41586-021-03819-2", limit=10)

    assert len(sources) == 1
    src = sources[0]
    assert isinstance(src, Source)
    assert src.id == "opencitations:10.1038/s41586-021-03819-2"
    assert src.doi == "10.1038/s41586-021-03819-2"
    assert src.title == "Highly Accurate Protein Structure Prediction With AlphaFold"
    assert src.authors == ["John Jumper", "Richard Evans", "Alexander Pritzel"]
    assert src.year == 2021
    assert src.venue == "Nature"
    assert src.url == "https://doi.org/10.1038/s41586-021-03819-2"
    assert src.retrieved_via == "opencitations"
