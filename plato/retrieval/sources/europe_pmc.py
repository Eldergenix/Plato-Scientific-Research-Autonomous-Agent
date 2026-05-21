"""
Europe PMC retrieval adapter.

Hits Europe PMC's public REST search endpoint and maps
``resultList.result[*]`` into :class:`plato.state.models.Source` records.
The endpoint is public and requires no API key.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx  # noqa: F401  # kept so ``patch("httpx.AsyncClient.get", ...)`` resolves.

from .. import register_adapter
from ..doi import normalize_doi
from ..middleware import RetrievalClient
from ...state.models import Source

__all__ = ["EuropePMCAdapter"]


_EUROPE_PMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_USER_AGENT = "Plato/1.0 (mailto:plato.astropilot.ai@gmail.com)"


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _coerce_year(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, int):
            return value if 1500 <= value <= 2100 else None
        if not isinstance(value, str) or not value.strip():
            continue
        head = value.strip()[:4]
        try:
            year = int(head)
        except ValueError:
            continue
        if 1500 <= year <= 2100:
            return year
    return None


def _extract_authors(item: dict[str, Any]) -> list[str]:
    author_list = item.get("authorList")
    raw_authors = author_list.get("author") if isinstance(author_list, dict) else None
    names: list[str] = []
    if isinstance(raw_authors, list):
        for entry in raw_authors:
            if not isinstance(entry, dict):
                continue
            full_name = _text(entry.get("fullName"))
            if full_name:
                names.append(full_name)
                continue
            first = _text(entry.get("firstName")) or ""
            last = _text(entry.get("lastName")) or ""
            name = f"{first} {last}".strip()
            if name:
                names.append(name)

    if names:
        return names

    author_string = _text(item.get("authorString"))
    if not author_string:
        return []
    return [part.strip().rstrip(".") for part in author_string.split(",") if part.strip()]


def _extract_venue(item: dict[str, Any]) -> str | None:
    journal_info = item.get("journalInfo")
    if isinstance(journal_info, dict):
        journal = journal_info.get("journal")
        if isinstance(journal, dict):
            title = _text(journal.get("title"))
            if title:
                return title
        for key in ("journalTitle", "medlineAbbreviation"):
            value = _text(journal_info.get(key))
            if value:
                return value
    return _text(item.get("journalTitle"))


def _full_text_urls(item: dict[str, Any]) -> list[dict[str, Any]]:
    full_text_list = item.get("fullTextUrlList")
    raw = full_text_list.get("fullTextUrl") if isinstance(full_text_list, dict) else None
    if not isinstance(raw, list):
        return []
    return [entry for entry in raw if isinstance(entry, dict)]


def _extract_pdf_url(item: dict[str, Any]) -> str | None:
    for entry in _full_text_urls(item):
        url = _text(entry.get("url"))
        if not url:
            continue
        style = (_text(entry.get("documentStyle")) or "").lower()
        if style == "pdf" or ".pdf" in url.lower() or "pdf=render" in url.lower():
            return url
    return None


def _extract_url(item: dict[str, Any]) -> str | None:
    for entry in _full_text_urls(item):
        url = _text(entry.get("url"))
        if url and (_text(entry.get("documentStyle")) or "").lower() == "html":
            return url

    source = _text(item.get("source"))
    record_id = _text(item.get("id"))
    pmcid = _text(item.get("pmcid"))
    pmid = _text(item.get("pmid"))
    if pmcid:
        return f"https://europepmc.org/articles/{pmcid}"
    if source and record_id:
        return f"https://europepmc.org/article/{source}/{record_id}"
    if pmid:
        return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    return None


def _stable_id(item: dict[str, Any], doi: str | None) -> str | None:
    source = _text(item.get("source"))
    record_id = _text(item.get("id"))
    if source and record_id:
        return f"europe_pmc:{source}:{record_id}"
    pmcid = _text(item.get("pmcid"))
    if pmcid:
        return f"europe_pmc:{pmcid}"
    pmid = _text(item.get("pmid"))
    if pmid:
        return f"europe_pmc:MED:{pmid}"
    if doi:
        return f"europe_pmc:{doi}"
    return None


def _map_item_to_source(item: dict[str, Any]) -> Source | None:
    title = _text(item.get("title"))
    doi = normalize_doi(item.get("doi"))
    stable_id = _stable_id(item, doi)
    if not title or not stable_id:
        return None

    journal_info = item.get("journalInfo")
    journal_year = (
        journal_info.get("yearOfPublication") if isinstance(journal_info, dict) else None
    )

    return Source(
        id=stable_id,
        doi=doi,
        title=title,
        authors=_extract_authors(item),
        year=_coerce_year(
            item.get("pubYear"),
            journal_year,
            item.get("firstPublicationDate"),
            item.get("dateOfPublication"),
        ),
        venue=_extract_venue(item),
        abstract=_text(item.get("abstractText")),
        pdf_url=_extract_pdf_url(item),
        url=_extract_url(item),
        retrieved_via="europe_pmc",
        fetched_at=datetime.now(timezone.utc),
    )


class EuropePMCAdapter:
    """SourceAdapter hitting Europe PMC's public article search endpoint."""

    name = "europe_pmc"

    def __init__(
        self,
        *,
        search_url: str = _EUROPE_PMC_SEARCH_URL,
        user_agent: str = _USER_AGENT,
        timeout: float = 20.0,
    ) -> None:
        self._search_url = search_url
        self._user_agent = user_agent
        self._timeout = timeout

    async def search(self, query: str, limit: int) -> list[Source]:
        page_size = max(1, min(int(limit), 1000))
        params = urlencode(
            {
                "query": query,
                "resultType": "core",
                "format": "json",
                "pageSize": page_size,
            }
        )
        url = f"{self._search_url}?{params}"
        headers = {"User-Agent": self._user_agent}

        async with RetrievalClient(timeout=self._timeout, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()

        result_list = payload.get("resultList") if isinstance(payload, dict) else None
        items = result_list.get("result") if isinstance(result_list, dict) else None
        if not isinstance(items, list):
            return []

        sources: list[Source] = []
        for item in items[:page_size]:
            if not isinstance(item, dict):
                continue
            mapped = _map_item_to_source(item)
            if mapped is not None:
                sources.append(mapped)
        return sources


register_adapter(EuropePMCAdapter(), overwrite=True)
