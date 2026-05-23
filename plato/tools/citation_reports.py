"""Structured validation reports for citation verification runs."""

from __future__ import annotations

from typing import Any

from plato.state.models import Source, ValidationResult


STRICT_ACCURACY_THRESHOLD = 0.9999


def result_passes(result: ValidationResult) -> bool:
    return result.status in {"verified", "warning"} and result.verdict != "LIKELY"


def build_validation_report(
    run_id: str,
    sources: list[Source],
    results: list[ValidationResult],
    *,
    threshold: float = STRICT_ACCURACY_THRESHOLD,
) -> dict[str, Any]:
    total = len(sources)
    passed = sum(1 for result in results if result_passes(result))
    likely_hallucinations = sum(1 for result in results if result.verdict == "LIKELY")
    failures = [
        _failure_payload(source, result)
        for source, result in zip(sources, results, strict=True)
        if not result_passes(result)
    ]
    warnings = [
        _warning_payload(source, result)
        for source, result in zip(sources, results, strict=True)
        if result_passes(result) and result.warnings
    ]
    validation_rate = passed / total if total else 0.0
    gate_passed = (
        total > 0 and validation_rate >= threshold and likely_hallucinations == 0
    )
    return {
        "run_id": run_id,
        "validation_rate": validation_rate,
        "total": total,
        "passed": passed,
        "total_references": total,
        "verified_references": passed,
        "unverified_count": total - passed,
        "likely_hallucinations": likely_hallucinations,
        "accuracy_gate": {
            "threshold": threshold,
            "passed": gate_passed,
            "reason": None
            if gate_passed
            else "reference accuracy below 99.99% or hallucination candidates remain",
        },
        "failures": failures,
        "warnings": warnings,
        "references": [
            _reference_payload(source, result)
            for source, result in zip(sources, results, strict=True)
        ],
    }


def _failure_payload(source: Source, result: ValidationResult) -> dict[str, Any]:
    first_issue = result.issues[0] if result.issues else {}
    return {
        "source_id": source.id,
        "doi": source.doi,
        "arxiv_id": source.arxiv_id,
        "title": source.title,
        "reason": first_issue.get("type") or result.status,
        "detail": first_issue.get("detail") or result.error,
        "error": result.error,
        "source_type": source.retrieved_via,
        "verdict": result.verdict,
        "confidence": result.confidence,
        "hallucination_assessment": result.hallucination_assessment,
        "corrections": result.corrections,
        "tags": result.tags,
        "folder": result.folder,
        "notes": result.notes,
        "issues": result.issues,
    }


def _warning_payload(source: Source, result: ValidationResult) -> dict[str, Any]:
    return {
        "source_id": source.id,
        "title": source.title,
        "warnings": result.warnings,
        "tags": result.tags,
        "folder": result.folder,
        "notes": result.notes,
    }


def _reference_payload(source: Source, result: ValidationResult) -> dict[str, Any]:
    return {
        "source_id": source.id,
        "title": source.title,
        "authors": source.authors,
        "year": source.year,
        "doi": source.doi,
        "arxiv_id": source.arxiv_id,
        "status": result.status,
        "verdict": result.verdict,
        "matched_source": result.matched_source,
        "matched_metadata": result.matched_metadata,
        "issues": result.issues,
        "warnings": result.warnings,
        "corrections": result.corrections,
        "tags": result.tags,
        "folder": result.folder,
        "notes": result.notes,
    }
