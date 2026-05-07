from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional, cast

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from .parameters import GraphState


_OPERATION_ALIASES = {
    "formula_mass": ("formula_mass", "formula mass"),
    "harmonic_oscillator": ("harmonic_oscillator", "harmonic oscillator"),
    "linear_regression": ("linear_regression", "linear regression"),
    "logistic_regression": (
        "logistic_regression",
        "logistic regression",
        "regularized logistic",
    ),
    "random_forest": ("random forest", "random forests"),
    "sklearn_synthetic": (
        "sklearn_synthetic",
        "synthetic tabular",
        "synthetic-tabular",
        "deterministic synthetic",
    ),
    "single_cell_qc": ("single_cell_qc", "single-cell qc", "single cell qc"),
    "quantum_pauli": ("quantum_pauli", "quantum pauli", "pauli"),
    "publication_plot": ("publication_plot", "publication plot"),
}

_PROVENANCE_MARKERS = {
    "run_scientific_analysis",
    "validation",
    "random seed",
    "input sha-256",
    "reproducibility",
    "seed",
    "cross-validation",
    "csv",
    "json",
    "png",
    "html",
}

_NUMERIC_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:\d+\.\d+|\d+)(?:e[+-]?\d+)?(?![A-Za-z])",
    re.IGNORECASE,
)


class ScientificVerificationReport(BaseModel):
    passed: bool
    numeric_claim_count: int
    detected_operations: list[str] = Field(default_factory=list)
    provenance_markers: list[str] = Field(default_factory=list)
    artifact_inventory: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def scientific_verifier_node(
    state: GraphState,
    config: Optional[RunnableConfig] = None,  # noqa: ARG001 - LangGraph node signature
) -> dict[str, Any]:
    report = build_scientific_verification_report(state)
    _write_report(state, report)
    if report.blocking_issues:
        issues = "; ".join(report.blocking_issues)
        raise RuntimeError(f"Scientific verification failed: {issues}")
    return {"scientific_verification_report": report.model_dump(mode="json")}


def build_scientific_verification_report(
    state: GraphState,
) -> ScientificVerificationReport:
    paper = dict(cast(Any, state.get("paper")) or {})
    methods = str(paper.get("Methods") or "")
    results = str(paper.get("Results") or "")
    combined = f"{methods}\n{results}"
    combined_lower = combined.lower()

    detected_operations = sorted(
        name
        for name, aliases in _OPERATION_ALIASES.items()
        if any(alias in combined_lower for alias in aliases)
    )
    provenance_markers = sorted(
        marker for marker in _PROVENANCE_MARKERS if marker in combined_lower
    )
    artifact_inventory = _artifact_inventory(state)
    required_operations = _required_operations_from_artifacts(artifact_inventory)
    numeric_claim_count = len(_NUMERIC_PATTERN.findall(results))

    blocking_issues: list[str] = []
    warnings: list[str] = []

    if artifact_inventory and not detected_operations:
        blocking_issues.append(
            "analysis artifacts exist but Methods/Results do not name any scientific-analysis operations"
        )
    missing_operations = sorted(set(required_operations) - set(detected_operations))
    if missing_operations:
        blocking_issues.append(
            "analysis artifacts were found for operations not described in Methods/Results: "
            + ", ".join(missing_operations)
        )
    if artifact_inventory and not provenance_markers:
        blocking_issues.append(
            "analysis artifacts exist but Methods/Results do not mention reproducibility or artifact metadata"
        )
    if numeric_claim_count > 0 and not artifact_inventory:
        blocking_issues.append(
            "Results contain quantitative claims but no analysis artifacts were found"
        )
    if numeric_claim_count > 0 and "validation" not in combined_lower:
        blocking_issues.append(
            "Results contain quantitative claims but do not report validation checks"
        )
    if "publication_plot" in detected_operations and "figure" not in results.lower():
        warnings.append(
            "publication_plot was referenced but Results do not appear to discuss a figure"
        )
    if numeric_claim_count > 0 and "random seed" not in combined_lower:
        warnings.append(
            "quantitative content is present without an explicit random-seed statement"
        )

    return ScientificVerificationReport(
        passed=not blocking_issues,
        numeric_claim_count=numeric_claim_count,
        detected_operations=detected_operations,
        provenance_markers=provenance_markers,
        artifact_inventory=artifact_inventory,
        blocking_issues=blocking_issues,
        warnings=warnings,
    )


def _artifact_inventory(state: GraphState) -> list[str]:
    files = dict(cast(Any, state.get("files")) or {})
    folder = files.get("Folder")
    if not folder:
        return []
    project_root = Path(folder)
    roots = (
        project_root / "input_files" / "analysis_artifacts",
        project_root / "plots",
        project_root / "input_files" / "plots",
    )
    suffixes = {".csv", ".json", ".png", ".svg", ".pdf", ".html"}
    artifacts: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        artifacts.extend(
            str(path.relative_to(project_root))
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in suffixes
        )
    return sorted(artifacts)


def _required_operations_from_artifacts(artifact_inventory: list[str]) -> list[str]:
    required: set[str] = set()
    for artifact in artifact_inventory:
        match = re.search(
            r"analysis_artifacts/([a-z0-9_]+?)_[0-9a-f]{10}/",
            artifact,
        )
        if match:
            required.add(match.group(1))
        if artifact.startswith("plots/sklearn_synthetic/"):
            required.add("sklearn_synthetic")
    return sorted(required)


def _write_report(state: GraphState, report: ScientificVerificationReport) -> None:
    files = dict(cast(Any, state.get("files")) or {})
    paper_folder = files.get("Paper_folder")
    if not paper_folder:
        return
    target = Path(paper_folder) / "scientific_verification.json"
    target.write_text(report.model_dump_json(indent=2), encoding="utf-8")


__all__ = [
    "ScientificVerificationReport",
    "build_scientific_verification_report",
    "scientific_verifier_node",
]
