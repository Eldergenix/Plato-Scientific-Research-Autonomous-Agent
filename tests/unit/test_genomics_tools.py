from __future__ import annotations

import stat
from pathlib import Path

import pytest

from plato.tools import call, get, list_tools
from plato.tools.builtin import (
    ExpansionHunterDenovoInput,
    GauchianCallingInput,
    GenomeKitQueryInput,
    GenomicsToolReportInput,
    IlluminaIcaRequestInput,
    ParagraphGenotypingInput,
    ZippyPipelineInput,
)


def test_genomics_tools_are_registered_as_options():
    names = set(list_tools(category="genomics"))

    assert {
        "genomics_tool_report",
        "prepare_genomekit_query",
        "prepare_zippy_pipeline",
        "prepare_paragraph_genotyping",
        "prepare_expansionhunter_denovo",
        "prepare_gauchian_calling",
        "prepare_illumina_ica_request",
    }.issubset(names)
    assert get("prepare_illumina_ica_request").metadata.permissions == {"network"}


def test_genomics_tool_report_reviews_each_requested_illumina_tool():
    report = call("genomics_tool_report", GenomicsToolReportInput())
    tool_names = {capability.name for capability in report.capabilities}

    assert {
        "GenomeKit",
        "ZIPPY",
        "Paragraph",
        "ExpansionHunter Denovo",
        "Gauchian",
        "ica-sdk-python",
    } == tool_names
    assert report.fingerprint
    assert all(capability.expected_artifacts for capability in report.capabilities)


def test_genomekit_query_prepares_lazy_sequence_command():
    result = call(
        "prepare_genomekit_query",
        GenomeKitQueryInput(
            operation="sequence",
            genome="hg38",
            chrom="chr7",
            start=117120016,
            end=117120201,
        ),
        allowed_permissions={"filesystem_read", "code_exec"},
    )

    assert result.tool == "GenomeKit"
    assert result.operation == "sequence"
    assert result.command[1] == "-c"
    assert "import genome_kit as gk" in result.command[2]
    assert "GenomeKit may fetch remote resource files" in result.warnings[0]


def test_genomekit_variant_sequence_requires_variants():
    result = call(
        "prepare_genomekit_query",
        GenomeKitQueryInput(
            operation="variant_sequence",
            genome="hg19",
            chrom="chr7",
            start=117120016,
            end=117120201,
        ),
        allowed_permissions={"filesystem_read", "code_exec"},
    )

    assert result.status == "missing_requirements"
    assert "variants" in result.missing_requirements


def test_genomekit_is_exposed_through_mcp_genomics_alias():
    pytest.importorskip("mcp")
    from plato.tools.mcp_server import _genomics_tool_mapping

    registry_name, schema, permissions = _genomics_tool_mapping("genomekit")

    assert registry_name == "prepare_genomekit_query"
    assert schema is GenomeKitQueryInput
    assert permissions == {"filesystem_read", "code_exec"}


def test_zippy_make_params_builds_external_python27_command(tmp_path: Path):
    proto = tmp_path / "proto.json"
    proto.write_text('{"stages": ["bwa"]}', encoding="utf-8")
    params = tmp_path / "params.json"

    result = call(
        "prepare_zippy_pipeline",
        ZippyPipelineInput(
            operation="make_params",
            proto_workflow_path=str(proto),
            params_path=str(params),
            python_executable="/usr/bin/python2.7",
        ),
        allowed_permissions={"filesystem_read", "filesystem_write", "code_exec"},
    )

    assert result.tool == "ZIPPY"
    assert result.status == "missing_requirements"
    assert "zippy.make_params" in result.command
    assert str(params) in result.expected_artifacts


def test_paragraph_command_captures_required_wgs_inputs(tmp_path: Path):
    variants = tmp_path / "candidates.vcf"
    manifest = tmp_path / "samples.tsv"
    reference = tmp_path / "reference.fa"
    script = tmp_path / "multigrmpy.py"
    for path in [variants, manifest, reference, script]:
        path.write_text("", encoding="utf-8")

    result = call(
        "prepare_paragraph_genotyping",
        ParagraphGenotypingInput(
            variants_path=str(variants),
            manifest_path=str(manifest),
            reference_fasta=str(reference),
            executable=str(script),
            output_dir=str(tmp_path / "paragraph_out"),
        ),
        allowed_permissions={"filesystem_read", "filesystem_write", "code_exec"},
    )

    assert result.status == "ready"
    assert "-i" in result.command
    assert str(variants) in result.command
    assert any(path.endswith("genotypes.vcf.gz") for path in result.expected_artifacts)


def test_expansionhunter_denovo_profile_command_records_mapq_thresholds(tmp_path: Path):
    binary = tmp_path / "ExpansionHunterDenovo"
    reads = tmp_path / "sample.bam"
    reference = tmp_path / "reference.fa"
    for path in [binary, reads, reference]:
        path.write_text("", encoding="utf-8")

    result = call(
        "prepare_expansionhunter_denovo",
        ExpansionHunterDenovoInput(
            operation="profile",
            executable=str(binary),
            reads_path=str(reads),
            reference_fasta=str(reference),
            output_prefix=str(tmp_path / "sample"),
            min_anchor_mapq=45,
            max_irr_mapq=35,
        ),
        allowed_permissions={"filesystem_read", "filesystem_write", "code_exec"},
    )

    assert result.status == "ready"
    assert result.command[:2] == [str(binary), "profile"]
    assert "--min-anchor-mapq" in result.command
    assert "de novo STR expansion discovery" in result.scientific_scope


def test_gauchian_can_execute_when_binary_is_configured(tmp_path: Path):
    script = tmp_path / "fake-gauchian"
    script.write_text("#!/bin/sh\necho gauchian-ok\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    manifest = tmp_path / "manifest.txt"
    manifest.write_text("/tmp/sample.bam\n", encoding="utf-8")

    result = call(
        "prepare_gauchian_calling",
        GauchianCallingInput(
            executable=str(script),
            manifest_path=str(manifest),
            genome="38",
            output_dir=str(tmp_path / "out"),
            execute=True,
        ),
        allowed_permissions={"filesystem_read", "filesystem_write", "code_exec"},
    )

    assert result.status == "executed"
    assert result.execution is not None
    assert result.execution.returncode == 0
    assert "gauchian-ok" in result.execution.stdout


def test_ica_request_never_echoes_secret_values(monkeypatch):
    monkeypatch.setenv("PLATO_ICA_API_KEY", "secret-api-key")
    monkeypatch.setenv("PLATO_ICA_JWT", "secret-jwt")

    result = call(
        "prepare_illumina_ica_request",
        IlluminaIcaRequestInput(operation="get_projects"),
        allowed_permissions={"network"},
    )

    dumped = result.model_dump_json()
    assert result.status == "ready"
    assert "secret-api-key" not in dumped
    assert "secret-jwt" not in dumped
    assert result.request["headers"]["X-API-Key"] == "<redacted>"


def test_ica_token_reports_missing_auth_without_environment(monkeypatch):
    for name in ["PLATO_ICA_API_KEY", "PLATO_ICA_BASIC_AUTH", "PLATO_ICA_JWT"]:
        monkeypatch.delenv(name, raising=False)

    result = call(
        "prepare_illumina_ica_request",
        IlluminaIcaRequestInput(operation="token"),
        allowed_permissions={"network"},
    )

    assert result.status == "missing_requirements"
    assert "PLATO_ICA_API_KEY or PLATO_ICA_BASIC_AUTH" in result.missing_requirements
