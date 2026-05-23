from __future__ import annotations

from pathlib import Path

import pytest

from plato.tools import call, get, list_tools
from plato.tools.builtin import ScientificAnalysisInput
from plato.tools.scientific_analysis import ScientificOperation


@pytest.mark.parametrize(
    ("operation", "data", "required_values"),
    [
        ("formula_mass", {"formula": "C6H12O6"}, {"molar_mass_g_mol"}),
        (
            "harmonic_oscillator",
            {
                "mass": 2.0,
                "spring_constant": 8.0,
                "x0": 1.0,
                "v0": 0.0,
                "duration": 2.0,
                "points": 80,
            },
            {"omega_rad_s", "period", "max_abs_energy_drift"},
        ),
        (
            "linear_regression",
            {"x": [0, 1, 2, 3], "y": [1.0, 2.0, 2.9, 4.1]},
            {"r_squared", "n_observations"},
        ),
        (
            "single_cell_qc",
            {
                "matrix": [[3, 0, 2], [0, 5, 1], [7, 1, 0]],
                "gene_names": ["MT-CO1", "ACTB", "GAPDH"],
            },
            {"n_cells", "n_genes", "scanpy_available"},
        ),
        ("quantum_pauli", {"pauli": "Z", "state": [1, 0]}, {"operator", "expectation"}),
        (
            "publication_plot",
            {"x": [0, 1, 2], "y": [0.0, 0.5, 2.0], "title": "Calibration"},
            {"n_points", "chart_type"},
        ),
    ],
)
def test_scientific_analysis_operations_emit_publication_artifacts(
    tmp_path: Path,
    operation: ScientificOperation,
    data: dict[str, object],
    required_values: set[str],
):
    result = call(
        "run_scientific_analysis",
        ScientificAnalysisInput(
            operation=operation,
            data=data,
            output_dir=str(tmp_path),
        ),
        allowed_permissions={"filesystem_write"},
    )

    assert result.markdown
    assert result.latex
    assert result.reproducibility["operation"] == operation
    assert result.reproducibility["input_sha256"]
    assert required_values.issubset(result.values)
    assert result.checks
    assert all(check["passed"] for check in result.checks)
    assert result.artifacts

    for artifact in result.artifacts:
        path = Path(artifact.path)
        assert path.exists()
        assert path.stat().st_size > 0


def test_scientific_analysis_tool_registered_with_filesystem_permission():
    names = set(list_tools(category="scientific_analysis"))

    assert "run_scientific_analysis" in names
    assert "scientific_capability_report" in names
    assert get("run_scientific_analysis").metadata.permissions == {"filesystem_write"}
