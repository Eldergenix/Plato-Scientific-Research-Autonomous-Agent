"""Unit tests for :mod:`plato.retrieval.sources.pubmed`."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plato.retrieval import ADAPTER_REGISTRY, list_adapters
from plato.retrieval.sources.pubmed import (
    PubMedAdapter,
    _extract_doi_from_articleids,
)
from plato.state.models import Source


# ---------------------------------------------------------------------------
# Sample esearch + esummary payloads (mirrors NCBI E-utilities JSON schema)
# ---------------------------------------------------------------------------

_ESEARCH_PAYLOAD: dict[str, Any] = {
    "esearchresult": {
        "count": "2",
        "retmax": "2",
        "idlist": ["12345", "67890"],
    }
}


_ESUMMARY_PAYLOAD: dict[str, Any] = {
    "header": {"type": "esummary", "version": "0.3"},
    "result": {
        "uids": ["12345", "67890"],
        "12345": {
            "uid": "12345",
            "pubdate": "2021 Jul 15",
            "source": "Nature",
            "fulljournalname": "Nature",
            "title": "CRISPR genome editing in human embryos",
            "authors": [
                {"name": "Doe J", "authtype": "Author"},
                {"name": "Smith A", "authtype": "Author"},
            ],
            "elocationid": "doi: 10.1038/s41586-021-03819-2",
            "articleids": [
                {"idtype": "pubmed", "value": "12345"},
                {"idtype": "doi", "value": "10.1038/s41586-021-03819-2"},
            ],
        },
        "67890": {
            "uid": "67890",
            "pubdate": "2019",
            "source": "Cell",
            "fulljournalname": "Cell",
            "title": "Single-cell transcriptomics of immune cells",
            "authors": [{"name": "Lee K", "authtype": "Author"}],
            "elocationid": "",
            "articleids": [
                {"idtype": "pubmed", "value": "67890"},
            ],
        },
    },
}


# ---------------------------------------------------------------------------
# Adapter wiring
# ---------------------------------------------------------------------------


def test_pubmed_adapter_name() -> None:
    assert PubMedAdapter.name == "pubmed"


def test_pubmed_adapter_is_registered() -> None:
    assert "pubmed" in list_adapters()
    assert "pubmed" in ADAPTER_REGISTRY
    assert isinstance(ADAPTER_REGISTRY["pubmed"], PubMedAdapter)


# ---------------------------------------------------------------------------
# search() with mocked httpx — esearch then esummary
# ---------------------------------------------------------------------------


def _build_mock_response(url: str, payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=payload, request=httpx.Request("GET", url))


def _two_step_responses() -> list[httpx.Response]:
    return [
        _build_mock_response(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            _ESEARCH_PAYLOAD,
        ),
        _build_mock_response(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            _ESUMMARY_PAYLOAD,
        ),
    ]


@pytest.mark.asyncio
async def test_search_maps_payload_to_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    adapter = PubMedAdapter()

    captured_urls: list[str] = []

    async def fake_get(self: httpx.AsyncClient, url: str) -> httpx.Response:
        captured_urls.append(url)
        if "esearch.fcgi" in url:
            return _build_mock_response(url, _ESEARCH_PAYLOAD)
        if "esummary.fcgi" in url:
            return _build_mock_response(url, _ESUMMARY_PAYLOAD)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    sources = await adapter.search("CRISPR", limit=2)

    # Outgoing requests: first esearch, then esummary with both PMIDs.
    assert len(captured_urls) == 2
    assert "esearch.fcgi" in captured_urls[0]
    assert "db=pubmed" in captured_urls[0]
    assert "term=CRISPR" in captured_urls[0]
    assert "retmax=2" in captured_urls[0]
    assert "esummary.fcgi" in captured_urls[1]
    assert "id=12345,67890" in captured_urls[1]
    # No api_key when NCBI_API_KEY is unset.
    assert "api_key=" not in captured_urls[0]

    assert len(sources) == 2

    first = sources[0]
    assert isinstance(first, Source)
    assert first.id == "pubmed:12345"
    assert first.title == "CRISPR genome editing in human embryos"
    assert first.authors == ["Doe J", "Smith A"]
    assert first.year == 2021
    assert first.venue == "Nature"
    assert first.url == "https://pubmed.ncbi.nlm.nih.gov/12345/"
    assert first.doi == "10.1038/s41586-021-03819-2"
    assert first.retrieved_via == "pubmed"
    assert first.fetched_at.tzinfo is not None

    second = sources[1]
    assert second.id == "pubmed:67890"
    assert second.title == "Single-cell transcriptomics of immune cells"
    assert second.authors == ["Lee K"]
    assert second.year == 2019
    assert second.venue == "Cell"
    # No DOI in elocationid OR articleids.
    assert second.doi is None


@pytest.mark.asyncio
async def test_search_doi_falls_back_to_articleids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If elocationid lacks a DOI, the adapter must scan articleids."""
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    adapter = PubMedAdapter()

    esearch = {"esearchresult": {"idlist": ["111"]}}
    esummary = {
        "result": {
            "uids": ["111"],
            "111": {
                "uid": "111",
                "title": "Articleids fallback test",
                "pubdate": "2022",
                "source": "PLOS Biology",
                "fulljournalname": "PLOS Biology",
                "authors": [{"name": "Park S"}],
                # elocationid intentionally omits a DOI keyword.
                "elocationid": "pii: e3001234",
                "articleids": [
                    {"idtype": "pubmed", "value": "111"},
                    {"idtype": "doi", "value": "10.1371/JOURNAL.PBIO.3001234"},
                ],
            },
        }
    }

    async def fake_get(self: httpx.AsyncClient, url: str) -> httpx.Response:
        if "esearch.fcgi" in url:
            return _build_mock_response(url, esearch)
        return _build_mock_response(url, esummary)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    sources = await adapter.search("anything", limit=1)
    assert len(sources) == 1
    # normalize_doi lowercases the DOI per the adapter contract.
    assert sources[0].doi == "10.1371/journal.pbio.3001234"
    assert sources[0].venue == "PLOS Biology"


@pytest.mark.asyncio
async def test_search_empty_idlist_skips_esummary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When esearch returns no PMIDs, no esummary request should be issued."""
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    adapter = PubMedAdapter()

    call_count = 0

    async def fake_get(self: httpx.AsyncClient, url: str) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if "esummary.fcgi" in url:
            raise AssertionError("esummary should not be called for empty idlist")
        return _build_mock_response(url, {"esearchresult": {"idlist": []}})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    sources = await adapter.search("nothingness", limit=10)
    assert sources == []
    assert call_count == 1


@pytest.mark.asyncio
async def test_search_skips_articles_missing_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    adapter = PubMedAdapter()

    esearch = {"esearchresult": {"idlist": ["1", "2"]}}
    esummary = {
        "result": {
            "uids": ["1", "2"],
            "1": {"uid": "1", "title": "", "pubdate": "2020"},
            "2": {"uid": "2", "title": "Has a title", "pubdate": "2020"},
        }
    }

    async def fake_get(self: httpx.AsyncClient, url: str) -> httpx.Response:
        if "esearch.fcgi" in url:
            return _build_mock_response(url, esearch)
        return _build_mock_response(url, esummary)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    sources = await adapter.search("q", limit=2)
    assert len(sources) == 1
    assert sources[0].id == "pubmed:2"


@pytest.mark.asyncio
async def test_search_uses_api_key_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """An NCBI_API_KEY should be appended to outbound URLs."""
    monkeypatch.setenv("NCBI_API_KEY", "secret-key")
    adapter = PubMedAdapter()

    captured_urls: list[str] = []

    async def fake_get(self: httpx.AsyncClient, url: str) -> httpx.Response:
        captured_urls.append(url)
        if "esearch.fcgi" in url:
            return _build_mock_response(url, {"esearchresult": {"idlist": []}})
        raise AssertionError("should not reach esummary")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    await adapter.search("q", limit=1)
    assert "api_key=secret-key" in captured_urls[0]


# ---------------------------------------------------------------------------
# _extract_doi_from_articleids — table-driven
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "article, expected",
    [
        # Valid DOI present.
        (
            {
                "articleids": [
                    {"idtype": "pubmed", "value": "1"},
                    {"idtype": "doi", "value": "10.1234/test"},
                ]
            },
            "10.1234/test",
        ),
        # First DOI wins when there are multiple.
        (
            {
                "articleids": [
                    {"idtype": "doi", "value": "10.1234/first"},
                    {"idtype": "doi", "value": "10.5678/second"},
                ]
            },
            "10.1234/first",
        ),
        # Capitalized DOI gets lowercased by normalize_doi.
        (
            {"articleids": [{"idtype": "doi", "value": "10.1038/S41586-021-03819-2"}]},
            "10.1038/s41586-021-03819-2",
        ),
        # Missing articleids field entirely.
        ({}, None),
        # articleids exists but contains no DOI entry.
        (
            {"articleids": [{"idtype": "pubmed", "value": "9999"}]},
            None,
        ),
        # DOI value is empty.
        (
            {"articleids": [{"idtype": "doi", "value": "  "}]},
            None,
        ),
        # articleids is the wrong shape — defensive.
        (
            {"articleids": "not a list"},
            None,
        ),
    ],
)
def test_extract_doi_from_articleids_table(
    article: dict[str, Any], expected: str | None
) -> None:
    assert _extract_doi_from_articleids(article) == expected


# ---------------------------------------------------------------------------
# Sanity: the adapter itself doesn't touch the network unless invoked.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    adapter = PubMedAdapter()

    error_response = httpx.Response(
        500,
        request=httpx.Request("GET", "https://eutils.ncbi.nlm.nih.gov"),
    )

    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(return_value=error_response),
    ):
        with pytest.raises(httpx.HTTPStatusError):
            await adapter.search("q", limit=5)
