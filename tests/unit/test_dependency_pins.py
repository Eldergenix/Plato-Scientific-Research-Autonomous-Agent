from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AIOSQLITE_PIN = "aiosqlite>=0.22,<0.23"
MISTRALAI_V1_PIN = "mistralai>=1.12.4,<1.13"
CMBAGENT_AUTOGEN_PIN = "cmbagent-autogen>=0.0.91.post11,<0.0.92"
FUTUREHOUSE_CLIENT_PIN = "futurehouse-client>=0.7.1,<0.8"
LDP_PIN = "ldp>=0.46.0,<0.47"
FHLMI_PIN = "fhlmi>=0.43.1,<0.44"
CERTIFI_PIN = "certifi>=2026.4.22,<2027"
REQUESTS_PIN = "requests>=2.34.2,<3"
URLLIB3_PIN = "urllib3>=2.7,<3"
UUID_UTILS_PIN = "uuid-utils>=0.16,<0.17"


def test_mistralai_stays_on_v1_for_cmbagent_imports() -> None:
    """cmbagent still imports SDK v1 symbols from the mistralai top level."""

    root_dependencies = _dependencies(ROOT / "pyproject.toml")
    backend_dependencies = _dependencies(ROOT / "dashboard/backend/pyproject.toml")

    assert MISTRALAI_V1_PIN in root_dependencies
    assert MISTRALAI_V1_PIN in backend_dependencies


def test_legacy_app_extra_is_resolver_safe() -> None:
    """The legacy PlatoApp package is not published on PyPI."""

    optional_dependencies = tomllib.loads((ROOT / "pyproject.toml").read_text())[
        "project"
    ]["optional-dependencies"]

    assert optional_dependencies["app"] == []


def test_futurehouse_dependency_chain_stays_bounded_for_docker_builds() -> None:
    """Unbounded FutureHouse transitive deps trigger pip resolver backtracking."""

    root_dependencies = _dependencies(ROOT / "pyproject.toml")

    assert AIOSQLITE_PIN in root_dependencies
    assert CMBAGENT_AUTOGEN_PIN in root_dependencies
    assert FUTUREHOUSE_CLIENT_PIN in root_dependencies
    assert LDP_PIN in root_dependencies
    assert FHLMI_PIN in root_dependencies
    assert CERTIFI_PIN in root_dependencies
    assert REQUESTS_PIN in root_dependencies
    assert URLLIB3_PIN in root_dependencies
    assert UUID_UTILS_PIN in root_dependencies


def _dependencies(path: Path) -> list[str]:
    return tomllib.loads(path.read_text())["project"]["dependencies"]
