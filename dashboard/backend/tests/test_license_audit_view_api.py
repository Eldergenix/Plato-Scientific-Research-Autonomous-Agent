"""Tests for the license audit + SBOM viewer endpoints."""
from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# Mirror the bits of ``scripts.license_audit.DistInfo`` the view actually
# reads. Keeping a local stand-in lets the tests run on any branch — even
# one where ``scripts/license_audit.py`` hasn't been merged yet.
@dataclass
class _StubDist:
    name: str
    version: str
    license: str
    compatible: bool
    homepage: str | None = None
    license_source: str = "expression"
    license_snippet: str = ""
    compatibility_reason: str = ""
    classifiers: list[str] | None = None


def _install_stub_license_audit(monkeypatch, dists: list[_StubDist]) -> None:
    """Inject a fake ``scripts.license_audit`` module into ``sys.modules``.

    The view imports ``collect_distributions`` lazily inside the request
    handler, so patching ``sys.modules`` ahead of the request reliably
    redirects the import without touching the real script.
    """
    fake = types.ModuleType("scripts.license_audit")
    fake.collect_distributions = lambda: list(dists)  # type: ignore[attr-defined]
    fake.is_compatible_with_gpl3 = lambda s: (True, "stub")  # type: ignore[attr-defined]

    scripts_pkg = sys.modules.get("scripts")
    if scripts_pkg is None:
        scripts_pkg = types.ModuleType("scripts")
        scripts_pkg.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "scripts", scripts_pkg)
    monkeypatch.setitem(sys.modules, "scripts.license_audit", fake)


def _build_client(monkeypatch) -> TestClient:
    """Fresh TestClient with the license_audit_view router mounted.

    Cache is cleared between tests via the ``_clear_audit_cache`` fixture.
    The router is mounted under ``/api/v1`` to mirror what server.py would
    do once it includes it.
    """
    from plato_dashboard.api.license_audit_view import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_audit_cache() -> Iterator[None]:
    from plato_dashboard.api import license_audit_view

    license_audit_view._reset_cache()
    yield
    license_audit_view._reset_cache()


def test_license_audit_returns_expected_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    dists = [
        _StubDist("requests", "2.31.0", "Apache-2.0", True, "https://requests.example"),
        _StubDist("foo-proprietary", "1.0", "Proprietary", False, None),
        _StubDist("mystery", "0.0", "UNKNOWN", False, None),
        _StubDist("rich", "13.0", "MIT", True, "https://rich.example"),
    ]
    _install_stub_license_audit(monkeypatch, dists)
    client = _build_client(monkeypatch)

    resp = client.get("/api/v1/license_audit")
    assert resp.status_code == 200
    body = resp.json()

    assert body["summary"] == {
        "total": 4,
        "compatible": 2,
        "incompatible": 1,
        "unknown": 1,
    }

    licenses = {b["license"] for b in body["by_license"]}
    assert {"Apache-2.0", "MIT", "Proprietary", "UNKNOWN"} <= licenses

    by_name = {d["name"]: d for d in body["distributions"]}
    assert by_name["requests"]["gpl3_compatible"] is True
    assert by_name["requests"]["source_url"] == "https://requests.example"
    assert by_name["foo-proprietary"]["gpl3_compatible"] is False
    # UNKNOWN gets normalised to null in the per-row license field so the
    # frontend can render a distinct "?" badge.
    assert by_name["mystery"]["license"] is None


def test_license_audit_caches_for_five_minutes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Second GET inside the TTL must NOT re-invoke ``collect_distributions``."""
    call_count = {"n": 0}

    def _spy() -> list[_StubDist]:
        call_count["n"] += 1
        return [_StubDist("rich", "13.0", "MIT", True, None)]

    fake = types.ModuleType("scripts.license_audit")
    fake.collect_distributions = _spy  # type: ignore[attr-defined]
    if "scripts" not in sys.modules:
        scripts_pkg = types.ModuleType("scripts")
        scripts_pkg.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "scripts", scripts_pkg)
    monkeypatch.setitem(sys.modules, "scripts.license_audit", fake)

    client = _build_client(monkeypatch)

    r1 = client.get("/api/v1/license_audit")
    r2 = client.get("/api/v1/license_audit")
    r3 = client.get("/api/v1/license_audit")
    assert r1.status_code == r2.status_code == r3.status_code == 200
    assert r1.json() == r2.json() == r3.json()
    assert call_count["n"] == 1, "expected the audit to be computed exactly once"


def test_license_audit_500_when_script_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force the import to fail by replacing the module entry with one that
    # raises on attribute access.
    broken = types.ModuleType("scripts.license_audit")

    def _missing() -> None:
        raise ImportError("collect_distributions vanished")

    # The view does ``from scripts.license_audit import collect_distributions``;
    # that raises ImportError if the attribute isn't present.
    monkeypatch.setitem(sys.modules, "scripts.license_audit", broken)
    if "scripts" not in sys.modules:
        scripts_pkg = types.ModuleType("scripts")
        scripts_pkg.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "scripts", scripts_pkg)

    client = _build_client(monkeypatch)
    resp = client.get("/api/v1/license_audit")
    assert resp.status_code == 500
    assert resp.json()["detail"]["error"] == "license_audit script not available"


def test_sbom_returns_prebuilt_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If ``<repo>/sbom.json`` exists, return its parsed contents verbatim."""
    fake_sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "components": [{"name": "rich", "version": "13.0"}],
    }
    sbom_path = tmp_path / "sbom.json"
    sbom_path.write_text(json.dumps(fake_sbom))

    from plato_dashboard.api import license_audit_view

    monkeypatch.setattr(license_audit_view, "_repo_root", lambda: tmp_path)
    client = _build_client(monkeypatch)

    resp = client.get("/api/v1/sbom")
    assert resp.status_code == 200
    assert resp.json() == fake_sbom


def test_sbom_503_when_neither_prebuilt_nor_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No sbom.json and no scripts/generate_sbom.py → 503 with hint."""
    from plato_dashboard.api import license_audit_view

    monkeypatch.setattr(license_audit_view, "_repo_root", lambda: tmp_path)
    client = _build_client(monkeypatch)

    resp = client.get("/api/v1/sbom")
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert detail["error"] == "sbom_unavailable"


def test_sbom_503_when_generator_exits_with_missing_dependency(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Subprocess returncode=2 (cyclonedx-bom not installed) → 503 with install hint."""
    from plato_dashboard.api import license_audit_view

    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    # A script that just exits with code 2 emulates the "cyclonedx-bom not
    # installed" path in scripts/generate_sbom.py.
    (scripts_dir / "generate_sbom.py").write_text(
        "import sys; sys.stderr.write('cyclonedx-bom missing\\n'); sys.exit(2)\n"
    )

    monkeypatch.setattr(license_audit_view, "_repo_root", lambda: tmp_path)
    client = _build_client(monkeypatch)

    resp = client.get("/api/v1/sbom")
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert detail["error"] == "sbom_generation_failed"
    assert "cyclonedx-bom" in detail.get("hint", "")
