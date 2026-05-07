from __future__ import annotations

import json
from pathlib import Path

import pytest

from plato.paper_agents.scientific_verifier import (
    build_scientific_verification_report,
    scientific_verifier_node,
)


def _state(tmp_path: Path, *, methods: str, results: str) -> dict:
    project = tmp_path / "project"
    paper = project / "paper"
    artifacts = project / "input_files" / "analysis_artifacts"
    paper.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    (artifacts / "metrics.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    return {
        "files": {"Folder": str(project), "Paper_folder": str(paper)},
        "paper": {"Methods": methods, "Results": results},
    }


def test_scientific_verification_passes_when_provenance_is_present(tmp_path: Path):
    state = _state(
        tmp_path,
        methods=(
            "We used run_scientific_analysis with linear_regression and "
            "recorded reproducibility metadata, CSV outputs, and random seed 1729."
        ),
        results=(
            "The model achieved R^2=0.991329 and all validation checks passed. "
            "Artifact metadata were preserved in JSON and PNG outputs."
        ),
    )

    update = scientific_verifier_node(state)
    report = update["scientific_verification_report"]

    assert report["passed"] is True
    assert report["blocking_issues"] == []
    assert "linear_regression" in report["detected_operations"]
    assert (tmp_path / "project" / "paper" / "scientific_verification.json").exists()


def test_scientific_verification_blocks_quantitative_claims_without_provenance(
    tmp_path: Path,
):
    state = _state(
        tmp_path,
        methods="We fit a model.",
        results="The result was 0.991329 across 5 observations.",
    )

    report = build_scientific_verification_report(state)

    assert report.passed is False
    assert report.numeric_claim_count >= 2
    assert report.blocking_issues
    with pytest.raises(RuntimeError, match="Scientific verification failed"):
        scientific_verifier_node(state)


def test_scientific_verification_report_is_machine_readable(tmp_path: Path):
    state = _state(
        tmp_path,
        methods=(
            "run_scientific_analysis publication_plot reproducibility random seed 1729 CSV PNG"
        ),
        results="validation checks passed with value 1.23 and figure discussion.",
    )

    scientific_verifier_node(state)
    payload = json.loads(
        (tmp_path / "project" / "paper" / "scientific_verification.json").read_text(
            encoding="utf-8"
        )
    )

    assert payload["passed"] is True
    assert "artifact_inventory" in payload


def test_scientific_verification_accepts_executor_artifacts(tmp_path: Path):
    project = tmp_path / "project"
    paper = project / "paper"
    executor_artifacts = project / "plots" / "sklearn_synthetic"
    figure_artifacts = project / "input_files" / "plots"
    paper.mkdir(parents=True)
    executor_artifacts.mkdir(parents=True)
    figure_artifacts.mkdir(parents=True)
    (executor_artifacts / "synthetic_benchmark_metrics.csv").write_text(
        "model,roc_auc\nlogistic_regression,0.99\n",
        encoding="utf-8",
    )
    (figure_artifacts / "roc_auc_by_scenario.png").write_bytes(b"png")

    state = {
        "files": {"Folder": str(project), "Paper_folder": str(paper)},
        "paper": {
            "Methods": (
                "We ran a deterministic synthetic tabular benchmark with "
                "logistic regression and random forest classifiers using seed 1729."
            ),
            "Results": (
                "Validation checks passed. ROC-AUC was 0.99 and calibration "
                "figures were exported as PNG and CSV artifacts."
            ),
        },
    }

    report = build_scientific_verification_report(state)

    assert report.passed is True
    assert "sklearn_synthetic" in report.detected_operations
    assert "plots/sklearn_synthetic/synthetic_benchmark_metrics.csv" in report.artifact_inventory
    assert "input_files/plots/roc_auc_by_scenario.png" in report.artifact_inventory
