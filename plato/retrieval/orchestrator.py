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
from typing import TYPE_CHECKING

from . import ADAPTER_REGISTRY, SourceAdapter, get_adapter
from .citation_graph import ExpansionDirection, expand_citations
from .dedup import dedup_sources
from .reranker import rerank
from ..state.models import Source

if TYPE_CHECKING:
    from ..domain import DomainProfile

logger = logging.getLogger(__name__)

__all__ = ["retrieve", "retrieve_with_expansion"]


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

    results = await asyncio.gather(
        *(adapter.search(query, per_adapter_limit) for adapter in adapters),
        return_exceptions=True,
    )

    flat: list[Source] = []
    for adapter, result in zip(adapters, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning(
                "Adapter %r raised during retrieval: %s",
                adapter.name,
                result,
            )
            continue
        flat.extend(result)

    deduped = dedup_sources(flat)
    # R4 — relevance-rerank deduplicated candidates. Backends are
    # opt-in (``plato[rerank]``); without them the call falls through
    # to a first-seen-wins slice with a one-time warning.
    return rerank(query, deduped, top_k=limit)


async def retrieve_with_expansion(
    query: str,
    *,
    limit: int = 20,
    profile: "DomainProfile | None" = None,
    adapter_names: list[str] | None = None,
    expand: bool = False,
    expansion_direction: ExpansionDirection = "referenced_works",
    expansion_limit_per_seed: int = 25,
    run_dir: "Path | str | None" = None,
) -> list[Source]:
    """Run :func:`retrieve` and optionally fold in a 1-hop citation-graph expansion.

    With ``expand=False`` (the default) this is a thin wrapper around
    :func:`retrieve`. With ``expand=True``, each seed Source carrying an
    ``openalex_id`` is walked one hop in the requested direction
    (``referenced_works`` or ``cited_by``) via
    :func:`plato.retrieval.citation_graph.expand_citations`, and the
    deduped union of seeds plus expansion is returned.

    Iter-5: when ``run_dir`` is supplied, persist a ``citation_graph.json``
    payload alongside the run's other artefacts so the dashboard's
    citation-graph view has a real source to read. Without this write,
    the dashboard endpoint falls back to the manifest-extras path which
    most workflows never populate.
    """
    seeds = await retrieve(
        query, limit, profile=profile, adapter_names=adapter_names
    )
    if not expand or not seeds:
        return seeds

    expanded = await expand_citations(
        seeds,
        direction=expansion_direction,
        limit_per_seed=expansion_limit_per_seed,
    )
    merged = dedup_sources(seeds + expanded)

    if run_dir is not None:
        try:
            _persist_citation_graph(
                run_dir,
                seeds=seeds,
                expanded=expanded,
                merged=merged,
            )
        except Exception:  # noqa: BLE001
            # Persistence is best-effort — a write failure must never
            # break the retrieval flow. The dashboard falls back to
            # manifest extras when the file is absent.
            import logging
            logging.getLogger(__name__).exception(
                "citation_graph.json persistence failed; continuing"
            )

    return merged


def _persist_citation_graph(
    run_dir: "Path | str",
    *,
    seeds: list[Source],
    expanded: list[Source],
    merged: list[Source],
) -> None:
    """Write ``<run_dir>/citation_graph.json`` in the dashboard view shape.

    The shape mirrors what
    ``dashboard.../citation_graph_view._read_graph_payload`` returns —
    keep the two in sync. ``edges`` are derived best-effort: every
    expanded node points back at the first seed that carries an
    ``openalex_id`` (the ``expand_citations`` walker doesn't currently
    return per-edge provenance, so we encode the seed→expanded
    relationship without finer attribution).
    """
    import json
    from pathlib import Path as _Path

    target = _Path(run_dir) / "citation_graph.json"
    target.parent.mkdir(parents=True, exist_ok=True)

    def _node(s: Source) -> dict:
        return {
            "id": getattr(s, "openalex_id", None) or getattr(s, "doi", None) or s.title,
            "title": s.title,
            "doi": getattr(s, "doi", None),
            "openalex_id": getattr(s, "openalex_id", None),
            "year": getattr(s, "year", None),
            "authors": list(getattr(s, "authors", []) or []),
        }

    seed_nodes = [_node(s) for s in seeds]
    expanded_nodes = [_node(s) for s in expanded]
    seed_ids = [n["id"] for n in seed_nodes if n["id"]]
    primary_seed = seed_ids[0] if seed_ids else None
    edges = (
        [
            {"source": primary_seed, "target": n["id"]}
            for n in expanded_nodes
            if n["id"]
        ]
        if primary_seed
        else []
    )

    payload = {
        "seeds": seed_nodes,
        "expanded": expanded_nodes,
        "edges": edges,
        "stats": {
            "seed_count": len(seed_nodes),
            "expanded_count": len(expanded_nodes),
            "edge_count": len(edges),
            "duplicates_filtered": max(
                0, len(seeds) + len(expanded) - len(merged)
            ),
        },
    }

    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    import os
    os.replace(tmp, target)
