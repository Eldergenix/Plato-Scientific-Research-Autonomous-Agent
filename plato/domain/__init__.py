"""
Domain profile registry.

A `DomainProfile` names the retrieval sources, keyword extractor, journal
presets, executor, and novelty corpus that a domain expects. Plato ships
with the `astro` profile registered by default; non-astro projects
(biology, ML, chemistry, ...) register additional profiles by importing a
side-module that calls `register_domain(...)`.

Phase 1 ships only this schema and the astro registration. Phase 2 wires
retrieval to consume `DomainProfile.retrieval_sources` via the
`SourceAdapter` registry; later phases plug in `KeywordExtractor`,
`JournalPreset`, and `Executor` registries the same way.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class DomainProfile(BaseModel):
    """Pluggable per-domain configuration consumed by retrieval, drafting, and execution layers."""

    name: str = Field(description="Stable identifier, e.g. 'astro', 'biology', 'ml'")
    retrieval_sources: list[str] = Field(
        default_factory=list,
        description="Adapter names registered in the SourceAdapter registry (Phase 2).",
    )
    keyword_extractor: str = Field(
        default="default",
        description="Name of the registered KeywordExtractor implementation.",
    )
    journal_presets: list[str] = Field(
        default_factory=list,
        description="Allowed Journal enum values for this domain.",
    )
    executor: str = Field(
        default="cmbagent",
        description="Code-execution backend identifier ('cmbagent', 'modal', 'e2b', ...).",
    )
    novelty_corpus: str = Field(
        default="",
        description="Reference corpus identifier used by the novelty scorer.",
    )


_DOMAIN_REGISTRY: dict[str, DomainProfile] = {}


def register_domain(profile: DomainProfile, *, overwrite: bool = False) -> None:
    """Register a domain profile. Raises if `profile.name` already exists unless `overwrite=True`."""
    if not overwrite and profile.name in _DOMAIN_REGISTRY:
        raise ValueError(
            f"Domain {profile.name!r} is already registered. "
            "Pass overwrite=True to replace it."
        )
    _DOMAIN_REGISTRY[profile.name] = profile


def get_domain(name: str) -> DomainProfile:
    """Look up a registered domain profile by name."""
    if name not in _DOMAIN_REGISTRY:
        raise KeyError(
            f"Unknown domain {name!r}. Registered: {sorted(_DOMAIN_REGISTRY)}"
        )
    return _DOMAIN_REGISTRY[name]


def list_domains() -> list[str]:
    """Return the sorted list of registered domain names."""
    return sorted(_DOMAIN_REGISTRY)


# --- Built-in profiles -----------------------------------------------------

register_domain(
    DomainProfile(
        name="astro",
        retrieval_sources=["semantic_scholar", "arxiv", "openalex", "ads"],
        keyword_extractor="cmbagent",
        journal_presets=["NONE", "AAS", "APS", "JHEP", "PASJ", "ICML", "NeurIPS"],
        executor="cmbagent",
        novelty_corpus="arxiv:astro-ph",
    )
)


register_domain(
    DomainProfile(
        name="biology",
        retrieval_sources=["pubmed", "openalex", "semantic_scholar"],
        keyword_extractor="mesh",
        journal_presets=["NATURE", "CELL", "SCIENCE", "PLOS_BIO", "ELIFE", "NONE"],
        executor="cmbagent",  # placeholder until biology-specific executor lands
        novelty_corpus="pubmed",
    )
)


__all__ = [
    "DomainProfile",
    "register_domain",
    "get_domain",
    "list_domains",
]
