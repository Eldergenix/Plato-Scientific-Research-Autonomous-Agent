"""Tests for the CI gate scripts in .github/scripts."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tomllib
from datetime import date
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / ".github" / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = _load("pip_audit_gate")

TODAY = date(2026, 11, 19)


def _report(*vulns: tuple[str, str, list[str]]) -> dict:
    deps: dict[str, dict] = {}
    for package, vuln_id, aliases in vulns:
        dep = deps.setdefault(package, {"name": package, "version": "1.0", "vulns": []})
        dep["vulns"].append(
            {"id": vuln_id, "aliases": aliases, "fix_versions": ["2.0"]}
        )
    return {
        "dependencies": [*deps.values(), {"name": "plato", "skip_reason": "editable"}]
    }


def _allowlist(*entries: dict, review_by: str = "2027-01-01") -> dict:
    return {
        "review_by": review_by,
        "blockers": {"pin": "held back by an upstream pin"},
        "finding": list(entries),
    }


def _entry(package: str, vuln_id: str, **extra) -> dict:
    return {
        "package": package,
        "id": vuln_id,
        "blocked_by": "pin",
        "reason": "unreachable",
        **extra,
    }


def _errors(report: dict, allowlist: dict) -> list[str]:
    findings, _ = gate.parse_report(report)
    return gate.evaluate(findings, allowlist, TODAY)


def test_listed_finding_passes() -> None:
    assert (
        _errors(_report(("pkg", "PYSEC-1", [])), _allowlist(_entry("pkg", "PYSEC-1")))
        == []
    )


def test_unlisted_finding_fails() -> None:
    errors = _errors(
        _report(("pkg", "PYSEC-1", []), ("pkg", "PYSEC-2", [])),
        _allowlist(_entry("pkg", "PYSEC-1")),
    )
    assert len(errors) == 1 and errors[0].startswith("new finding: pkg 1.0 PYSEC-2")


def test_alias_matches_but_only_for_the_same_package() -> None:
    allow = _allowlist(_entry("pkg", "CVE-2026-1"))
    assert _errors(_report(("pkg", "PYSEC-1", ["CVE-2026-1"])), allow) == []
    other = _errors(_report(("other", "PYSEC-1", ["CVE-2026-1"])), allow)
    assert any(e.startswith("new finding: other") for e in other)
    assert any(e.startswith("stale allowlist entry: pkg") for e in other)


def test_package_names_are_normalised() -> None:
    assert (
        _errors(
            _report(("Lang_Graph", "PYSEC-1", [])),
            _allowlist(_entry("lang-graph", "PYSEC-1")),
        )
        == []
    )


def test_exact_id_wins_over_shared_alias() -> None:
    # Two OSV records for one advisory, each listing the other as an alias.
    report = _report(
        ("pkg", "PYSEC-1", ["PYSEC-2", "CVE-9"]), ("pkg", "PYSEC-2", ["CVE-9"])
    )
    allow = _allowlist(_entry("pkg", "PYSEC-1"), _entry("pkg", "PYSEC-2"))
    assert _errors(report, allow) == []


def test_stale_entry_fails() -> None:
    errors = _errors(_report(), _allowlist(_entry("pkg", "PYSEC-1")))
    assert errors == [
        "stale allowlist entry: pkg PYSEC-1 is no longer reported; delete it"
    ]


def test_expired_review_date_fails() -> None:
    errors = _errors(
        _report(("pkg", "PYSEC-1", [])),
        _allowlist(_entry("pkg", "PYSEC-1"), review_by="2026-11-18"),
    )
    assert len(errors) == 1 and "review_by 2026-11-18 has passed" in errors[0]


def test_entry_needs_reason_and_known_blocker() -> None:
    bad = _entry("pkg", "PYSEC-1", reason=" ", blocked_by="nope")
    errors = _errors(_report(("pkg", "PYSEC-1", [])), _allowlist(bad))
    assert any("reason is required" in e for e in errors)
    assert any("blocked_by must name" in e for e in errors)


def test_skipped_dependencies_are_reported_not_audited() -> None:
    findings, skipped = gate.parse_report(_report(("pkg", "PYSEC-1", [])))
    assert [f.id for f in findings] == ["PYSEC-1"]
    assert skipped == ["plato: editable"]


def test_checked_in_allowlist_is_well_formed() -> None:
    allowlist = tomllib.loads(
        (ROOT / ".github" / "pip-audit-allowlist.toml").read_text()
    )
    entries = allowlist["finding"]
    # Feed back exactly the listed findings: only structural problems can remain.
    report = _report(*[(e["package"], e["id"], e.get("aliases", [])) for e in entries])
    findings, _ = gate.parse_report(report)
    assert gate.evaluate(findings, allowlist, date(2026, 11, 19)) == []
    keys = [(e["package"], e["id"]) for e in entries]
    assert len(keys) == len(set(keys)), "duplicate allowlist entries"


def test_gate_cli_reads_a_saved_report(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(
        '{"dependencies": [{"name": "pkg", "version": "1.0", "vulns": [{"id": "PYSEC-9", "aliases": [], "fix_versions": []}]}]}'
    )
    allow = tmp_path / "allow.toml"
    allow.write_text('review_by = "2999-01-01"\n[blockers]\nx = "y"\n')
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "pip_audit_gate.py"),
            "--report",
            str(report),
            "--allowlist",
            str(allow),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "new finding: pkg 1.0 PYSEC-9" in proc.stdout


def _cycles(tmp_path: Path, files: dict[str, str]) -> subprocess.CompletedProcess[str]:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    for name, body in files.items():
        (pkg / name).write_text(body)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "check_import_cycles.py"), "--root", "pkg"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


def test_type_checking_import_is_not_a_cycle(tmp_path: Path) -> None:
    proc = _cycles(
        tmp_path,
        {
            "a.py": "from .b import f\n",
            "b.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .a import g\n",
        },
    )
    assert proc.returncode == 0, proc.stdout


def test_runtime_cycles_are_still_caught(tmp_path: Path) -> None:
    lazy = _cycles(
        tmp_path,
        {"a.py": "from .b import f\n", "b.py": "def f():\n    from .a import g\n"},
    )
    assert lazy.returncode == 1 and "pkg.a -> pkg.b" in lazy.stderr


def test_type_checking_else_branch_still_counts(tmp_path: Path) -> None:
    proc = _cycles(
        tmp_path,
        {
            "a.py": "from .b import f\n",
            "b.py": "import typing\nif typing.TYPE_CHECKING:\n    pass\nelse:\n    from .a import g\n",
        },
    )
    assert proc.returncode == 1
