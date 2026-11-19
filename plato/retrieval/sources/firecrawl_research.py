"""Firecrawl Research Index adapter (``firecrawl_research``).

Semantic search over ~43M paper abstracts (PubMed, bioRxiv, medRxiv and arXiv) through
``GET /v2/search/research/papers``; every result carries its abstract. Search results
have no authors or dates, so each paper is completed from the paper detail endpoint
(best effort). Both endpoints are free. Without ``FIRECRAWL_API_KEY`` the adapter
returns no results, like the ADS adapter without its key.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from ...state.models import Source
from .. import register_adapter
from ..doi import normalize_doi
from ..firecrawl import FirecrawlClient, FirecrawlError, api_key

__all__ = ["FirecrawlResearchAdapter", "paper_to_source"]

logger = logging.getLogger(__name__)

# Concurrent detail lookups per search.
_DETAIL_CONCURRENCY = 4


def _first(ids: Any, namespace: str) -> str | None:
    if not isinstance(ids, dict):
        return None
    values = ids.get(namespace)
    if isinstance(values, list) and values and isinstance(values[0], str):
        return values[0].strip() or None
    if isinstance(values, str):
        return values.strip() or None
    return None


def _from_primary(primary: Any, namespace: str) -> str | None:
    if isinstance(primary, str) and primary.lower().startswith(f"{namespace}:"):
        return primary.split(":", 1)[1].strip() or None
    return None


def _identifier(paper: dict[str, Any], namespace: str) -> str | None:
    return _first(paper.get("ids"), namespace) or _from_primary(
        paper.get("primaryId"), namespace
    )


def _year(*dates: Any) -> int | None:
    for value in dates:
        if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
            year = int(value[:4])
            if 1500 <= year <= 2100:
                return year
    return None


def _authors(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(a).strip() for a in value if str(a).strip()][:50]
    if isinstance(value, str):
        return [a.strip() for a in value.split(",") if a.strip()][:50]
    return []


def paper_to_source(
    paper: dict[str, Any], detail: dict[str, Any] | None = None
) -> Source | None:
    """Map a Research Index paper (search or similar result, plus optional detail) to a
    Source. ``web:`` results are web pages surfaced for display, not papers: skipped."""
    detail = detail or {}
    paper_id = str(paper.get("paperId") or detail.get("paperId") or "").strip()
    title = str(paper.get("title") or detail.get("title") or "").strip()
    if not paper_id or not title or paper_id.startswith("web:"):
        return None
    merged = {**paper, "ids": paper.get("ids") or detail.get("ids")}
    doi = normalize_doi(_identifier(merged, "doi"))
    arxiv_id = _identifier(merged, "arxiv")
    pmid = _identifier(merged, "pmid")
    pmcid = _identifier(merged, "pmcid")
    if arxiv_id:
        url = f"https://arxiv.org/abs/{arxiv_id}"
    elif pmid:
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    elif pmcid:
        url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
    elif doi:
        url = f"https://doi.org/{doi}"
    else:
        url = None
    abstract = (
        str(paper.get("abstract") or detail.get("abstract") or "").strip() or None
    )
    return Source(
        id=f"firecrawl:{paper_id}"[:256],
        doi=doi,
        arxiv_id=arxiv_id[:64] if arxiv_id else None,
        title=title[:1024],
        authors=_authors(detail.get("authors") or paper.get("authors")),
        year=_year(
            detail.get("createdDate"),
            paper.get("createdDate"),
            detail.get("updateDate"),
            paper.get("updateDate"),
        ),
        abstract=abstract[:32768] if abstract else None,
        url=url,
        retrieved_via="firecrawl_research",
        fetched_at=datetime.now(UTC),
    )


class FirecrawlResearchAdapter:
    name = "firecrawl_research"

    def __init__(
        self, *, client: FirecrawlClient | None = None, enrich: bool = True
    ) -> None:
        self._client = client
        self._enrich = enrich

    async def search(self, query: str, limit: int) -> list[Source]:
        if self._client is None and not api_key():
            logger.debug(
                "FIRECRAWL_API_KEY not set; firecrawl_research adapter is a no-op"
            )
            return []
        client = self._client or FirecrawlClient()
        try:
            results = await client.search_papers(query, k=max(1, min(int(limit), 50)))
            papers = [
                r for r in results if not str(r.get("paperId", "")).startswith("web:")
            ]
            papers = papers[: max(1, int(limit))]
            details: list[dict[str, Any] | None] = [None] * len(papers)
            if self._enrich and papers:
                sem = asyncio.Semaphore(_DETAIL_CONCURRENCY)

                async def one(i: int, pid: str) -> None:
                    async with sem:
                        try:
                            body = await client.get_paper(pid)
                        except (FirecrawlError, ValueError) as exc:
                            logger.info(
                                "firecrawl paper detail %s failed: %s", pid, exc
                            )
                            return
                    paper = body.get("paper")
                    details[i] = paper if isinstance(paper, dict) else None

                await asyncio.gather(
                    *(one(i, str(p.get("paperId") or "")) for i, p in enumerate(papers))
                )
            sources = [
                paper_to_source(p, d) for p, d in zip(papers, details, strict=True)
            ]
            return [s for s in sources if s is not None]
        finally:
            if self._client is None:
                await client.aclose()


register_adapter(FirecrawlResearchAdapter(), overwrite=True)
