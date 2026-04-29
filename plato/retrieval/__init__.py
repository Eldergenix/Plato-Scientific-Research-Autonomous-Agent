"""
Phase 2 — retrieval foundation.

Each external literature source (arXiv, OpenAlex, ADS, Crossref, PubMed,
Semantic Scholar) implements the :class:`SourceAdapter` Protocol and
registers itself via :func:`register_adapter`. The retrieval orchestrator
(``plato/retrieval/orchestrator.py``) consumes a ``DomainProfile`` to
decide which adapters to fan out to and merges results.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..state.models import Source

__all__ = [
    "SourceAdapter",
    "register_adapter",
    "get_adapter",
    "list_adapters",
    "ADAPTER_REGISTRY",
    "Source",
]


@runtime_checkable
class SourceAdapter(Protocol):
    """Protocol every retrieval adapter must implement."""

    name: str
    """Stable identifier matching ``DomainProfile.retrieval_sources`` entries."""

    async def search(self, query: str, limit: int) -> list[Source]:
        """Return up to ``limit`` Source records matching ``query``. Must be async."""
        ...


ADAPTER_REGISTRY: dict[str, SourceAdapter] = {}


def register_adapter(adapter: SourceAdapter, *, overwrite: bool = False) -> None:
    """Register a SourceAdapter. Raises if name collides unless ``overwrite=True``."""
    if not overwrite and adapter.name in ADAPTER_REGISTRY:
        raise ValueError(
            f"Adapter {adapter.name!r} is already registered; pass overwrite=True to replace."
        )
    ADAPTER_REGISTRY[adapter.name] = adapter


def get_adapter(name: str) -> SourceAdapter:
    if name not in ADAPTER_REGISTRY:
        raise KeyError(
            f"Unknown adapter {name!r}. Registered: {sorted(ADAPTER_REGISTRY)}"
        )
    return ADAPTER_REGISTRY[name]


def list_adapters() -> list[str]:
    return sorted(ADAPTER_REGISTRY)
