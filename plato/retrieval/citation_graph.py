"""Phase 5 / Workflow #7 — 1-hop citation-graph expansion via OpenAlex.

Given a list of seed :class:`Source` records, walk OpenAlex's citation
graph one hop in either direction:

- ``referenced_works`` — papers each seed *cites* (its bibliography).
- ``cited_by`` — papers that cite each seed.

Only ``depth=1`` is currently supported. ``depth>1`` raises
``NotImplementedError``: BFS at depth ≥ 2 is its own scaffold (rate
limiting, frontier dedup, stop conditions) and is deferred to a follow-up
workflow rather than half-built here.

Seeds without an ``openalex_id`` are skipped — DOI → OpenAlex resolution
is exposed as the separate :func:`expand_via_doi` convenience.

All emitted Sources carry ``retrieved_via="openalex"`` and are deduped
against the seeds (via :func:`plato.retrieval.dedup.dedup_sources`) before
being returned, so a self-referential loop is filtered out.
"""
from __future__ import annotations

from typing import Literal
from urllib.parse import quote_plus

import httpx

from .dedup import dedup_sources
from .sources.openalex import _map_work_to_source
from ..state.models import Source

__all__ = [
    "ExpansionDirection",
    "expand_citations",
    "expand_via_doi",
]


ExpansionDirection = Literal["referenced_works", "cited_by"]

_OPENALEX_WORKS_URL = "https://api.openalex.org/works"
_OPENALEX_WORK_PREFIX = "https://openalex.org/"
_DEFAULT_TIMEOUT = 30.0
# OpenAlex caps `per-page` at 200; we stay well under to keep payloads small.
_MAX_PER_PAGE = 200


def _strip_openalex_prefix(work_id: str) -> str:
    if work_id.startswith(_OPENALEX_WORK_PREFIX):
        return work_id[len(_OPENALEX_WORK_PREFIX) :]
    return work_id


async def _fetch_referenced_works(
    client: httpx.AsyncClient, openalex_id: str, limit: int
) -> list[Source]:
    """Fetch the works ``openalex_id`` references (its bibliography).

    Two API calls: one to read the seed's ``referenced_works`` list,
    another to batch-resolve those IDs into full work records.
    """
    seed_url = f"{_OPENALEX_WORKS_URL}/{openalex_id}"
    seed_resp = await client.get(seed_url)
    seed_resp.raise_for_status()
    seed_payload = seed_resp.json()

    raw_refs = seed_payload.get("referenced_works") or []
    ref_ids = [_strip_openalex_prefix(r) for r in raw_refs if isinstance(r, str)]
    if not ref_ids:
        return []

    capped_ids = ref_ids[:limit]
    per_page = max(1, min(len(capped_ids), _MAX_PER_PAGE))
    filter_value = "|".join(capped_ids)
    batch_url = (
        f"{_OPENALEX_WORKS_URL}?filter=openalex:{quote_plus(filter_value)}"
        f"&per-page={per_page}"
    )

    batch_resp = await client.get(batch_url)
    batch_resp.raise_for_status()
    batch_payload = batch_resp.json()

    works = batch_payload.get("results") or []
    sources: list[Source] = []
    for work in works:
        mapped = _map_work_to_source(work)
        if mapped is not None:
            sources.append(mapped)
    return sources


async def _fetch_cited_by(
    client: httpx.AsyncClient, openalex_id: str, limit: int
) -> list[Source]:
    """Fetch works that cite ``openalex_id``."""
    per_page = max(1, min(limit, _MAX_PER_PAGE))
    url = (
        f"{_OPENALEX_WORKS_URL}?filter=cites:{openalex_id}&per-page={per_page}"
    )
    resp = await client.get(url)
    resp.raise_for_status()
    payload = resp.json()

    works = payload.get("results") or []
    sources: list[Source] = []
    for work in works[:limit]:
        mapped = _map_work_to_source(work)
        if mapped is not None:
            sources.append(mapped)
    return sources


async def expand_citations(
    seeds: list[Source],
    *,
    direction: ExpansionDirection = "referenced_works",
    depth: int = 1,
    limit_per_seed: int = 25,
    http_client: httpx.AsyncClient | None = None,
) -> list[Source]:
    """Walk OpenAlex's citation graph from each seed Source.

    For each seed with an ``openalex_id``, fetch up to ``limit_per_seed``
    works in the chosen direction (``referenced_works`` or ``cited_by``)
    and emit them as Sources. ``depth=1`` is the only currently-supported
    value; higher depths require a BFS scaffold that's deferred.

    Sources without an ``openalex_id`` are skipped (we'd need a DOI →
    OpenAlex resolution, which is its own retrieval round). Returns the
    deduped union of all emitted Sources, with seed papers excluded so a
    reference-pointing-back-to-itself loop is filtered out.

    Parameters
    ----------
    seeds:
        Sources to expand from. Seeds lacking ``openalex_id`` are skipped.
    direction:
        ``"referenced_works"`` (papers each seed cites) or ``"cited_by"``
        (papers that cite each seed).
    depth:
        Currently must be 1. Higher depths raise ``NotImplementedError``.
    limit_per_seed:
        Cap on works fetched per seed.
    http_client:
        Optional reusable :class:`httpx.AsyncClient`. If ``None`` we
        create — and cleanly close — our own.
    """
    if depth != 1:
        raise NotImplementedError(
            "expand_citations only supports depth=1; deeper BFS is deferred."
        )
    if not seeds:
        return []

    seed_keys = {s.openalex_id for s in seeds if s.openalex_id}
    seeds_to_expand = [s for s in seeds if s.openalex_id]
    if not seeds_to_expand:
        return []

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    try:
        emitted: list[Source] = []
        for seed in seeds_to_expand:
            assert seed.openalex_id is not None  # narrowed by the filter above
            if direction == "referenced_works":
                fetched = await _fetch_referenced_works(
                    client, seed.openalex_id, limit_per_seed
                )
            elif direction == "cited_by":
                fetched = await _fetch_cited_by(
                    client, seed.openalex_id, limit_per_seed
                )
            else:  # pragma: no cover — guarded by the Literal type
                raise ValueError(f"Unknown expansion direction: {direction!r}")
            emitted.extend(fetched)
    finally:
        if owns_client:
            await client.aclose()

    # Drop anything that points back at a seed (the self-loop case) before
    # the final dedup pass so the seed itself never re-surfaces in the
    # expansion result set.
    filtered = [s for s in emitted if s.openalex_id not in seed_keys]
    return dedup_sources(filtered)


async def expand_via_doi(
    seed_dois: list[str],
    *,
    direction: ExpansionDirection = "referenced_works",
    depth: int = 1,
    limit_per_seed: int = 25,
    http_client: httpx.AsyncClient | None = None,
) -> list[Source]:
    """Resolve DOIs to OpenAlex works, then expand their citation graph.

    Each DOI is looked up via ``GET /works/doi:{doi}``; resolved works
    become the seeds for :func:`expand_citations`. DOIs that fail to
    resolve are silently skipped — one bad DOI shouldn't poison the rest
    of the batch.
    """
    if not seed_dois:
        return []

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    seeds: list[Source] = []
    try:
        for doi in seed_dois:
            url = f"{_OPENALEX_WORKS_URL}/doi:{quote_plus(doi)}"
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except httpx.HTTPError:
                continue
            mapped = _map_work_to_source(resp.json())
            if mapped is not None:
                seeds.append(mapped)

        if not seeds:
            return []

        return await expand_citations(
            seeds,
            direction=direction,
            depth=depth,
            limit_per_seed=limit_per_seed,
            http_client=client,
        )
    finally:
        if owns_client:
            await client.aclose()
