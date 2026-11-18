"""
Phase 2 (R4) — retrieval orchestrator.

Given a free-text query, fan it out to a configurable set of
:class:`SourceAdapter` implementations in parallel, dedupe the union of
their results via :func:`plato.retrieval.dedup.dedup_sources`, and return
at most ``limit`` Sources.

Adapter selection priority:

1. Explicit ``adapter_names`` argument wins.
2. Otherwise the supplied ``DomainProfile.retrieval_sources`` list is used.
3. Otherwise we fall back to *all* registered adapters.

Adapters that aren't registered or that raise during ``search`` are logged
and skipped — one flaky source never takes the whole orchestration down.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Literal

from . import ADAPTER_REGISTRY, SourceAdapter, get_adapter
from .citation_graph import ExpansionDirection, expand_citations
from .dedup import _dedup_key, dedup_sources, title_key
from .reranker import rerank
from ..state.models import Source

if TYPE_CHECKING:
    from ..domain import DomainProfile

logger = logging.getLogger(__name__)

__all__ = ["is_supplementary", "retrieve", "retrieve_with_expansion"]

# Repository records for a paper's supplementary files ("Additional file 5: of ...",
# "Supplemental material for: ...", "Figure S2 from ..."): DOIs, but not literature.
_SUPPLEMENTARY = re.compile(
    r"^\s*(additional\s+file\b|supplementa(l|ry)\s+(material|information|file|data|table|figure|text|method)s?\b|(figure|fig\.?|table|data|movie|video)\s+s?\d+\b"
    r"[^a-z]*(from|of)\b)",
    re.IGNORECASE,
)


def is_supplementary(source: Source) -> bool:
    return bool(_SUPPLEMENTARY.match(source.title))


def _resolve_adapter_names(
    *,
    adapter_names: list[str] | None,
    profile: "DomainProfile | None",
) -> list[str]:
    """Pick the adapter-name list the caller actually wants us to use."""
    if adapter_names is not None:
        return list(adapter_names)
    if profile is not None and profile.retrieval_sources:
        return list(profile.retrieval_sources)
    return sorted(ADAPTER_REGISTRY)


def _resolve_adapters(names: list[str]) -> list[SourceAdapter]:
    """Look up each name in the registry, logging and skipping unknowns."""
    adapters: list[SourceAdapter] = []
    for name in names:
        try:
            adapters.append(get_adapter(name))
        except KeyError:
            logger.warning(
                "Skipping unknown retrieval adapter %r (not registered).", name
            )
    return adapters


async def retrieve(
    query: str,
    limit: int,
    *,
    profile: "DomainProfile | None" = None,
    adapter_names: list[str] | None = None,
    rerank_fallback: Literal["passthrough", "bm25", "fused"] = "passthrough",
    adapter_timeout: float | None = None,
    drop_supplementary: bool = False,
) -> list[Source]:
    """Search every selected adapter for ``query`` and return up to ``limit`` deduped Sources.

    Parameters
    ----------
    query:
        Free-text query passed unchanged to every adapter.
    limit:
        Maximum number of Sources to return. We over-fetch (``limit * 2``)
        from each adapter to leave headroom for the dedup pass.
    profile:
        Optional :class:`DomainProfile`. Its ``retrieval_sources`` is used
        when ``adapter_names`` is not provided.
    adapter_names:
        Optional explicit list of adapter names. Overrides ``profile``.
    rerank_fallback:
        Ranking used when no Cohere/CrossEncoder backend is installed: ``"bm25"``
        ranks lexically, ``"passthrough"`` keeps first-seen order.
    drop_supplementary:
        Drop records of supplementary files (see :func:`is_supplementary`).
    adapter_timeout:
        Seconds each adapter may take (retries included) before it is skipped, so one
        slow or rate-limited source cannot hold up the others. ``None``: no limit.
    """
    if limit <= 0:
        return []

    names = _resolve_adapter_names(adapter_names=adapter_names, profile=profile)
    adapters = _resolve_adapters(names)
    if not adapters:
        logger.warning("retrieve(): no usable adapters; returning [].")
        return []

    # Over-fetch so dedup has more candidates to fold together.
    per_adapter_limit = max(limit * 2, limit)

    def _search(adapter: SourceAdapter):
        call = adapter.search(query, per_adapter_limit)
        return (
            call if adapter_timeout is None else asyncio.wait_for(call, adapter_timeout)
        )

    results = await asyncio.gather(
        *(_search(adapter) for adapter in adapters),
        return_exceptions=True,
    )

    flat: list[Source] = []
    # Reciprocal-rank credit per work from every adapter that returned it.
    prior: dict[str, float] = {}
    for adapter, result in zip(adapters, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning(
                "Adapter %r raised during retrieval: %s: %s",
                adapter.name,
                type(result).__name__,
                result,
            )
            continue
        kept = [s for s in result if not (drop_supplementary and is_supplementary(s))]
        for rank, src in enumerate(kept, start=1):
            for key in {_dedup_key(src), title_key(src)} - {None}:
                prior[key] = prior.get(key, 0.0) + 1 / (60 + rank)
        flat.extend(kept)

    deduped = dedup_sources(flat)
    if rerank_fallback == "fused":
        source_prior = [
            max(prior.get(k, 0.0) for k in {_dedup_key(s), title_key(s)} - {None})
            for s in deduped
        ]
        return rerank(
            query, deduped, top_k=limit, fallback="fused", source_prior=source_prior
        )
    # R4 — relevance-rerank deduplicated candidates. Backends are
    # opt-in (``plato[rerank]``); without them the call falls through
    # to a first-seen-wins slice with a one-time warning.
    return rerank(query, deduped, top_k=limit, fallback=rerank_fallback)


async def retrieve_with_expansion(
    query: str,
    *,
    limit: int = 20,
    profile: "DomainProfile | None" = None,
    adapter_names: list[str] | None = None,
    expand: bool = False,
    expansion_direction: ExpansionDirection = "referenced_works",
    expansion_limit_per_seed: int = 25,
) -> list[Source]:
    """Run :func:`retrieve` and optionally fold in a 1-hop citation-graph expansion.

    With ``expand=False`` (the default) this is a thin wrapper around
    :func:`retrieve`. With ``expand=True``, each seed Source carrying an
    ``openalex_id`` is walked one hop in the requested direction
    (``referenced_works`` or ``cited_by``) via
    :func:`plato.retrieval.citation_graph.expand_citations`, and the
    deduped union of seeds plus expansion is returned.
    """
    seeds = await retrieve(query, limit, profile=profile, adapter_names=adapter_names)
    if not expand or not seeds:
        return seeds

    expanded = await expand_citations(
        seeds,
        direction=expansion_direction,
        limit_per_seed=expansion_limit_per_seed,
    )
    return dedup_sources(seeds + expanded)
