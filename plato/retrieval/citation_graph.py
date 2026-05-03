"""Phase 5 / Workflow #7 — N-hop citation-graph expansion via OpenAlex.

Given a list of seed :class:`Source` records, walk OpenAlex's citation
graph in either direction:

- ``referenced_works`` — papers each seed *cites* (its bibliography).
- ``cited_by`` — papers that cite each seed.

``depth`` controls how many hops to walk. ``depth=1`` (the default) is the
direct-neighbour case — referenced/cited works of the seed papers
themselves. ``depth>=2`` triggers a frontier-based BFS: at each level we
take the *new* sources discovered in the previous level, expand them, and
add anything we haven't already visited. The walk stops when either:

  - the configured ``depth`` is exhausted, OR
  - the configured ``total_limit`` is reached, OR
  - the next frontier is empty (no new sources to expand).

Concurrent HTTP fetches at each depth level are bounded by an
``asyncio.Semaphore`` so the OpenAlex rate-limit is respected even on
high-fanout seeds. Sources without an ``openalex_id`` are skipped — DOI
→ OpenAlex resolution is exposed as the separate :func:`expand_via_doi`
convenience.

All emitted Sources carry ``retrieved_via="openalex"`` and are deduped
against the seeds and against each previously-emitted source (via the
visited-set + :func:`plato.retrieval.dedup.dedup_sources`), so a
self-referential loop is filtered out.
"""
from __future__ import annotations

import asyncio
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


_DEFAULT_BFS_CONCURRENCY = 8
"""Max concurrent OpenAlex calls per depth level. Conservative — OpenAlex
recommends polite-pool requests stay below 10/s with no API key."""


async def _fetch_one(
    client: httpx.AsyncClient,
    openalex_id: str,
    direction: ExpansionDirection,
    limit_per_seed: int,
    semaphore: asyncio.Semaphore,
) -> list[Source]:
    """Bounded-concurrency wrapper around the per-direction fetchers.

    Errors from a single seed are swallowed so one rate-limited call
    can't poison the rest of the frontier — the absent results just don't
    appear in the emitted set.
    """
    async with semaphore:
        try:
            if direction == "referenced_works":
                return await _fetch_referenced_works(
                    client, openalex_id, limit_per_seed
                )
            elif direction == "cited_by":
                return await _fetch_cited_by(client, openalex_id, limit_per_seed)
            else:  # pragma: no cover — guarded by the Literal type
                raise ValueError(f"Unknown expansion direction: {direction!r}")
        except httpx.HTTPError:
            return []


async def expand_citations(
    seeds: list[Source],
    *,
    direction: ExpansionDirection = "referenced_works",
    depth: int = 1,
    limit_per_seed: int = 25,
    total_limit: int | None = None,
    concurrency: int = _DEFAULT_BFS_CONCURRENCY,
    http_client: httpx.AsyncClient | None = None,
) -> list[Source]:
    """Walk OpenAlex's citation graph from each seed Source.

    For ``depth=1`` (the default), fetch up to ``limit_per_seed`` works in
    the chosen direction (``referenced_works`` or ``cited_by``) for each
    seed and return the deduped union with seeds removed.

    For ``depth>=2``, run a frontier-based BFS: at each level expand only
    the *new* sources discovered in the previous level (so a paper found
    at depth-1 is expanded once when it surfaces, not again at depth-2),
    bounded by ``concurrency`` concurrent OpenAlex calls per level. The
    walk stops as soon as ``total_limit`` is reached or the next frontier
    is empty.

    Sources without an ``openalex_id`` are skipped (we'd need a DOI →
    OpenAlex resolution, which is its own retrieval round). Returns the
    deduped union of all emitted Sources, with seed papers and
    intra-frontier duplicates excluded so a reference-pointing-back-to-
    itself loop is filtered out.

    Parameters
    ----------
    seeds:
        Sources to expand from. Seeds lacking ``openalex_id`` are skipped.
    direction:
        ``"referenced_works"`` (papers each seed cites) or ``"cited_by"``
        (papers that cite each seed).
    depth:
        Number of BFS hops. Must be ``>= 1``. ``depth=0`` returns an empty
        list (no expansion); ``depth=1`` returns direct neighbours;
        ``depth>=2`` triggers the frontier walk.
    limit_per_seed:
        Cap on works fetched per seed at every depth level.
    total_limit:
        Optional cap on the total number of emitted Sources across all
        depths. The walk short-circuits as soon as the cap is reached.
    concurrency:
        Max concurrent OpenAlex calls per depth level. Defaults to 8 to
        stay polite with the OpenAlex anonymous rate limit.
    http_client:
        Optional reusable :class:`httpx.AsyncClient`. If ``None`` we
        create — and cleanly close — our own.
    """
    if depth < 1:
        return []
    if not seeds:
        return []

    seed_keys = {s.openalex_id for s in seeds if s.openalex_id}
    seeds_to_expand = [s for s in seeds if s.openalex_id]
    if not seeds_to_expand:
        return []

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
    semaphore = asyncio.Semaphore(max(1, int(concurrency)))

    try:
        emitted: list[Source] = []
        # ``visited`` covers seeds + every source we've already emitted at
        # any depth level, so we never re-fetch the same OpenAlex work.
        visited: set[str] = set(seed_keys)
        frontier: list[Source] = list(seeds_to_expand)

        for current_depth in range(depth):
            if not frontier:
                break

            # Fan out the frontier into a single asyncio.gather so the
            # ``concurrency`` semaphore actually rate-limits across the
            # whole level rather than one seed at a time.
            tasks = [
                _fetch_one(
                    client,
                    seed.openalex_id,  # type: ignore[arg-type]
                    direction,
                    limit_per_seed,
                    semaphore,
                )
                for seed in frontier
                if seed.openalex_id
            ]
            results = await asyncio.gather(*tasks)

            next_frontier: list[Source] = []
            for fetched in results:
                for src in fetched:
                    key = src.openalex_id
                    if not key or key in visited:
                        continue
                    visited.add(key)
                    emitted.append(src)
                    next_frontier.append(src)
                    if total_limit is not None and len(emitted) >= total_limit:
                        # Truncate emitted in case the inner loop ran past
                        # the cap on the same fetched batch.
                        emitted = emitted[:total_limit]
                        return dedup_sources(emitted)

            frontier = next_frontier
    finally:
        if owns_client:
            await client.aclose()

    return dedup_sources(emitted)


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
