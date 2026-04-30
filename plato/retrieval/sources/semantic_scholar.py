"""
Semantic Scholar retrieval adapter.

This adapter replaces the legacy ``literature.SSAPI`` direct call with the
canonical ``SourceAdapter`` interface so the multi-source orchestrator can
fan out to Semantic Scholar alongside arXiv / OpenAlex / Crossref / ADS.

Without this adapter, the ``astro`` ``DomainProfile``'s declared
``retrieval_sources=["semantic_scholar", "arxiv", ...]`` would silently
drop the ``semantic_scholar`` entry — the orchestrator's tolerant
fallback path logs and skips unknown adapter names.

Reads ``SEMANTIC_SCHOLAR_KEY`` from the environment for the higher
rate-limit tier; without a key the public endpoint still works (with
stricter limits).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

from .. import register_adapter
from ...state.models import Source
from ..doi import normalize_doi


__all__ = ["SemanticScholarAdapter"]


_BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_FIELDS = "title,authors,year,abstract,url,paperId,externalIds,openAccessPdf,venue"


def _read_api_key() -> str | None:
    """Optional API key for the higher rate-limit tier."""
    key = os.environ.get("SEMANTIC_SCHOLAR_KEY")
    if key and key.strip():
        return key.strip()
    return None


def _extract_doi(external_ids: dict[str, Any] | None) -> str | None:
    """Pull a normalized DOI out of Semantic Scholar's ``externalIds`` block."""
    if not isinstance(external_ids, dict):
        return None
    raw = external_ids.get("DOI")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return normalize_doi(raw)


def _extract_arxiv_id(external_ids: dict[str, Any] | None) -> str | None:
    """Pull an arXiv id out of ``externalIds``; strip the ``arXiv:`` prefix."""
    if not isinstance(external_ids, dict):
        return None
    raw = external_ids.get("ArXiv")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip()


def _extract_authors(authors: Any) -> list[str]:
    if not isinstance(authors, list):
        return []
    out: list[str] = []
    for entry in authors:
        if isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str) and name.strip():
                out.append(name.strip())
    return out


def _extract_pdf_url(open_access_pdf: Any) -> str | None:
    if isinstance(open_access_pdf, dict):
        url = open_access_pdf.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()
    return None


class SemanticScholarAdapter:
    """``SourceAdapter`` over the Semantic Scholar Graph API."""

    name = "semantic_scholar"

    async def search(self, query: str, limit: int) -> list[Source]:
        if limit <= 0 or not query:
            return []

        params = {"query": query, "limit": str(limit), "fields": _FIELDS}
        headers: dict[str, str] = {}
        api_key = _read_api_key()
        if api_key:
            headers["x-api-key"] = api_key

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                response = await client.get(_BASE_URL, params=params, headers=headers)
            except httpx.HTTPError:
                return []
            if response.status_code != 200:
                return []
            try:
                payload = response.json()
            except ValueError:
                return []

        items = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return []

        now = datetime.now(timezone.utc)
        out: list[Source] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            paper_id = item.get("paperId")
            title = item.get("title")
            if not paper_id or not title:
                continue

            external = item.get("externalIds")
            doi = _extract_doi(external)
            arxiv_id = _extract_arxiv_id(external)
            authors = _extract_authors(item.get("authors"))
            year = item.get("year") if isinstance(item.get("year"), int) else None
            abstract = item.get("abstract") if isinstance(item.get("abstract"), str) else None
            url = item.get("url") if isinstance(item.get("url"), str) else None
            venue = item.get("venue") if isinstance(item.get("venue"), str) else None
            pdf_url = _extract_pdf_url(item.get("openAccessPdf"))

            out.append(
                Source(
                    id=f"semantic_scholar:{paper_id}",
                    semantic_scholar_id=str(paper_id),
                    doi=doi,
                    arxiv_id=arxiv_id,
                    title=str(title),
                    authors=authors,
                    year=year,
                    venue=venue,
                    abstract=abstract,
                    pdf_url=pdf_url,
                    url=url,
                    retrieved_via="semantic_scholar",
                    fetched_at=now,
                )
            )
        return out


register_adapter(SemanticScholarAdapter(), overwrite=True)
