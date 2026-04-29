"""
Phase 2 (R4) — arXiv ``SourceAdapter``.

This adapter hits the public arXiv export API
(https://export.arxiv.org/api/query) and parses the returned Atom feed
into :class:`plato.state.models.Source` records.

Design notes
------------
* The arXiv export endpoint is **not** authenticated and is rate-limited
  to roughly one request every 3 seconds; callers (the orchestrator) are
  expected to obey that — this module focuses on protocol conformance and
  pure parsing.
* We deliberately avoid the ``feedparser`` third-party dep and parse with
  ``xml.etree.ElementTree`` from the stdlib. The Atom feed uses two
  namespaces (``atom`` and ``arxiv``) which we handle explicitly.
* This module auto-registers the adapter at import time so that simply
  importing ``plato.retrieval.sources.arxiv`` is enough to make
  ``"arxiv"`` show up in :data:`plato.retrieval.ADAPTER_REGISTRY`.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote_plus

import httpx

from .. import register_adapter
from ...state.models import Source

logger = logging.getLogger(__name__)

ARXIV_ENDPOINT = "http://export.arxiv.org/api/query"

# Atom feed namespaces used by the arXiv API.
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# Match either an abs/<id> or pdf/<id> URL ending in optional version.
# Captures the bare arXiv identifier — both new-style ("2401.12345") and
# old-style ("astro-ph/0601001") IDs are accepted.
_ARXIV_ID_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf)/([A-Za-z\-.]+/\d+|\d{4}\.\d{4,5})(v\d+)?",
    re.IGNORECASE,
)


def _extract_arxiv_id(url: str | None) -> str | None:
    """Pull the arXiv identifier out of an abs/pdf URL. Returns None on miss."""
    if not url:
        return None
    m = _ARXIV_ID_RE.search(url)
    if not m:
        return None
    return m.group(1)


def _text(el: ET.Element | None) -> str | None:
    """Return ``el.text`` stripped, or None if the element is missing/empty."""
    if el is None or el.text is None:
        return None
    txt = el.text.strip()
    return txt or None


def _parse_year(published: str | None) -> int | None:
    """Extract a 4-digit year from an Atom ``<published>`` timestamp."""
    if not published:
        return None
    # Atom timestamps look like "2024-01-15T17:00:00Z".
    m = re.match(r"(\d{4})", published)
    return int(m.group(1)) if m else None


def _parse_entry(entry: ET.Element) -> Source | None:
    """Convert one ``<entry>`` element to a Source. Returns None if unparsable."""
    title = _text(entry.find("atom:title", _NS))
    if not title:
        return None
    # arXiv often wraps titles across multiple lines — collapse whitespace.
    title = re.sub(r"\s+", " ", title)

    abstract = _text(entry.find("atom:summary", _NS))
    if abstract:
        abstract = re.sub(r"\s+", " ", abstract)

    authors: list[str] = []
    for author_el in entry.findall("atom:author", _NS):
        name = _text(author_el.find("atom:name", _NS))
        if name:
            authors.append(name)

    # The <id> element holds the canonical abs URL.
    abs_url = _text(entry.find("atom:id", _NS))
    arxiv_id = _extract_arxiv_id(abs_url)

    # Walk <link> elements to find the PDF URL and (failing the <id> match)
    # the abstract URL.
    pdf_url: str | None = None
    alt_url: str | None = None
    for link in entry.findall("atom:link", _NS):
        href = link.get("href")
        if not href:
            continue
        rel = link.get("rel")
        link_type = link.get("type")
        title_attr = link.get("title")
        if title_attr == "pdf" or link_type == "application/pdf":
            pdf_url = href
        elif rel == "alternate":
            alt_url = href

    if arxiv_id is None:
        arxiv_id = _extract_arxiv_id(alt_url) or _extract_arxiv_id(pdf_url)

    year = _parse_year(_text(entry.find("atom:published", _NS)))

    if arxiv_id is None:
        # Without a stable identifier we cannot build a usable Source ID;
        # skip rather than emitting a dangling record.
        logger.debug("Skipping arXiv entry without parseable id: %s", abs_url)
        return None

    return Source(
        id=f"arxiv:{arxiv_id}",
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        year=year,
        abstract=abstract,
        pdf_url=pdf_url,
        url=alt_url or abs_url,
        retrieved_via="arxiv",
        fetched_at=datetime.now(timezone.utc),
    )


def _parse_feed(xml_text: str) -> list[Source]:
    """Parse a full Atom feed string into a list of Sources."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("arXiv feed parse error: %s", exc)
        return []

    sources: list[Source] = []
    for entry in root.findall("atom:entry", _NS):
        src = _parse_entry(entry)
        if src is not None:
            sources.append(src)
    return sources


class ArxivAdapter:
    """`SourceAdapter` implementation backed by the arXiv export API."""

    name = "arxiv"

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._timeout = timeout

    async def search(self, query: str, limit: int) -> list[Source]:
        """Run a free-text search against arXiv and return up to ``limit`` Sources."""
        if limit <= 0:
            return []
        params = {
            "search_query": f"all:{quote_plus(query)}",
            "start": "0",
            "max_results": str(limit),
        }
        # We build the URL by hand so we can keep the ``all:`` prefix verbatim
        # — httpx would otherwise re-encode the colon and trip arXiv's parser.
        url = (
            f"{ARXIV_ENDPOINT}"
            f"?search_query={params['search_query']}"
            f"&start={params['start']}"
            f"&max_results={params['max_results']}"
        )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return _parse_feed(response.text)


# Auto-register on import so that callers only need to ``import
# plato.retrieval.sources.arxiv`` (or import the package) to make the
# adapter discoverable via :func:`plato.retrieval.get_adapter`.
register_adapter(ArxivAdapter(), overwrite=True)


__all__ = ["ArxivAdapter"]
