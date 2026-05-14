"""Optional genomics pipeline adapters for WGS-oriented agent workflows."""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


GenomicsStatus = Literal["ready", "missing_requirements", "executed", "failed"]
IcaOperation = Literal[
    "token",
    "get_projects",
    "get_pipelines",
    "get_analysis",
    "get_analysis_outputs",
    "create_cwl_analysis",
    "create_nextflow_analysis",
    "custom_request",
]


class GenomicsCapability(BaseModel):
    name: str
    registry_tool: str
    domain: str
    source_url: str
    decision: Literal["optional_cli_adapter", "optional_api_adapter"]
    supported_use: str
    requirements: list[str]
    required_inputs: list[str]
    expected_artifacts: list[str]
    verification: list[str]
    caveats: list[str] = Field(default_factory=list)
    install_hint: str | None = None
    configured: bool


class GenomicsToolReport(BaseModel):
    summary: str
    capabilities: list[GenomicsCapability]
    fingerprint: str


class GenomicsToolReportInput(BaseModel):
    """Input schema for ``genomics_tool_report``."""


class GenomicsExecutionResult(BaseModel):
    returncode: int | None = None
    elapsed_ms: int | None = None
    stdout: str = ""
    stderr: str = ""
    response_status_code: int | None = None
    response_body: Any = None


class GenomicsPreparedRun(BaseModel):
    tool: str
    operation: str
    status: GenomicsStatus
    command: list[str] = Field(default_factory=list)
    command_display: str = ""
    request: dict[str, Any] = Field(default_factory=dict)
    requirements: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    scientific_scope: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    execution: GenomicsExecutionResult | None = None


class _CommandInput(BaseModel):
    output_dir: str | None = None
    executable: str | None = None
    python_executable: str | None = None
    execute: bool = False
    timeout_seconds: int = Field(default=3600, ge=1, le=604800)
    extra_args: list[str] = Field(default_factory=list)


class ZippyPipelineInput(_CommandInput):
    """Prepare or execute an Illumina ZIPPY pipeline command."""

    operation: Literal["make_params", "run_pipeline"] = "run_pipeline"
    proto_workflow_path: str | None = None
    params_path: str | None = None


class ParagraphGenotypingInput(_CommandInput):
    """Prepare or execute Paragraph structural-variant genotyping."""

    variants_path: str
    manifest_path: str
    reference_fasta: str


class ExpansionHunterDenovoInput(_CommandInput):
    """Prepare or execute ExpansionHunter Denovo profile/merge/analysis commands."""

    operation: Literal[
        "profile",
        "merge",
        "casecontrol_locus",
        "casecontrol_motif",
        "outlier_locus",
        "outlier_motif",
    ] = "profile"
    reads_path: str | None = None
    reference_fasta: str | None = None
    manifest_path: str | None = None
    multisample_profile: str | None = None
    output_prefix: str | None = None
    output_path: str | None = None
    target_regions_bed: str | None = None
    min_anchor_mapq: int = Field(default=50, ge=0)
    max_irr_mapq: int = Field(default=40, ge=0)


class GauchianCallingInput(_CommandInput):
    """Prepare or execute Gauchian WGS GBA variant calling."""

    manifest_path: str
    genome: Literal["19", "37", "38"] = "38"
    prefix: str = "gauchian"
    threads: int = Field(default=1, ge=1)
    reference_fasta: str | None = None


class IlluminaIcaRequestInput(BaseModel):
    """Prepare or execute a constrained Illumina Connected Analytics API request."""

    operation: IcaOperation = "get_projects"
    base_url: str | None = None
    project_id: str | None = None
    analysis_id: str | None = None
    method: Literal["GET", "POST", "PUT", "DELETE"] | None = None
    path: str | None = None
    json_body: dict[str, Any] = Field(default_factory=dict)
    execute: bool = False
    timeout_seconds: int = Field(default=60, ge=1, le=600)


class GenomeKitQueryInput(_CommandInput):
    """Prepare or execute a GenomeKit resource query."""

    operation: Literal[
        "sequence",
        "annotation_overlaps",
        "vcf_query",
        "variant_sequence",
        "motif_scan",
        "track_query",
    ] = "sequence"
    genome: str = "hg38"
    chrom: str | None = None
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    strand: Literal["+", "-"] = "+"
    annotation_table: Literal["genes", "transcripts", "exons", "introns", "cdss"] = (
        "genes"
    )
    vcf_path: str | None = None
    track_path: str | None = None
    motif: str | None = None
    variants: list[str] = Field(default_factory=list)
    info_ids: list[str] = Field(default_factory=list)
    fmt_ids: list[str] = Field(default_factory=list)
    max_records: int = Field(default=50, ge=1, le=1000)


def build_genomics_tool_report() -> GenomicsToolReport:
    capabilities = [
        _capability(
            name="GenomeKit",
            registry_tool="prepare_genomekit_query",
            domain="genomic resource access and ML feature extraction",
            source_url="https://github.com/deepgenomics/GenomeKit",
            decision="optional_cli_adapter",
            supported_use=(
                "Query reference DNA, annotation tables, genomic tracks, VCF "
                "variants, variant-applied sequences, and motif hits through "
                "GenomeKit's Python API without importing the native package at "
                "Plato dashboard startup."
            ),
            requirements=[
                "genomekit Python package",
                "GenomeKit resource data for the selected assembly or annotation",
                "Optional VCF, BAM/SAM-backed, or GenomeTrack files for file-backed queries",
            ],
            required_inputs=[
                "sequence/annotation/motif/track: genome, chrom, start, end",
                "vcf_query: vcf_path plus interval",
                "variant_sequence: genome, interval, and variants",
                "track_query: track_path plus interval",
            ],
            expected_artifacts=[
                "JSON stdout with query metadata and result rows",
                "GenomeKit resource cache entries under GENOMEKIT_DATA_DIR or the platform default",
                "Optional manuscript-ready sequence/variant/annotation tables copied into Plato run artifacts",
            ],
            verification=[
                "Lazy-import genome_kit only inside the subprocess execution path",
                "Record GenomeKit version, operation, genome, interval, and resource paths",
                "Use 0-based exclusive-end intervals and include UCSC coordinates in query output",
            ],
            caveats=[
                "GenomeKit may download prebuilt resources from its configured data source on first use.",
                "GenomeKit intervals are 0-based with an exclusive end; convert external coordinates before querying.",
            ],
            install_hint="conda install -c conda-forge genomekit or pip install genomekit",
            configured=importlib.util.find_spec("genome_kit") is not None,
        ),
        _capability(
            name="ZIPPY",
            registry_tool="prepare_zippy_pipeline",
            domain="NGS pipeline prototyping",
            source_url="https://github.com/Illumina/zippy",
            decision="optional_cli_adapter",
            supported_use=(
                "Generate ZIPPY JSON parameter files from proto-workflows and run "
                "configured NGS pipeline stages."
            ),
            requirements=[
                "CPython 2.7 runtime",
                "zippy-pipeline package",
                "Illumina pyflow dependency",
                "Pipeline-stage tools such as BWA, Bcl2Fastq, RSEM, MACS, Picard, or Nirvana as required by the selected stages",
            ],
            required_inputs=[
                "proto_workflow_path for make_params",
                "params_path for run_pipeline",
            ],
            expected_artifacts=[
                "ZIPPY parameter JSON",
                "Stage outputs defined by the selected JSON workflow",
                "Pipeline logs from pyflow/ZIPPY execution",
            ],
            verification=[
                "Validate JSON parameter file exists before execution",
                "Record selected stages and resolved Python 2.7 executable",
                "Preserve generated pipeline logs and stage artifacts",
            ],
            caveats=[
                "ZIPPY is Python 2.7-era software and must not be imported into Plato's Python 3.12 process.",
                "The adapter runs it only as an external command when explicitly configured.",
            ],
            install_hint=(
                "Set PLATO_ZIPPY_PYTHON to a CPython 2.7 environment containing "
                "zippy-pipeline and pyflow."
            ),
            configured=_configured_from_env("PLATO_ZIPPY_PYTHON", ["python2.7"]),
        ),
        _capability(
            name="Paragraph",
            registry_tool="prepare_paragraph_genotyping",
            domain="Known structural-variant genotyping from WGS short reads",
            source_url="https://github.com/Illumina/paragraph",
            decision="optional_cli_adapter",
            supported_use=(
                "Run multigrmpy.py against a candidate VCF/graph JSON, sample "
                "manifest, and matching reference FASTA."
            ),
            requirements=[
                "Paragraph build or static release",
                "Python 3.6+ for wrapper scripts",
                "BAM/CRAM inputs with depth/read-length or idxdepth metadata",
                "Reference FASTA matching the alignments",
            ],
            required_inputs=[
                "variants_path",
                "manifest_path",
                "reference_fasta",
                "output_dir",
            ],
            expected_artifacts=[
                "genotypes.vcf.gz",
                "genotypes.json.gz",
                "variants.vcf.gz",
                "variants.json.gz",
                "grmpy.log",
            ],
            verification=[
                "Require the sample manifest before execution",
                "Record the exact candidate VCF/JSON and reference FASTA",
                "Check for genotype VCF/JSON outputs and log file after execution",
            ],
            caveats=[
                "The candidate variants must be known variants; Paragraph is not a discovery caller.",
                "The reference FASTA must match the BAM/CRAM alignment reference.",
            ],
            install_hint="Set PLATO_PARAGRAPH_MULTIGRMPY to bin/multigrmpy.py from a Paragraph build.",
            configured=_configured_from_env(
                "PLATO_PARAGRAPH_MULTIGRMPY", ["multigrmpy.py"]
            ),
        ),
        _capability(
            name="ExpansionHunter Denovo",
            registry_tool="prepare_expansionhunter_denovo",
            domain="De novo short tandem repeat expansion discovery",
            source_url="https://github.com/Illumina/ExpansionHunterDenovo",
            decision="optional_cli_adapter",
            supported_use=(
                "Compute STR profiles, merge multisample profiles, then run "
                "case/control or outlier STR expansion analyses."
            ),
            requirements=[
                "ExpansionHunterDenovo binary",
                "Python 3 for casecontrol.py/outlier.py secondary analyses",
                "BAM/CRAM short-read WGS alignments",
                "Reference FASTA used for alignment",
            ],
            required_inputs=[
                "profile: reads_path, reference_fasta, output_prefix",
                "merge: manifest_path, reference_fasta, output_prefix",
                "case/control or outlier: manifest_path, multisample_profile, output_path",
            ],
            expected_artifacts=[
                "*.str_profile.json",
                "*.locus.tsv",
                "*.motif.tsv",
                "*.multisample_profile.json",
                "casecontrol/outlier TSV findings",
            ],
            verification=[
                "Record MAPQ thresholds for STR profile generation",
                "Preserve manifest case/control labels",
                "Treat locations as approximate and counts as depth-normalized evidence, not genotypes",
            ],
            caveats=[
                "Best suited to short reads of about 100-200 bp and expansions longer than read length.",
                "Samples should have comparable sequencing and preprocessing to reduce false signals.",
            ],
            install_hint=(
                "Set PLATO_EHDN_BINARY to ExpansionHunterDenovo and optionally "
                "PLATO_EHDN_CASECONTROL_SCRIPT / PLATO_EHDN_OUTLIER_SCRIPT."
            ),
            configured=_configured_from_env(
                "PLATO_EHDN_BINARY", ["ExpansionHunterDenovo"]
            ),
        ),
        _capability(
            name="Gauchian",
            registry_tool="prepare_gauchian_calling",
            domain="WGS GBA/GBAP1 variant calling",
            source_url="https://github.com/Illumina/Gauchian",
            decision="optional_cli_adapter",
            supported_use=(
                "Run targeted GBA variant calling from whole-genome BAM/CRAM files, "
                "including pseudogene-related Exon 9-11 events."
            ),
            requirements=[
                "gauchian executable or Python package",
                "WGS BAM/CRAM input manifest",
                "Genome build 19, 37, or 38",
                "Approximately 30X or higher WGS depth for intended accuracy",
            ],
            required_inputs=["manifest_path", "genome", "prefix", "output_dir"],
            expected_artifacts=["Gauchian TSV", "Gauchian JSON per-sample detail"],
            verification=[
                "Reject targeted sequencing as unsupported by the method contract",
                "Record genome build and reference FASTA for CRAM inputs",
                "Surface CN(GBA+GBAP1)=None as a no-call requiring downstream caution",
            ],
            caveats=[
                "Lower WGS coverage can produce false calls.",
                "No small-variant calling is performed when regional copy number is a no-call.",
            ],
            install_hint="pip install gauchian, then ensure gauchian is on PATH or set PLATO_GAUCHIAN_BINARY.",
            configured=_configured_from_env("PLATO_GAUCHIAN_BINARY", ["gauchian"]),
        ),
        _capability(
            name="ica-sdk-python",
            registry_tool="prepare_illumina_ica_request",
            domain="Illumina Connected Analytics API orchestration",
            source_url="https://github.com/Illumina/ica-sdk-python",
            decision="optional_api_adapter",
            supported_use=(
                "Prepare or execute authenticated ICA project, pipeline, data, and "
                "analysis requests for hosted genomic workflows."
            ),
            requirements=[
                "ICA tenant access",
                "PLATO_ICA_API_KEY",
                "PLATO_ICA_JWT for non-token endpoints",
                "Optional icasdk package for SDK-backed client code",
            ],
            required_inputs=[
                "token: API key or Basic auth in environment",
                "analysis operations: project_id and operation-specific body/analysis id",
            ],
            expected_artifacts=[
                "ICA request metadata",
                "ICA response payload",
                "Analysis ids and output data ids when launching or inspecting runs",
            ],
            verification=[
                "Never echo API keys, Basic credentials, or JWT values",
                "Require API key plus JWT for ordinary API endpoints",
                "Use POST /api/tokens only for token generation/refresh workflows",
            ],
            caveats=[
                "Live execution depends on tenant-specific entitlements and project ids.",
                "Network calls are skipped unless execute=True.",
            ],
            install_hint="pip install git+https://github.com/Illumina/ica-sdk-python.git or use the REST-compatible request adapter.",
            configured=bool(os.environ.get("PLATO_ICA_API_KEY")),
        ),
    ]
    payload = "|".join(
        f"{item.registry_tool}:{item.configured}" for item in capabilities
    )
    return GenomicsToolReport(
        summary=(
            "GenomeKit and Illumina genomics integrations are registered as "
            "optional tools: a GenomeKit adapter for genomic resource queries, "
            "external CLI adapters for local WGS/NGS execution, and a "
            "network-gated ICA request adapter for hosted workflow orchestration."
        ),
        capabilities=capabilities,
        fingerprint=__import__("hashlib")
        .sha256(payload.encode("utf-8"))
        .hexdigest()[:16],
    )


def prepare_zippy_pipeline(payload: ZippyPipelineInput) -> GenomicsPreparedRun:
    missing: list[str] = []
    python_bin = _resolve_executable(
        payload.python_executable or payload.executable,
        "PLATO_ZIPPY_PYTHON",
        ["python2.7"],
        missing,
        "CPython 2.7 with zippy installed",
    )
    output_dir = Path(payload.output_dir or ".")
    if payload.operation == "make_params":
        proto = _require_path(
            payload.proto_workflow_path, "proto_workflow_path", missing
        )
        params = payload.params_path or str(output_dir / "zippy_params.json")
        command = [python_bin, "-m", "zippy.make_params", proto or "", params]
        expected = [params]
    else:
        params_path = _require_path(payload.params_path, "params_path", missing)
        command = [python_bin, "-m", "zippy.zippy", params_path or ""]
        expected = [
            "ZIPPY stage artifacts declared in params_path",
            "ZIPPY/pyflow logs",
        ]
    command.extend(payload.extra_args)
    return _finish_command(
        tool="ZIPPY",
        operation=payload.operation,
        command=command,
        requirements=["CPython 2.7", "zippy-pipeline", "pyflow"],
        missing=missing,
        expected_artifacts=expected,
        scientific_scope=["NGS pipeline prototyping", "JSON pipeline specifications"],
        warnings=[
            "Runs out-of-process because ZIPPY is CPython 2.7 software.",
            "Generated findings depend on configured downstream stage tools.",
        ],
        execute=payload.execute,
        timeout_seconds=payload.timeout_seconds,
    )


def prepare_paragraph_genotyping(
    payload: ParagraphGenotypingInput,
) -> GenomicsPreparedRun:
    missing: list[str] = []
    script = _resolve_executable(
        payload.executable,
        "PLATO_PARAGRAPH_MULTIGRMPY",
        ["multigrmpy.py"],
        missing,
        "Paragraph multigrmpy.py",
    )
    python_bin = _resolve_python(payload.python_executable)
    _require_path(payload.variants_path, "variants_path", missing)
    _require_path(payload.manifest_path, "manifest_path", missing)
    _require_path(payload.reference_fasta, "reference_fasta", missing)
    output_dir = payload.output_dir or "paragraph_out"
    command = [
        python_bin,
        script,
        "-i",
        payload.variants_path,
        "-m",
        payload.manifest_path,
        "-r",
        payload.reference_fasta,
        "-o",
        output_dir,
        *payload.extra_args,
    ]
    return _finish_command(
        tool="Paragraph",
        operation="multigrmpy",
        command=command,
        requirements=[
            "Paragraph build/static release",
            "Python 3",
            "indexed BAM/CRAM files",
            "reference FASTA",
        ],
        missing=missing,
        expected_artifacts=[
            str(Path(output_dir) / "genotypes.vcf.gz"),
            str(Path(output_dir) / "genotypes.json.gz"),
            str(Path(output_dir) / "variants.vcf.gz"),
            str(Path(output_dir) / "variants.json.gz"),
            str(Path(output_dir) / "grmpy.log"),
        ],
        scientific_scope=["known structural variation", "WGS short-read genotyping"],
        warnings=[
            "Paragraph genotypes known candidate variants; it is not a de novo SV discovery caller.",
            "Manifest depth/read-length metadata should match the input BAM/CRAM files.",
        ],
        execute=payload.execute,
        timeout_seconds=payload.timeout_seconds,
    )


def prepare_expansionhunter_denovo(
    payload: ExpansionHunterDenovoInput,
) -> GenomicsPreparedRun:
    missing: list[str] = []
    output_prefix = payload.output_prefix or str(
        Path(payload.output_dir or ".") / "ehdn"
    )
    if payload.operation in {"profile", "merge"}:
        binary = _resolve_executable(
            payload.executable,
            "PLATO_EHDN_BINARY",
            ["ExpansionHunterDenovo"],
            missing,
            "ExpansionHunterDenovo binary",
        )
        if payload.operation == "profile":
            _require_path(payload.reads_path, "reads_path", missing)
            _require_path(payload.reference_fasta, "reference_fasta", missing)
            command = [
                binary,
                "profile",
                "--reads",
                payload.reads_path or "",
                "--reference",
                payload.reference_fasta or "",
                "--output-prefix",
                output_prefix,
                "--min-anchor-mapq",
                str(payload.min_anchor_mapq),
                "--max-irr-mapq",
                str(payload.max_irr_mapq),
                *payload.extra_args,
            ]
            expected = [
                f"{output_prefix}.str_profile.json",
                f"{output_prefix}.locus.tsv",
                f"{output_prefix}.motif.tsv",
            ]
        else:
            _require_path(payload.reference_fasta, "reference_fasta", missing)
            _require_path(payload.manifest_path, "manifest_path", missing)
            command = [
                binary,
                "merge",
                "--reference",
                payload.reference_fasta or "",
                "--manifest",
                payload.manifest_path or "",
                "--output-prefix",
                output_prefix,
                *payload.extra_args,
            ]
            expected = [f"{output_prefix}.multisample_profile.json"]
    else:
        script_env = (
            "PLATO_EHDN_CASECONTROL_SCRIPT"
            if payload.operation.startswith("casecontrol")
            else "PLATO_EHDN_OUTLIER_SCRIPT"
        )
        script_name = (
            "casecontrol.py"
            if payload.operation.startswith("casecontrol")
            else "outlier.py"
        )
        script = _resolve_executable(
            payload.executable, script_env, [script_name], missing, script_name
        )
        python_bin = _resolve_python(payload.python_executable)
        mode = "locus" if payload.operation.endswith("locus") else "motif"
        output_path = payload.output_path or f"{output_prefix}.{payload.operation}.tsv"
        _require_path(payload.manifest_path, "manifest_path", missing)
        _require_path(payload.multisample_profile, "multisample_profile", missing)
        command = [
            python_bin,
            script,
            mode,
            "--manifest",
            payload.manifest_path or "",
            "--multisample-profile",
            payload.multisample_profile or "",
            "--output",
            output_path,
        ]
        if payload.target_regions_bed:
            _require_path(payload.target_regions_bed, "target_regions_bed", missing)
            command.extend(["--target-regions", payload.target_regions_bed])
        command.extend(payload.extra_args)
        expected = [output_path]
    return _finish_command(
        tool="ExpansionHunter Denovo",
        operation=payload.operation,
        command=command,
        requirements=[
            "ExpansionHunterDenovo binary for profile/merge",
            "Python 3 scripts for case-control/outlier analyses",
            "short-read BAM/CRAM WGS data",
            "matched reference FASTA",
        ],
        missing=missing,
        expected_artifacts=expected,
        scientific_scope=[
            "de novo STR expansion discovery",
            "WGS short reads",
            "case-control/outlier repeat prioritization",
        ],
        warnings=[
            "EHdn reports approximate loci and depth-normalized STR evidence rather than genotypes.",
            "Comparable sequencing platform, coverage, read length, and preprocessing are important for valid comparisons.",
        ],
        execute=payload.execute,
        timeout_seconds=payload.timeout_seconds,
    )


def prepare_gauchian_calling(payload: GauchianCallingInput) -> GenomicsPreparedRun:
    missing: list[str] = []
    binary = _resolve_executable(
        payload.executable,
        "PLATO_GAUCHIAN_BINARY",
        ["gauchian"],
        missing,
        "gauchian executable",
    )
    _require_path(payload.manifest_path, "manifest_path", missing)
    output_dir = payload.output_dir or "gauchian_out"
    command = [
        binary,
        "--manifest",
        payload.manifest_path,
        "--genome",
        payload.genome,
        "--prefix",
        payload.prefix,
        "--outDir",
        output_dir,
        "--threads",
        str(payload.threads),
    ]
    if payload.reference_fasta:
        _require_path(payload.reference_fasta, "reference_fasta", missing)
        command.extend(["--reference", payload.reference_fasta])
    command.extend(payload.extra_args)
    return _finish_command(
        tool="Gauchian",
        operation="call",
        command=command,
        requirements=[
            "gauchian package",
            "WGS BAM/CRAM manifest",
            "genome build 19/37/38",
        ],
        missing=missing,
        expected_artifacts=[
            str(Path(output_dir) / f"{payload.prefix}.tsv"),
            str(Path(output_dir) / f"{payload.prefix}.json"),
        ],
        scientific_scope=["GBA", "GBAP1", "WGS pseudogene-aware variant calling"],
        warnings=[
            "Gauchian is designed for WGS, not targeted sequencing data.",
            "Standard-depth WGS around 30X or higher is expected for reliable calls.",
            "CN(GBA+GBAP1)=None means copy-number no-call and blocks small variant calling for that sample.",
        ],
        execute=payload.execute,
        timeout_seconds=payload.timeout_seconds,
    )


def prepare_illumina_ica_request(
    payload: IlluminaIcaRequestInput,
) -> GenomicsPreparedRun:
    missing: list[str] = []
    base_url = (
        payload.base_url
        or os.environ.get("PLATO_ICA_BASE_URL")
        or "https://ica.illumina.com/ica/rest"
    ).rstrip("/")
    method, path = _ica_operation_to_request(payload, missing)
    url = f"{base_url}{path}"
    token_endpoint = payload.operation == "token"
    api_key = os.environ.get("PLATO_ICA_API_KEY")
    jwt = os.environ.get("PLATO_ICA_JWT")
    basic = os.environ.get("PLATO_ICA_BASIC_AUTH")
    if token_endpoint:
        if not api_key and not basic:
            missing.append("PLATO_ICA_API_KEY or PLATO_ICA_BASIC_AUTH")
    else:
        if not api_key:
            missing.append("PLATO_ICA_API_KEY")
        if not jwt:
            missing.append("PLATO_ICA_JWT")

    request = {
        "method": method,
        "url": url,
        "auth": "token" if token_endpoint else "api_key+jwt",
        "headers": _ica_redacted_headers(
            token_endpoint, bool(api_key), bool(jwt), bool(basic)
        ),
        "body_keys": sorted(payload.json_body),
        "icasdk_available": importlib.util.find_spec("icasdk") is not None,
    }
    result = GenomicsPreparedRun(
        tool="ica-sdk-python",
        operation=payload.operation,
        status="missing_requirements" if missing else "ready",
        request=request,
        requirements=[
            "ICA tenant access",
            "PLATO_ICA_API_KEY",
            "PLATO_ICA_JWT for non-token endpoints",
        ],
        missing_requirements=sorted(set(missing)),
        expected_artifacts=[
            "ICA response payload",
            "analysis ids/output data ids where applicable",
        ],
        scientific_scope=[
            "Illumina Connected Analytics",
            "hosted WGS workflow orchestration",
        ],
        warnings=[
            "Secrets are read from environment variables and are never echoed in tool output."
        ],
    )
    if payload.execute and not missing:
        return _execute_ica_request(result, payload, method, url, token_endpoint)
    return result


def prepare_genomekit_query(payload: GenomeKitQueryInput) -> GenomicsPreparedRun:
    missing: list[str] = []
    if importlib.util.find_spec("genome_kit") is None:
        missing.append("genome_kit package (conda install -c conda-forge genomekit)")
    _validate_interval(payload, missing)
    if payload.operation == "vcf_query":
        _require_path(payload.vcf_path, "vcf_path", missing)
    if payload.operation == "track_query":
        _require_path(payload.track_path, "track_path", missing)
    if payload.operation == "motif_scan" and not payload.motif:
        missing.append("motif")
    if payload.operation == "variant_sequence" and not payload.variants:
        missing.append("variants")

    options = payload.model_dump(
        exclude={
            "execute",
            "timeout_seconds",
            "extra_args",
            "output_dir",
            "executable",
            "python_executable",
        },
    )
    command = [
        _resolve_python(payload.python_executable),
        "-c",
        _GENOMEKIT_QUERY_SCRIPT,
        json.dumps(options, sort_keys=True),
        *payload.extra_args,
    ]
    return _finish_command(
        tool="GenomeKit",
        operation=payload.operation,
        command=command,
        requirements=[
            "genomekit Python package",
            "GenomeKit data files for the selected genome/annotation",
            "0-based exclusive-end interval coordinates",
        ],
        missing=missing,
        expected_artifacts=[
            "JSON query result on stdout",
            "GenomeKit resource cache files as needed",
        ],
        scientific_scope=[
            "reference sequence extraction",
            "genomic annotations",
            "variant-aware feature extraction",
            "motif/track/VCF resource queries",
        ],
        warnings=[
            "GenomeKit may fetch remote resource files during first access.",
            "Coordinate inputs are DNA0: 0-based with an exclusive end.",
        ],
        execute=payload.execute,
        timeout_seconds=payload.timeout_seconds,
    )


def _capability(**kwargs: Any) -> GenomicsCapability:
    return GenomicsCapability.model_validate(kwargs)


def _configured_from_env(env_var: str, fallback_names: list[str]) -> bool:
    configured = os.environ.get(env_var)
    if configured:
        return Path(configured).exists() or shutil.which(configured) is not None
    return any(shutil.which(name) for name in fallback_names)


def _resolve_executable(
    configured: str | None,
    env_var: str,
    fallback_names: list[str],
    missing: list[str],
    label: str,
) -> str:
    raw = configured or os.environ.get(env_var)
    if raw:
        resolved = shutil.which(raw) or raw
        if _command_available(resolved):
            return resolved
        missing.append(f"{label} ({env_var}={raw})")
        return resolved
    for name in fallback_names:
        found = shutil.which(name)
        if found:
            return found
    missing.append(f"{label} ({env_var} or PATH)")
    return fallback_names[0]


def _resolve_python(configured: str | None) -> str:
    if configured:
        return shutil.which(configured) or configured
    return sys.executable


def _command_available(command: str) -> bool:
    if shutil.which(command):
        return True
    try:
        return Path(command).exists()
    except OSError:
        return False


def _require_path(value: str | None, label: str, missing: list[str]) -> str | None:
    if not value:
        missing.append(label)
        return None
    if _looks_remote(value):
        return value
    path = Path(value)
    if not path.exists():
        missing.append(f"{label} ({value})")
    return value


def _validate_interval(payload: GenomeKitQueryInput, missing: list[str]) -> None:
    if not payload.chrom:
        missing.append("chrom")
    if payload.start is None:
        missing.append("start")
    if payload.end is None:
        missing.append("end")
    if (
        payload.start is not None
        and payload.end is not None
        and payload.end < payload.start
    ):
        missing.append("end must be greater than or equal to start")


def _looks_remote(value: str) -> bool:
    return "://" in value and not value.startswith("file://")


def _finish_command(
    *,
    tool: str,
    operation: str,
    command: list[str],
    requirements: list[str],
    missing: list[str],
    expected_artifacts: list[str],
    scientific_scope: list[str],
    warnings: list[str],
    execute: bool,
    timeout_seconds: int,
) -> GenomicsPreparedRun:
    result = GenomicsPreparedRun(
        tool=tool,
        operation=operation,
        status="missing_requirements" if missing else "ready",
        command=command,
        command_display=shlex.join(command),
        requirements=requirements,
        missing_requirements=sorted(set(missing)),
        expected_artifacts=expected_artifacts,
        scientific_scope=scientific_scope,
        warnings=warnings,
    )
    if execute and not missing:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return result.model_copy(
                update={
                    "status": "executed" if completed.returncode == 0 else "failed",
                    "execution": GenomicsExecutionResult(
                        returncode=completed.returncode,
                        elapsed_ms=elapsed_ms,
                        stdout=completed.stdout[-10000:],
                        stderr=completed.stderr[-10000:],
                    ),
                }
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as tool output
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return result.model_copy(
                update={
                    "status": "failed",
                    "execution": GenomicsExecutionResult(
                        elapsed_ms=elapsed_ms,
                        stderr=f"{exc.__class__.__name__}: {exc}",
                    ),
                }
            )
    return result


def _ica_operation_to_request(
    payload: IlluminaIcaRequestInput, missing: list[str]
) -> tuple[str, str]:
    if payload.operation == "token":
        return "POST", "/api/tokens"
    if payload.operation == "get_projects":
        return "GET", "/api/projects"
    if payload.operation == "get_pipelines":
        return "GET", "/api/pipelines"
    if payload.operation in {"get_analysis", "get_analysis_outputs"}:
        if not payload.project_id:
            missing.append("project_id")
        if not payload.analysis_id:
            missing.append("analysis_id")
        suffix = "outputs" if payload.operation == "get_analysis_outputs" else ""
        path = f"/api/projects/{payload.project_id or '{projectId}'}/analyses/{payload.analysis_id or '{analysisId}'}"
        if suffix:
            path = f"{path}/{suffix}"
        return "GET", path
    if payload.operation in {"create_cwl_analysis", "create_nextflow_analysis"}:
        if not payload.project_id:
            missing.append("project_id")
        kind = "cwl" if payload.operation == "create_cwl_analysis" else "nextflow"
        return (
            "POST",
            f"/api/projects/{payload.project_id or '{projectId}'}/analysis:{kind}",
        )
    if not payload.method:
        missing.append("method")
    if not payload.path:
        missing.append("path")
    path = payload.path or "/api"
    if not path.startswith("/"):
        path = f"/{path}"
    return payload.method or "GET", path


def _ica_redacted_headers(
    token_endpoint: bool,
    has_api_key: bool,
    has_jwt: bool,
    has_basic: bool,
) -> dict[str, str]:
    headers = {"Accept": "application/vnd.illumina.v3+json"}
    if has_api_key:
        headers["X-API-Key"] = "<redacted>"
    if token_endpoint and has_basic:
        headers["Authorization"] = "Basic <redacted>"
    elif not token_endpoint and has_jwt:
        headers["Authorization"] = "Bearer <redacted>"
    return headers


def _execute_ica_request(
    prepared: GenomicsPreparedRun,
    payload: IlluminaIcaRequestInput,
    method: str,
    url: str,
    token_endpoint: bool,
) -> GenomicsPreparedRun:
    import httpx

    headers = {"Accept": "application/vnd.illumina.v3+json"}
    api_key = os.environ.get("PLATO_ICA_API_KEY")
    jwt = os.environ.get("PLATO_ICA_JWT")
    basic = os.environ.get("PLATO_ICA_BASIC_AUTH")
    if api_key:
        headers["X-API-Key"] = api_key
    if token_endpoint and basic:
        headers["Authorization"] = (
            basic if basic.startswith("Basic ") else f"Basic {basic}"
        )
    elif not token_endpoint and jwt:
        headers["Authorization"] = jwt if jwt.startswith("Bearer ") else f"Bearer {jwt}"

    started = time.monotonic()
    try:
        with httpx.Client(timeout=payload.timeout_seconds) as client:
            response = client.request(
                method,
                url,
                headers=headers,
                json=payload.json_body if payload.json_body is not None else None,
            )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        try:
            body: Any = response.json()
        except ValueError:
            body = response.text[-10000:]
        return prepared.model_copy(
            update={
                "status": "executed" if response.is_success else "failed",
                "execution": GenomicsExecutionResult(
                    elapsed_ms=elapsed_ms,
                    response_status_code=response.status_code,
                    response_body=body,
                ),
            }
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as tool output
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return prepared.model_copy(
            update={
                "status": "failed",
                "execution": GenomicsExecutionResult(
                    elapsed_ms=elapsed_ms,
                    stderr=f"{exc.__class__.__name__}: {exc}",
                ),
            }
        )


_GENOMEKIT_QUERY_SCRIPT = r"""
import json
import sys

import genome_kit as gk

options = json.loads(sys.argv[1])


def interval():
    return gk.Interval(
        options["chrom"],
        options["strand"],
        int(options["start"]),
        int(options["end"]),
        options["genome"],
    )


def summarize(item):
    data = {"repr": repr(item)}
    iv = getattr(item, "interval", item if isinstance(item, gk.Interval) else None)
    if iv is not None:
        data["interval"] = {
            "chrom": iv.chrom,
            "strand": iv.strand,
            "start": iv.start,
            "end": iv.end,
            "ucsc": iv.as_ucsc(),
        }
    for attr in ("id", "name", "gene_name", "gene_type", "transcript_type"):
        if hasattr(item, attr):
            try:
                data[attr] = getattr(item, attr)
            except Exception:
                pass
    return data


operation = options["operation"]
genome = gk.Genome(options["genome"])
iv = interval()
result = {
    "genomekit_version": getattr(gk, "__version__", "unknown"),
    "operation": operation,
    "genome": options["genome"],
    "interval": {
        "chrom": iv.chrom,
        "strand": iv.strand,
        "start": iv.start,
        "end": iv.end,
        "ucsc": iv.as_ucsc(),
    },
}

if operation == "sequence":
    result["sequence"] = genome.dna(iv)
elif operation == "annotation_overlaps":
    table = getattr(genome, options["annotation_table"])
    rows = table.find_overlapping(iv)
    result["records"] = [summarize(item) for item in rows[: options["max_records"]]]
    result["record_count"] = len(rows)
elif operation == "vcf_query":
    vcf = gk.VCFTable.from_vcf(
        options["vcf_path"],
        genome,
        info_ids=options["info_ids"],
        fmt_ids=options["fmt_ids"],
    )
    rows = vcf.find_within(iv)
    result["records"] = [summarize(item) for item in rows[: options["max_records"]]]
    result["record_count"] = len(rows)
elif operation == "variant_sequence":
    variants = [gk.Variant.from_string(value, genome) for value in options["variants"]]
    result["sequence"] = gk.VariantGenome(genome, variants).dna(iv)
    result["variants"] = options["variants"]
elif operation == "motif_scan":
    matches = []
    sequence = genome.dna(iv).upper()
    motif = options["motif"].upper()
    offset = sequence.find(motif)
    while offset >= 0 and len(matches) < options["max_records"]:
        start = iv.start + offset
        hit = gk.Interval(iv.chrom, iv.strand, start, start + len(motif), options["genome"])
        matches.append({"start": hit.start, "end": hit.end, "ucsc": hit.as_ucsc(), "motif": motif})
        offset = sequence.find(motif, offset + 1)
    result["records"] = matches
    result["record_count"] = len(matches)
elif operation == "track_query":
    track = gk.GenomeTrack(options["track_path"])
    values = track(iv)
    result["shape"] = list(getattr(values, "shape", []))
    result["values"] = values[: options["max_records"]].tolist()
else:
    raise ValueError(f"Unsupported GenomeKit operation: {operation}")

print(json.dumps(result, sort_keys=True))
"""


__all__ = [
    "ExpansionHunterDenovoInput",
    "GauchianCallingInput",
    "GenomeKitQueryInput",
    "GenomicsPreparedRun",
    "GenomicsToolReport",
    "GenomicsToolReportInput",
    "IlluminaIcaRequestInput",
    "ParagraphGenotypingInput",
    "ZippyPipelineInput",
    "build_genomics_tool_report",
    "prepare_expansionhunter_denovo",
    "prepare_gauchian_calling",
    "prepare_genomekit_query",
    "prepare_illumina_ica_request",
    "prepare_paragraph_genotyping",
    "prepare_zippy_pipeline",
]
