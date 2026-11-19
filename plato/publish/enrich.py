"""Complete reference metadata from Crossref before formatting.

Literature search returns title, authors, year and DOI, but journals want complete
references (journal, volume, issue, pages or article number). For every cited paper
with a DOI and no cached record, the Crossref REST API is asked once; the result is
cached on the knowledge asset (``metadata.crossref``) so later exports and other
campaigns of the program reuse it. A failed lookup never blocks an export.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

CROSSREF = "https://api.crossref.org/works/"
# Crossref asks automated clients to identify themselves; no personal data is sent.
USER_AGENT = "Plato-scientist/1.0 (+https://jarvisos.xyz)"
_TYPES = {
    "journal-article": "article-journal",
    "proceedings-article": "paper-conference",
    "posted-content": "article",
    "book-chapter": "chapter",
    "book": "book",
    "monograph": "book",
    "dataset": "dataset",
    "report": "report",
    "dissertation": "thesis",
}


def crossref_fields(message: dict[str, Any]) -> dict[str, Any]:
    """The CSL fields we keep from one Crossref work record."""

    def first(key: str) -> str | None:
        v = message.get(key)
        if isinstance(v, list):
            return v[0] if v else None
        return v

    out: dict[str, Any] = {
        "type": _TYPES.get(message.get("type", ""), "article-journal")
    }
    if first("title"):
        out["title"] = re.sub(r"<[^>]+>", "", first("title"))  # JATS tags in titles
    if first("container-title"):
        out["container-title"] = first("container-title")
    if first("short-container-title"):
        out["container-title-short"] = first("short-container-title")
    for key in ("volume", "issue", "page", "publisher"):
        if message.get(key):
            out[key] = str(message[key])
    if message.get("article-number") and "page" not in out:
        out["page"] = str(message["article-number"])
    authors = []
    for a in message.get("author") or []:
        if a.get("family"):
            authors.append({"family": a["family"], "given": a.get("given", "")})
        elif a.get("name"):
            authors.append({"literal": a["name"]})
    if authors:
        out["author"] = authors
    for key in ("published-print", "published-online", "published", "issued"):
        parts = (message.get(key) or {}).get("date-parts")
        if parts and parts[0] and parts[0][0]:
            out["issued"] = {"date-parts": [parts[0][:3]]}
            break
    return out


async def _lookup(client: httpx.AsyncClient, doi: str) -> dict[str, Any] | None:
    try:
        r = await client.get(CROSSREF + quote(doi, safe="/"))
    except httpx.HTTPError as exc:
        logger.info("crossref lookup failed for %s: %s", doi, exc)
        return None
    if r.status_code != 200:
        return None
    try:
        return crossref_fields(r.json()["message"])
    except (KeyError, ValueError, TypeError):
        return None


async def enrich(pool, papers: dict[str, dict[str, Any]], keys: list[str]) -> None:
    """Fill ``metadata.crossref`` for cited papers that have a DOI (in place and in the DB)."""
    todo = []
    for k in keys:
        p = papers.get(k)
        if not p:
            continue
        meta = p.get("metadata") or {}
        doi = (meta.get("doi") or "").strip()
        if doi and "crossref" not in meta:
            todo.append((p, re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)))
    if not todo:
        return
    sem = asyncio.Semaphore(6)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(10.0),
        headers={"user-agent": USER_AGENT},
        follow_redirects=True,
    ) as client:

        async def one(p: dict[str, Any], doi: str) -> None:
            async with sem:
                fields = await _lookup(client, doi)
            record = {"fetched_at": datetime.now(UTC).isoformat(), "fields": fields}
            p["metadata"] = {**(p.get("metadata") or {}), "crossref": record}
            try:
                await pool.execute(
                    "UPDATE plato.knowledge_assets SET metadata = metadata || $2::jsonb WHERE id = $1",
                    p["id"],
                    {"crossref": record},
                )
            except Exception:  # caching is best effort
                logger.warning("could not cache crossref record", exc_info=True)

        await asyncio.gather(*(one(p, doi) for p, doi in todo))
