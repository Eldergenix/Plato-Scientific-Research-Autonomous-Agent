"""
§5.4 built-in tool registrations.

Wraps existing Phase 2 components (CitationValidator, retrieval orchestrator)
in the typed :class:`~plato.tools.registry.Tool` interface so agent nodes
can discover them through ``plato.tools.list_tools()`` and invoke them with
permission gates.

Both tools are registered at import time with ``overwrite=True`` so that
re-importing this module (e.g. across test sessions or after a fork) is
idempotent.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..domain import get_domain
from ..retrieval.orchestrator import retrieve as _retrieve_sources
from ..state.models import Source, ValidationResult
from .citation_validator import CitationValidator
from .registry import Tool, ToolMetadata, register


# --- verify_citation -------------------------------------------------------


class VerifyCitationInput(BaseModel):
    """Input schema for ``verify_citation`` — one Source to validate."""

    source: Source


VerifyCitationOutput = ValidationResult


async def _verify_citation(payload: VerifyCitationInput) -> ValidationResult:
    """Spin up a short-lived ``CitationValidator`` and validate a single source.

    A fresh ``httpx.AsyncClient`` per call is wasteful for batch workloads;
    that's what ``CitationValidator.validate_batch`` is for. This tool wrapper
    targets one-off lookups where simplicity beats reuse.
    """
    async with CitationValidator() as validator:
        return await validator.validate(payload.source)


_VERIFY_CITATION_TOOL = Tool(
    metadata=ToolMetadata(
        name="verify_citation",
        description=(
            "Validate a Source citation against Crossref, arXiv, and live URLs. "
            "Returns a ValidationResult with doi_resolved / arxiv_resolved / "
            "url_alive / retracted booleans."
        ),
        permissions={"network"},
        category="validation",
    ),
    input_schema=VerifyCitationInput,
    output_schema=VerifyCitationOutput,
    fn=_verify_citation,
)


# --- search_literature -----------------------------------------------------


class SearchLiteratureInput(BaseModel):
    """Input schema for ``search_literature``."""

    query: str
    limit: int = Field(default=20, ge=1)
    profile_name: str | None = Field(
        default=None,
        description=(
            "Optional name of a registered DomainProfile. If set, the tool "
            "looks up the profile and uses its retrieval_sources."
        ),
    )


class SearchLiteratureOutput(BaseModel):
    """Output schema for ``search_literature``."""

    sources: list[Source]


async def _search_literature(payload: SearchLiteratureInput) -> SearchLiteratureOutput:
    """Resolve the optional ``profile_name`` and delegate to the retrieval orchestrator."""
    profile = get_domain(payload.profile_name) if payload.profile_name else None
    sources = await _retrieve_sources(
        payload.query,
        limit=payload.limit,
        profile=profile,
    )
    return SearchLiteratureOutput(sources=sources)


_SEARCH_LITERATURE_TOOL = Tool(
    metadata=ToolMetadata(
        name="search_literature",
        description=(
            "Fan a query out to every registered SourceAdapter (filtered by an "
            "optional DomainProfile) and return up to `limit` deduped Sources."
        ),
        permissions={"network"},
        category="retrieval",
    ),
    input_schema=SearchLiteratureInput,
    output_schema=SearchLiteratureOutput,
    fn=_search_literature,
)


# Register at import time. ``overwrite=True`` keeps re-imports idempotent
# (pytest collection, dev-loop reloads, etc.).
register(_VERIFY_CITATION_TOOL, overwrite=True)
register(_SEARCH_LITERATURE_TOOL, overwrite=True)


__all__ = [
    "VerifyCitationInput",
    "VerifyCitationOutput",
    "SearchLiteratureInput",
    "SearchLiteratureOutput",
]
