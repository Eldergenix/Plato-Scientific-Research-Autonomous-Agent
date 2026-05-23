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

from typing import cast

from pydantic import BaseModel, Field

from ..domain import get_domain
from ..retrieval.orchestrator import retrieve as _retrieve_sources
from ..state.models import Source, ValidationResult
from .citation_validator import CitationValidator
from .genomics import (
    ExpansionHunterDenovoInput,
    GauchianCallingInput,
    GenomeKitQueryInput,
    GenomicsPreparedRun,
    GenomicsToolReport,
    GenomicsToolReportInput,
    IlluminaIcaRequestInput,
    ParagraphGenotypingInput,
    ZippyPipelineInput,
    build_genomics_tool_report,
    prepare_expansionhunter_denovo,
    prepare_gauchian_calling,
    prepare_genomekit_query,
    prepare_illumina_ica_request,
    prepare_paragraph_genotyping,
    prepare_zippy_pipeline,
)
from .registry import Permission, Tool, ToolFn, ToolMetadata, register
from .scientific_analysis import (
    ScientificAnalysisInput,
    ScientificAnalysisResult,
    run_scientific_analysis,
)
from .scientific_capabilities import (
    ScientificCapabilityReport,
    build_scientific_capability_report,
)


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
    fn=cast(ToolFn, _verify_citation),
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
    fn=cast(ToolFn, _search_literature),
)


# Register at import time. ``overwrite=True`` keeps re-imports idempotent
# (pytest collection, dev-loop reloads, etc.).
register(_VERIFY_CITATION_TOOL, overwrite=True)
register(_SEARCH_LITERATURE_TOOL, overwrite=True)


# --- scientific_capability_report -----------------------------------------


class ScientificCapabilityReportInput(BaseModel):
    """Input schema for ``scientific_capability_report``."""


def _scientific_capability_report(
    payload: ScientificCapabilityReportInput,  # noqa: ARG001 - future filter hook
) -> ScientificCapabilityReport:
    """Return the scientific stack decision matrix and repeatability checks."""
    return build_scientific_capability_report()


_SCIENTIFIC_CAPABILITY_REPORT_TOOL = Tool(
    metadata=ToolMetadata(
        name="scientific_capability_report",
        description=(
            "Review Plato's scientific analysis stack recommendations and return "
            "deterministic verification checks for graphing, single-cell, "
            "chemistry, physics, quantum physics, HEP, and statistics workflows."
        ),
        permissions=set(),
        category="scientific_analysis",
    ),
    input_schema=ScientificCapabilityReportInput,
    output_schema=ScientificCapabilityReport,
    fn=cast(ToolFn, _scientific_capability_report),
)

register(_SCIENTIFIC_CAPABILITY_REPORT_TOOL, overwrite=True)


# --- run_scientific_analysis ----------------------------------------------


_RUN_SCIENTIFIC_ANALYSIS_TOOL = Tool(
    metadata=ToolMetadata(
        name="run_scientific_analysis",
        description=(
            "Execute deterministic scientific calculations and plotting workflows "
            "for publications. Supports formula_mass, harmonic_oscillator, "
            "linear_regression, single_cell_qc, quantum_pauli, and publication_plot. "
            "Returns Markdown, LaTeX, tables, artifacts, reproducibility metadata, "
            "and validation checks."
        ),
        permissions={"filesystem_write"},
        category="scientific_analysis",
    ),
    input_schema=ScientificAnalysisInput,
    output_schema=ScientificAnalysisResult,
    fn=cast(ToolFn, run_scientific_analysis),
)

register(_RUN_SCIENTIFIC_ANALYSIS_TOOL, overwrite=True)


# --- genomics optional tools ----------------------------------------------


def _genomics_tool_report(
    payload: GenomicsToolReportInput,  # noqa: ARG001 - future filter hook
) -> GenomicsToolReport:
    """Return the optional Illumina genomics adapter decision matrix."""
    return build_genomics_tool_report()


_GENOMICS_TOOL_REPORT_TOOL = Tool(
    metadata=ToolMetadata(
        name="genomics_tool_report",
        description=(
            "Review optional GenomeKit and Illumina genomics adapters for "
            "genomic resource access, NGS prototyping, known structural-variant "
            "genotyping, de novo STR expansion discovery, WGS GBA calling, and "
            "Illumina Connected Analytics orchestration."
        ),
        permissions=set(),
        category="genomics",
    ),
    input_schema=GenomicsToolReportInput,
    output_schema=GenomicsToolReport,
    fn=cast(ToolFn, _genomics_tool_report),
)

register(_GENOMICS_TOOL_REPORT_TOOL, overwrite=True)


_GENOMICS_TOOL_DEFINITIONS: list[
    tuple[str, str, type[BaseModel], ToolFn, set[Permission]]
] = [
    (
        "prepare_genomekit_query",
        "Prepare or execute GenomeKit reference sequence, annotation, VCF, variant-sequence, motif, or track queries.",
        GenomeKitQueryInput,
        cast(ToolFn, prepare_genomekit_query),
        {"filesystem_read", "code_exec"},
    ),
    (
        "prepare_zippy_pipeline",
        "Prepare or execute an external ZIPPY NGS pipeline command from JSON workflow inputs.",
        ZippyPipelineInput,
        cast(ToolFn, prepare_zippy_pipeline),
        {"filesystem_read", "filesystem_write", "code_exec"},
    ),
    (
        "prepare_paragraph_genotyping",
        "Prepare or execute Paragraph multigrmpy structural-variant genotyping for WGS short-read data.",
        ParagraphGenotypingInput,
        cast(ToolFn, prepare_paragraph_genotyping),
        {"filesystem_read", "filesystem_write", "code_exec"},
    ),
    (
        "prepare_expansionhunter_denovo",
        "Prepare or execute ExpansionHunter Denovo profile, merge, case-control, or outlier STR expansion analysis.",
        ExpansionHunterDenovoInput,
        cast(ToolFn, prepare_expansionhunter_denovo),
        {"filesystem_read", "filesystem_write", "code_exec"},
    ),
    (
        "prepare_gauchian_calling",
        "Prepare or execute Gauchian WGS GBA/GBAP1 variant calling.",
        GauchianCallingInput,
        cast(ToolFn, prepare_gauchian_calling),
        {"filesystem_read", "filesystem_write", "code_exec"},
    ),
    (
        "prepare_illumina_ica_request",
        "Prepare or execute a constrained Illumina Connected Analytics API request using environment-backed credentials.",
        IlluminaIcaRequestInput,
        cast(ToolFn, prepare_illumina_ica_request),
        {"network"},
    ),
]

for name, description, input_schema, fn, permissions in _GENOMICS_TOOL_DEFINITIONS:
    register(
        Tool(
            metadata=ToolMetadata(
                name=name,
                description=description,
                permissions=permissions,
                category="genomics",
            ),
            input_schema=input_schema,
            output_schema=GenomicsPreparedRun,
            fn=fn,
        ),
        overwrite=True,
    )


__all__ = [
    "VerifyCitationInput",
    "VerifyCitationOutput",
    "SearchLiteratureInput",
    "SearchLiteratureOutput",
    "ScientificAnalysisInput",
    "ScientificAnalysisResult",
    "ScientificCapabilityReportInput",
    "ExpansionHunterDenovoInput",
    "GauchianCallingInput",
    "GenomeKitQueryInput",
    "GenomicsPreparedRun",
    "GenomicsToolReportInput",
    "IlluminaIcaRequestInput",
    "ParagraphGenotypingInput",
    "ZippyPipelineInput",
]
