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
from .dedup import dedup_sources
from ..state.models import Source

if TYPE_CHECKING:
    from ..domain import DomainProfile

logger = logging.getLogger(__name__)

__all__ = ["retrieve"]


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

    return dedup_sources(flat)[:limit]
