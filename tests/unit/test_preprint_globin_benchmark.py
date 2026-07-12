from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np


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
