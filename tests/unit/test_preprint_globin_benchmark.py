from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "preprint"
    / "experiments"
    / "run_globin_structure_benchmark.py"
)


def load_benchmark_module():
    spec = importlib.util.spec_from_file_location("globin_benchmark", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_kabsch_align_recovers_rigid_rotation_and_translation() -> None:
    benchmark = load_benchmark_module()
    moving = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    rotation = np.array(
        [
            [0.0, -1.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    fixed = moving @ rotation + np.array([4.0, -2.0, 7.0])

    aligned = benchmark.kabsch_align(moving, fixed)

    assert np.allclose(aligned, fixed, atol=1e-12)


def test_kabsch_apply_uses_core_fit_for_all_coordinates() -> None:
    benchmark = load_benchmark_module()
    moving = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [9.0, 9.0, 9.0]]
    )
    rotation = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    fixed = moving @ rotation + np.array([4.0, -2.0, 7.0])

    aligned = benchmark.kabsch_apply(moving[:3], fixed[:3], moving)

    assert np.allclose(aligned, fixed, atol=1e-12)


def test_parse_experimental_metadata_handles_xray_and_nmr(tmp_path: Path) -> None:
    benchmark = load_benchmark_module()
    xray = tmp_path / "xray.pdb"
    xray.write_text(
        "EXPDTA    X-RAY DIFFRACTION\n"
        "REMARK   2 RESOLUTION.    1.80 ANGSTROMS.\n"
        "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 50.00\n"
    )
    nmr = tmp_path / "nmr.pdb"
    nmr.write_text("EXPDTA    SOLUTION NMR\nREMARK   2 RESOLUTION. NOT APPLICABLE.\n")

    assert benchmark.parse_experimental_metadata(xray) == (
        "x-ray diffraction",
        1.8,
    )
    assert benchmark.parse_experimental_metadata(nmr) == ("solution nmr", None)


def test_moving_block_bootstrap_rmsd_is_deterministic() -> None:
    benchmark = load_benchmark_module()
    distances = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])

    first = benchmark.moving_block_bootstrap_rmsd_ci(
        distances,
        replicates=500,
        block_size=2,
        seed=42,
    )
    second = benchmark.moving_block_bootstrap_rmsd_ci(
        distances,
        replicates=500,
        block_size=2,
        seed=42,
    )

    assert first == second
    assert 0.0 < first[0] < first[1] < 1.0


def test_detect_discrepancy_regions_groups_adjacent_residues() -> None:
    benchmark = load_benchmark_module()
    rows = [
        {
            "target": "demo",
            "uniprot": "P00001",
            "pdb_id": "1ABC",
            "experimental_chain": "A",
            "alphafold_residue_number": number,
            "plddt": plddt,
            "ca_error_angstrom": error,
        }
        for number, plddt, error in [
            (10, 95.0, 2.5),
            (11, 94.0, 3.0),
            (12, 80.0, 4.0),
            (20, 99.0, 2.1),
        ]
    ]

    candidates = benchmark.detect_discrepancy_regions(rows)

    assert [candidate["candidate_id"] for candidate in candidates] == [
        "demo:10-11",
        "demo:20-20",
    ]
    assert candidates[0]["candidate_status"] == "regional_hypothesis_candidate"
    assert candidates[0]["novelty_status"] == "not_established"


def test_load_panel_rejects_duplicate_targets(tmp_path: Path) -> None:
    benchmark = load_benchmark_module()
    panel = tmp_path / "panel.json"
    panel.write_text(
        """[
          {"target":"same","uniprot":"P1","pdb_id":"1ABC","chain":"A"},
          {"target":"same","uniprot":"P2","pdb_id":"2ABC","chain":"A"}
        ]"""
    )

    with pytest.raises(ValueError, match="Duplicate panel target"):
        benchmark.load_panel(panel)
