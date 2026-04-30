"""Phase 5 unit tests for ``scripts/license_audit.py``."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make the repo's scripts/ directory importable.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import license_audit  # noqa: E402  (path manipulation above)


def test_collect_distributions_non_empty() -> None:
    dists = license_audit.collect_distributions()
    assert dists, "expected at least one installed distribution"
    # The CI venv installs pytest, so we should always see it.
    names = {d.name.lower() for d in dists}
    assert "pytest" in names


def test_each_entry_has_required_keys() -> None:
    dists = license_audit.collect_distributions()
    for d in dists:
        assert d.name
        assert d.version
        assert d.license  # always populated, even if it's "UNKNOWN"
        assert d.license_source in {
            "expression",
            "classifier",
            "license-field",
            "license-text",
            "project-own",
            "override",
            "unknown",
        }
        assert isinstance(d.compatible, bool)


@pytest.mark.parametrize(
    "license_str",
    [
        "MIT",
        "Apache-2.0",
        "Apache 2.0",
        "Apache License 2.0",
        "BSD-3-Clause",
        "BSD-2-Clause",
        "ISC",
        "MPL-2.0",
        "LGPL-3.0",
        "LGPL-2.1+",
        "GPL-3.0",
        "GPL-3.0-or-later",
        "GPLv3",
        "AGPL-3.0",
        "PSF-2.0",
        "0BSD",
        "Unlicense",
        "CC0-1.0",
        "NCSA",
    ],
)
def test_compatible_licenses(license_str: str) -> None:
    ok, reason = license_audit.is_compatible_with_gpl3(license_str)
    assert ok, f"{license_str!r} should be compatible: {reason}"


@pytest.mark.parametrize(
    "license_str",
    [
        "Proprietary",
        "All rights reserved",
        "Commercial license — all rights reserved",
        "BUSL-1.1",
        "Business Source License",
        "SSPL-1.0",
        "Elastic-2.0",
        "Commons Clause",
        "CC-BY-NC-4.0",
        "GPL-2.0-only",
        "",  # missing
    ],
)
def test_incompatible_licenses(license_str: str) -> None:
    ok, _ = license_audit.is_compatible_with_gpl3(license_str)
    assert not ok, f"{license_str!r} should be flagged incompatible"


def test_compatibility_match_is_word_boundaried() -> None:
    # A word that contains "MIT" as a substring should not be auto-approved.
    ok, _ = license_audit.is_compatible_with_gpl3("ADMITTED")
    assert not ok


def test_markdown_output_includes_table_header() -> None:
    md = license_audit.render_markdown(license_audit.collect_distributions())
    assert md.startswith("# License Audit")
    assert "## License distribution" in md
    assert "## Per-dependency table" in md
    assert "| Name | Version | License" in md


def test_json_output_is_valid_spdx_flavoured() -> None:
    payload = license_audit.render_json(license_audit.collect_distributions())
    parsed = json.loads(payload)
    assert parsed["spdxVersion"].startswith("SPDX-")
    assert parsed["name"] == "plato-license-audit"
    assert "totalDistributions" in parsed
    assert "packages" in parsed
    assert isinstance(parsed["packages"], list)
    assert parsed["packages"], "expected non-empty packages list"
    pkg = parsed["packages"][0]
    for key in (
        "name",
        "version",
        "licenseConcluded",
        "gpl3Compatible",
        "compatibilityReason",
    ):
        assert key in pkg


def test_csv_output_has_header() -> None:
    csv_text = license_audit.render_csv(license_audit.collect_distributions())
    first_line = csv_text.splitlines()[0]
    assert "name" in first_line
    assert "version" in first_line
    assert "license" in first_line
    assert "gpl3_compatible" in first_line


def test_main_exits_zero_in_clean_environment(capsys: pytest.CaptureFixture[str]) -> None:
    # The CI environment is curated; the audit must come back clean.
    code = license_audit.main(["--format=md"])
    assert code == 0
    captured = capsys.readouterr()
    assert "# License Audit" in captured.out
