"""Tests for pinned biomedical benchmark catalog ingestion."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from evals.biomedical_benchmarks import (
    COMPBIOBENCH_V1,
    parse_compbiobench_tsv,
    summarize_tasks,
    validate_payload,
)


HEADER = (
    "question_id\tcurator_name\tdomain\tquestion_style\tskills_tested\t"
    "question\tinternet_required\tgpu_preferred\tfile_paths\n"
)


def _payload() -> bytes:
    return (
        HEADER + "gene-q1\tAB\tGenomics\tRetrieval\tAPI/Web Fetching, Reasoning\t"
        "Resolve this gene identifier.\tTrue\tFalse\t\n"
        + "rna-q1\tCD\tSingle-cell\tRoutine Analysis\tCoding, Reasoning\t"
        "Identify the depleted cell type.\tFalse\tTrue\tcounts.tsv, genes.txt\n"
    ).encode()


def test_parse_compbiobench_tsv_normalizes_lists_and_booleans():
    tasks = parse_compbiobench_tsv(_payload())

    assert [task.question_id for task in tasks] == ["gene-q1", "rna-q1"]
    assert tasks[0].skills_tested == ("API/Web Fetching", "Reasoning")
    assert tasks[0].internet_required is True
    assert tasks[1].gpu_preferred is True
    assert tasks[1].file_paths == ("counts.tsv", "genes.txt")


def test_parse_compbiobench_tsv_rejects_duplicate_ids():
    duplicate = (
        _payload()
        + (
            "gene-q1\tEF\tGenomics\tRetrieval\tReasoning\tDuplicate.\tFalse\tFalse\t\n"
        ).encode()
    )

    with pytest.raises(ValueError, match="Duplicate CompBioBench question_id"):
        parse_compbiobench_tsv(duplicate)


def test_validate_payload_rejects_source_drift():
    payload = _payload()
    pinned = replace(
        COMPBIOBENCH_V1,
        sha256=hashlib.sha256(payload).hexdigest(),
    )

    assert validate_payload(payload, pinned) == pinned.sha256
    with pytest.raises(ValueError, match="payload hash mismatch"):
        validate_payload(payload + b"drift", pinned)


def test_summarize_tasks_reports_coverage_not_performance():
    summary = summarize_tasks(parse_compbiobench_tsv(_payload()))

    assert summary["task_count"] == 2
    assert summary["domain_counts"] == {"Genomics": 1, "Single-cell": 1}
    assert summary["internet_required_count"] == 1
    assert summary["gpu_preferred_count"] == 1
    assert summary["tasks_with_files_count"] == 1
