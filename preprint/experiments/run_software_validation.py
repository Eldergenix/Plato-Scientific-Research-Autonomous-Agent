#!/usr/bin/env python3
"""Run and summarize the deterministic validation suites cited by the preprint."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

SUITES = {
    "biology_domain": [
        "tests/unit/test_biology_domain.py",
        "tests/unit/test_biology_end_to_end.py",
    ],
    "genomics_adapters": ["tests/unit/test_genomics_tools.py"],
    "evidence_and_citations": [
        "tests/unit/test_citation_validator.py",
        "tests/unit/test_citation_validator_node.py",
        "tests/unit/test_claim_extractor.py",
        "tests/unit/test_evidence_matrix_node.py",
        "tests/unit/test_scientific_verifier.py",
    ],
    "adversarial_safety": ["tests/safety"],
    "full_python": ["tests"],
}


def read_junit(path: Path) -> dict[str, int | float]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {
        "tests": sum(int(suite.attrib.get("tests", 0)) for suite in suites),
        "failures": sum(int(suite.attrib.get("failures", 0)) for suite in suites),
        "errors": sum(int(suite.attrib.get("errors", 0)) for suite in suites),
        "skipped": sum(int(suite.attrib.get("skipped", 0)) for suite in suites),
        "junit_time_seconds": round(
            sum(float(suite.attrib.get("time", 0.0)) for suite in suites), 6
        ),
    }


def git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "preprint" / "results" / "software_validation.json",
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=REPO_ROOT / ".venv" / "bin" / "python",
    )
    args = parser.parse_args()
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(prefix="plato-preprint-validation-") as tmp:
        tmp_dir = Path(tmp)
        for name, paths in SUITES.items():
            junit_path = tmp_dir / f"{name}.xml"
            command = [
                str(args.python),
                "-m",
                "pytest",
                "-q",
                *paths,
                f"--junitxml={junit_path}",
            ]
            started = time.perf_counter()
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            wall_seconds = time.perf_counter() - started
            parsed = read_junit(junit_path) if junit_path.exists() else {}
            results[name] = {
                "paths": paths,
                "command": command,
                "returncode": completed.returncode,
                "wall_seconds": round(wall_seconds, 6),
                **parsed,
            }

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_value("rev-parse", "HEAD"),
        "git_dirty_at_run": bool(git_value("status", "--porcelain")),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "suites": results,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if any(result["returncode"] != 0 for result in results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
