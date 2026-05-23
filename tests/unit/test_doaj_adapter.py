"""Unit tests for :mod:`plato.retrieval.sources.doaj`."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plato.retrieval import list_adapters
from plato.retrieval.sources.doaj import DOAJAdapter
from plato.state.models import Source


SAMPLE_PAYLOAD: dict[str, Any] = {
    "total": 1,
    "results": [
        {
            "id": "0008896165294e208214362c4ac0b59e",
            "bibjson": {
                "identifier": [
                    {"id": "10.7554/eLife.101531", "type": "doi"},
                    {"id": "2050-084X", "type": "eissn"},
                ],
                "journal": {
                    "title": "eLife",
                    "publisher": "eLife Sciences Publications Ltd",
                },
                "year": "2025",
                "author": [{"name": "Yutaro Hama"}, {"name": "Yuko Fujioka"}],
                "title": "The triad interaction of ULK1, ATG13, and FIP200",
                "abstract": "The ULK complex initiates autophagy.",
                "link": [
                    {
                        "type": "fulltext",
                        "content_type": "text/html",
                        "url": "https://elifesciences.org/articles/101531",
                    }
                ],
            },
        }
    ],
}


def _build_response(payload: dict[str, Any]) -> httpx.Response:
    request = httpx.Request("GET", "https://doaj.org/api/search/articles/alphafold")
    return httpx.Response(200, json=payload, request=request)


def test_doaj_adapter_is_registered() -> None:
    assert "doaj" in list_adapters()


def test_doaj_adapter_name() -> None:
    assert DOAJAdapter.name == "doaj"


@pytest.mark.asyncio
async def test_search_maps_payload_to_source() -> None:
    adapter = DOAJAdapter()

    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(return_value=_build_response(SAMPLE_PAYLOAD)),
    ):
        sources = await adapter.search("alphafold", limit=10)

    assert len(sources) == 1
    src = sources[0]
    assert isinstance(src, Source)
    assert src.id == "doaj:0008896165294e208214362c4ac0b59e"
    assert src.doi == "10.7554/elife.101531"
    assert src.title == "The triad interaction of ULK1, ATG13, and FIP200"
    assert src.authors == ["Yutaro Hama", "Yuko Fujioka"]
    assert src.year == 2025
    assert src.venue == "eLife"
    assert src.abstract == "The ULK complex initiates autophagy."
    assert src.url == "https://elifesciences.org/articles/101531"
    assert src.retrieved_via == "doaj"


@pytest.mark.asyncio
async def test_search_skips_unusable_rows() -> None:
    adapter = DOAJAdapter()
    payload = {
        "results": [
            {"id": "missing-bibjson"},
            {
                "id": "missing-title",
                "bibjson": {"identifier": [{"type": "doi", "id": "10.1/x"}]},
            },
            {"id": "valid", "bibjson": {"title": "Valid open article"}},
        ]
    }

    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(return_value=_build_response(payload)),
    ):
        sources = await adapter.search("q", limit=10)

    assert len(sources) == 1
    assert sources[0].id == "doaj:valid"
    assert sources[0].title == "Valid open article"


@pytest.mark.asyncio
async def test_search_empty_payload() -> None:
    adapter = DOAJAdapter()

    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(return_value=_build_response({"results": []})),
    ):
        sources = await adapter.search("nothing", limit=5)

    assert sources == []
