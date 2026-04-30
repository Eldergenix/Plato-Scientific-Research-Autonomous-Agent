"""Counter-evidence search node (Workflow gap #11).

After ``literature_summary`` runs, this node deliberately searches for
papers that *contradict* the seed query — null results, failed
replications, limitations, retractions. The output augments the literature
panel with evidence the maker/hater debate would otherwise never see.

Implementation
--------------
- Read the seed query from ``state['literature']['query']`` (falling back
  to ``state['idea']['idea']`` if the literature track was skipped).
- Build ~3 query variants by appending steering phrases like ``"fail to
  replicate"`` or ``"null result"``.
- Run each variant through :func:`plato.retrieval.orchestrator.retrieve`
  in parallel against the active :class:`DomainProfile`.
- Dedup against the already-retrieved sources (``state['literature']
  ['sources']`` or ``state['sources']``) using DOI / arXiv / OpenAlex /
  title — same identifiers as the orchestrator's dedup pass.

The retrieve calls are awaited via ``asyncio.gather`` so the slowest
adapter, not the slowest variant, sets the wall-clock cost.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterable, Optional

from langchain_core.runnables import RunnableConfig

from .parameters import GraphState
from ..domain import DomainProfile, get_domain
from ..retrieval.orchestrator import retrieve
from ..state.models import Source

logger = logging.getLogger(__name__)


# Steering phrases appended to the seed query to bias retrieval toward
# disconfirming evidence. Order is significant — the first three are the
# canonical workflow-#11 targets, the rest stay around as ammunition for
# future tuning without breaking tests.
_VARIANT_PHRASES = (
    "fail to replicate",
    "null result",
    "limitations",
    "do not support",
    "contradicts",
)

# How many variants to dispatch per call. Three is the contract from the
# Stream F spec; bumping this would require widening the regression tests.
_NUM_VARIANTS = 3

# Per-variant retrieval limit. We over-fetch a little so the dedup pass
# against the already-retrieved corpus has headroom.
_PER_VARIANT_LIMIT = 10


def _resolve_profile(state: GraphState) -> DomainProfile:
    """Mirror of ``literature._resolve_profile`` — kept private to avoid a
    cross-module import that the test suite would have to mock."""
    profile = state.get("domain_profile")  # type: ignore[arg-type]
    if isinstance(profile, DomainProfile):
        return profile

    name = state.get("domain")  # type: ignore[arg-type]
    if isinstance(name, str) and name:
        try:
            return get_domain(name)
        except KeyError:
            logger.warning(
                "Unknown domain %r in state; falling back to 'astro'.", name
            )

    return get_domain("astro")


def _seed_query(state: GraphState) -> str | None:
    literature = state.get("literature") if isinstance(state, dict) else None
    if isinstance(literature, dict):
        q = literature.get("query")
        if isinstance(q, str) and q.strip():
            return q.strip()
    idea = state.get("idea") if isinstance(state, dict) else None
    if isinstance(idea, dict):
        text = idea.get("idea")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


def _existing_sources(state: GraphState) -> list[Source]:
    """Pull the already-retrieved sources from either of the two state slots."""
    out: list[Source] = []
    literature = state.get("literature") if isinstance(state, dict) else None
    if isinstance(literature, dict):
        for s in literature.get("sources") or []:
            if isinstance(s, Source):
                out.append(s)
    for s in state.get("sources") or []:  # type: ignore[arg-type]
        if isinstance(s, Source):
            out.append(s)
    return out


def _dedup_keys(sources: Iterable[Source]) -> set[str]:
    """Same key priority as ``plato.retrieval.dedup`` — DOI > arxiv > openalex > title."""
    keys: set[str] = set()
    for s in sources:
        keys.add(s.doi or s.arxiv_id or s.openalex_id or s.title.lower())
    return keys


def _build_variants(seed: str) -> list[str]:
    """Append the first ``_NUM_VARIANTS`` steering phrases to ``seed``."""
    return [f"{seed} {phrase}" for phrase in _VARIANT_PHRASES[:_NUM_VARIANTS]]


async def counter_evidence_search(
    state: GraphState, config: Optional[RunnableConfig] = None
):
    """LangGraph node: retrieve counter-evidence sources for the literature query."""

    seed = _seed_query(state)
    if not seed:
        return {"counter_evidence_sources": []}

    profile = _resolve_profile(state)
    variants = _build_variants(seed)

    fetched_lists = await asyncio.gather(
        *(
            retrieve(variant, limit=_PER_VARIANT_LIMIT, profile=profile)
            for variant in variants
        ),
        return_exceptions=True,
    )

    seen_keys = _dedup_keys(_existing_sources(state))
    fresh: list[Source] = []
    for variant, result in zip(variants, fetched_lists, strict=True):
        if isinstance(result, BaseException):
            logger.warning(
                "Counter-evidence variant %r raised: %s", variant, result
            )
            continue
        for src in result:
            if not isinstance(src, Source):
                continue
            key = src.doi or src.arxiv_id or src.openalex_id or src.title.lower()
            if key in seen_keys:
                continue
            seen_keys.add(key)
            fresh.append(src)

    return {"counter_evidence_sources": fresh}


__all__ = ["counter_evidence_search"]
