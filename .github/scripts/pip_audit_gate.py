#!/usr/bin/env python3
"""Fail CI on any pip-audit finding that is not a reviewed, still-blocked exception.

Runs ``pip-audit -f json`` over the current environment (or reads a saved
report with ``--report``) and compares it with ``.github/pip-audit-allowlist.toml``.

The gate fails when:
  * a finding is not in the allowlist (a new vulnerability);
  * an allowlist entry matches nothing (the package was upgraded or removed,
    so the exception must be deleted rather than left to hide a future
    finding with the same id);
  * an entry is malformed (no reason, unknown blocker, wrong package);
  * the allowlist's ``review_by`` date has passed.

Usage:
    python .github/scripts/pip_audit_gate.py                 # run pip-audit
    python .github/scripts/pip_audit_gate.py --report r.json # use a saved report

Exit codes: 0 clean, 1 gate failure, 2 pip-audit could not produce a report.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

DEFAULT_ALLOWLIST = Path(__file__).resolve().parents[1] / "pip-audit-allowlist.toml"


@dataclass(frozen=True)
class Finding:
    package: str
    version: str
    id: str
    aliases: frozenset[str]
    fix_versions: tuple[str, ...]


@dataclass(frozen=True)
class Allowed:
    package: str
    id: str
    aliases: frozenset[str]


def _norm(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


def parse_report(report: dict) -> tuple[list[Finding], list[str]]:
    """Return (findings, skipped) from a pip-audit JSON report."""
    findings: list[Finding] = []
    skipped: list[str] = []
    for dep in report["dependencies"]:
        if "skip_reason" in dep:
            skipped.append(f"{dep['name']}: {dep['skip_reason']}")
            continue
        for vuln in dep.get("vulns", []):
            findings.append(
                Finding(
                    package=_norm(dep["name"]),
                    version=dep.get("version", "?"),
                    id=vuln["id"],
                    aliases=frozenset(vuln.get("aliases") or ()),
                    fix_versions=tuple(vuln.get("fix_versions") or ()),
                )
            )
    return findings, skipped


def evaluate(findings: list[Finding], allowlist: dict, today: date) -> list[str]:
    """Return the list of gate errors (empty means pass)."""
    errors: list[str] = []
    blockers = allowlist.get("blockers", {})

    review_by = allowlist.get("review_by")
    if not isinstance(review_by, str):
        errors.append("allowlist: review_by (YYYY-MM-DD) is required")
    elif date.fromisoformat(review_by) < today:
        errors.append(
            f"allowlist: review_by {review_by} has passed; re-check every entry "
            "(is the fix installable yet? is the code still unreachable?) and move the date"
        )

    entries: list[Allowed] = []
    for raw in allowlist.get("finding", []):
        label = f"allowlist entry {raw.get('package')}/{raw.get('id')}"
        if not raw.get("package") or not raw.get("id"):
            errors.append(f"{label}: package and id are required")
            continue
        if not str(raw.get("reason", "")).strip():
            errors.append(f"{label}: reason is required")
        if raw.get("blocked_by") not in blockers:
            errors.append(f"{label}: blocked_by must name a [blockers] entry")
        entries.append(
            Allowed(
                package=_norm(raw["package"]),
                id=raw["id"],
                aliases=frozenset(raw.get("aliases", ())),
            )
        )

    def ids(item: Finding | Allowed) -> frozenset[str]:
        return item.aliases | {item.id}

    used: set[Allowed] = set()
    for finding in findings:
        same_package = [entry for entry in entries if entry.package == finding.package]
        # Prefer the entry for this exact id; fall back to a shared alias (OSV
        # often publishes one advisory under several PYSEC/GHSA/CVE ids).
        match = next(
            (entry for entry in same_package if entry.id == finding.id),
            next((entry for entry in same_package if ids(entry) & ids(finding)), None),
        )
        if match is None:
            fix = ", ".join(finding.fix_versions) or "none"
            errors.append(
                f"new finding: {finding.package} {finding.version} {finding.id} "
                f"(aliases: {', '.join(sorted(finding.aliases)) or '-'}; fixed in: {fix})"
            )
        else:
            used.add(match)

    for entry in entries:
        if entry not in used:
            errors.append(
                f"stale allowlist entry: {entry.package} {entry.id} is no longer "
                "reported; delete it"
            )
    return errors


def run_pip_audit(extra_args: list[str]) -> dict:
    cmd = [
        sys.executable,
        "-m",
        "pip_audit",
        "--skip-editable",
        "-f",
        "json",
        *extra_args,
    ]
    # pip-audit exits 1 whenever it finds anything; the JSON is what matters.
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.stderr.write(proc.stderr)
        raise SystemExit(
            f"pip-audit produced no JSON report (exit {proc.returncode})"
        ) from None
    if "dependencies" not in report:
        raise SystemExit("pip-audit report has no 'dependencies' key")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument("--report", type=Path, help="saved `pip-audit -f json` output")
    args, extra = parser.parse_known_args(argv)

    try:
        report = (
            json.loads(args.report.read_text()) if args.report else run_pip_audit(extra)
        )
    except SystemExit as exc:
        print(f"pip-audit gate: {exc}", file=sys.stderr)
        return 2

    allowlist = tomllib.loads(args.allowlist.read_text())
    findings, skipped = parse_report(report)
    for item in skipped:
        print(f"note: not audited: {item}")

    errors = evaluate(findings, allowlist, datetime.now(UTC).date())
    allowed = len(findings) - sum(e.startswith("new finding") for e in errors)
    # ``allowed`` counts findings covered by a reviewed exception.
    print(
        f"pip-audit gate: {len(findings)} findings, {allowed} reviewed exceptions, "
        f"{len(errors)} errors"
    )
    for error in errors:
        print(f"::error::{error}" if "GITHUB_ACTIONS" in os.environ else error)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
