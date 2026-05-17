from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MISTRALAI_V1_PIN = "mistralai>=1.0,<2.0"


def test_mistralai_stays_on_v1_for_cmbagent_imports() -> None:
    """cmbagent still imports SDK v1 symbols from the mistralai top level."""

    root_dependencies = _dependencies(ROOT / "pyproject.toml")
    backend_dependencies = _dependencies(ROOT / "dashboard/backend/pyproject.toml")

    assert MISTRALAI_V1_PIN in root_dependencies
    assert MISTRALAI_V1_PIN in backend_dependencies


def _dependencies(path: Path) -> list[str]:
    return tomllib.loads(path.read_text())["project"]["dependencies"]
