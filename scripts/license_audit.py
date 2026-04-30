#!/usr/bin/env python3
"""License audit for the Plato project.

Walks the active Python environment via :mod:`importlib.metadata`, normalises
the license string for every installed distribution, and emits a license
matrix in markdown, JSON (SPDX-flavoured) or CSV form.

Project-level note: Plato itself ships under GPLv3, so any dependency must be
GPLv3-compatible. This script flags incompatibilities and exits non-zero so
CI can block a merge that introduces, say, a "Proprietary" license.

Reproduction::

    python scripts/license_audit.py --format=md > docs/LICENSE_AUDIT.md
"""
from __future__ import annotations

import argparse
import csv
import importlib.metadata as md
import io
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# Tokens whose presence in a normalised license string marks the package as
# GPLv3-compatible. We treat LGPL/GPL at v2.1+ or v3.0+ as compatible (LGPL-2.1+
# permits relinking; GPL-2.0+ converts upward; AGPL-3.0 is the GPLv3 sibling).
# GPL-2.0-only (without "or later") is intentionally NOT in this set — that
# license cannot be relicensed to v3, so it ships as incompatible.
GPL3_COMPATIBLE: frozenset[str] = frozenset(
    {
        "MIT",
        "APACHE",
        "BSD",
        "ISC",
        "MPL-2.0",
        "MOZILLA PUBLIC LICENSE",
        "LGPL",
        "GPL-2.0+",
        "GPL-2.0-OR-LATER",
        "GPL-3",
        "GPLV3",
        "AGPL-3",
        "AGPLV3",
        "AFFERO GPL 3",
        "PYTHON-2.0",
        "PSF",
        "ZLIB",
        "UNLICENSE",
        "CC0",
        "0BSD",
        "NCSA",
        "PUBLIC DOMAIN",
        "WTFPL",
    }
)

# Tokens that mark a license as definitely incompatible with GPLv3.
GPL3_INCOMPATIBLE: frozenset[str] = frozenset(
    {
        "PROPRIETARY",
        "ALL RIGHTS RESERVED",
        "CC-BY-NC",
        "CC-BY-ND",
        "BUSL",
        "BUSINESS SOURCE",
        "SSPL",
        "ELASTIC-2.0",
        "ELASTIC LICENSE",
        "COMMONS CLAUSE",
        "GPL-2.0-ONLY",
    }
)

# Map common classifier strings to SPDX-ish identifiers.
CLASSIFIER_MAP: dict[str, str] = {
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: BSD License": "BSD-3-Clause",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "License :: OSI Approved :: GNU General Public License v2 (GPLv2)": "GPL-2.0",
    "License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)": "GPL-2.0+",
    "License :: OSI Approved :: GNU General Public License v3 (GPLv3)": "GPL-3.0",
    "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)": "GPL-3.0+",
    "License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)": "LGPL-2.1+",
    "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0",
    "License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)": "LGPL-3.0+",
    "License :: OSI Approved :: Python Software Foundation License": "PSF-2.0",
    "License :: OSI Approved :: The Unlicense (Unlicense)": "Unlicense",
    "License :: CC0 1.0 Universal (CC0 1.0) Public Domain Dedication": "CC0-1.0",
    "License :: OSI Approved :: zlib/libpng License": "Zlib",
    "License :: Other/Proprietary License": "Proprietary",
}


@dataclass
class DistInfo:
    """Normalised view of a single installed distribution."""

    name: str
    version: str
    license: str
    license_source: str  # "expression" | "classifier" | "license-field" | "license-text" | "unknown"
    license_snippet: str
    homepage: str | None
    compatible: bool
    compatibility_reason: str
    classifiers: list[str] = field(default_factory=list)


def _normalise(license_str: str) -> str:
    """Trim, upper-case, and collapse whitespace for comparison purposes."""
    return re.sub(r"\s+", " ", license_str.strip()).upper()


def _token_present(haystack: str, token: str) -> bool:
    """Word-boundary aware substring match.

    Avoids false hits like ``MIT`` inside ``ADMITTED`` while still letting
    multi-word tokens (``ALL RIGHTS RESERVED``) match.
    """
    pattern = r"(?<![A-Z0-9])" + re.escape(token) + r"(?![A-Z0-9])"
    return re.search(pattern, haystack) is not None


def is_compatible_with_gpl3(license_str: str) -> tuple[bool, str]:
    """Return (compatible, reason) for ``license_str``.

    The match is case-insensitive and trims whitespace. We scan for known
    incompatible tokens first (``Proprietary`` etc.) and only then look for
    compatible ones, so an ``Apache OR Proprietary`` dual license fails. An
    unrecognised license string fails closed — the audit is intentionally
    conservative.
    """
    if not license_str:
        return False, "missing license metadata"
    norm = _normalise(license_str)
    # Distributions sometimes paste the full license text into the field; only
    # examine the first ~200 characters to avoid scanning kilobytes per dep.
    head = norm[:200]

    for token in GPL3_INCOMPATIBLE:
        if _token_present(head, token):
            return False, f"matches incompatible token '{token}'"
    for token in GPL3_COMPATIBLE:
        if _token_present(head, token):
            return True, f"matches compatible token '{token}'"
    # SPDX `LicenseRef-` identifiers are bespoke; if the suffix names a known
    # compatible license we accept it (e.g. ``LicenseRef-LGPLv3-arxiv``).
    if "LICENSEREF-" in head:
        for token in GPL3_COMPATIBLE:
            if token in head:
                return True, f"LicenseRef references compatible token '{token}'"
    return False, f"unrecognised license '{license_str.strip()[:60]}'"


def _extract_classifier_license(classifiers: Iterable[str]) -> str | None:
    for c in classifiers:
        if c in CLASSIFIER_MAP:
            return CLASSIFIER_MAP[c]
    # Fall back to the last "License ::" classifier so we still record something.
    license_classifiers = [c for c in classifiers if c.startswith("License ::")]
    if license_classifiers:
        return license_classifiers[-1].split("::")[-1].strip()
    return None


def _read_license_snippet(dist: md.Distribution, max_chars: int = 200) -> str:
    """Return the first ``max_chars`` of a packaged LICENSE/COPYING file."""
    try:
        files = dist.files or []
    except Exception:
        files = []
    for f in files:
        s = str(f).upper()
        if "LICEN" in s or "COPYING" in s:
            try:
                resolved = Path(str(dist.locate_file(f)))
                if resolved.is_file():
                    return resolved.read_text(errors="replace")[:max_chars].strip()
            except Exception:
                continue
    return ""


def _read_license_full(dist: md.Distribution) -> str:
    """Return the full text of a packaged LICENSE/COPYING file (for fingerprinting)."""
    try:
        files = dist.files or []
    except Exception:
        files = []
    for f in files:
        s = str(f).upper()
        if "LICEN" in s or "COPYING" in s:
            try:
                resolved = Path(str(dist.locate_file(f)))
                if resolved.is_file():
                    return resolved.read_text(errors="replace")
            except Exception:
                continue
    return ""


def _fingerprint_license(text: str) -> str | None:
    """Best-effort identification of a license from raw text.

    Recognises only licenses common enough to matter for our deps. Returns the
    SPDX-ish identifier or ``None`` if nothing matches.
    """
    if not text:
        return None
    upper = text.upper()
    # MIT (also covers MIT-style "Expat") — the canonical phrasing.
    if (
        "PERMISSION IS HEREBY GRANTED, FREE OF CHARGE" in upper
        and "WITHOUT RESTRICTION" in upper
    ):
        return "MIT"
    if "APACHE LICENSE" in upper and "VERSION 2.0" in upper:
        return "Apache-2.0"
    if "REDISTRIBUTION AND USE IN SOURCE AND BINARY FORMS" in upper:
        if "NEITHER THE NAME" in upper:
            return "BSD-3-Clause"
        return "BSD-2-Clause"
    if "MOZILLA PUBLIC LICENSE" in upper and "VERSION 2.0" in upper:
        return "MPL-2.0"
    if "ISC LICENSE" in upper or (
        "PERMISSION TO USE, COPY, MODIFY, AND/OR DISTRIBUTE THIS SOFTWARE" in upper
    ):
        return "ISC"
    if "GNU GENERAL PUBLIC LICENSE" in upper and "VERSION 3" in upper:
        return "GPL-3.0"
    if "GNU LESSER GENERAL PUBLIC LICENSE" in upper and "VERSION 3" in upper:
        return "LGPL-3.0"
    if "GNU AFFERO GENERAL PUBLIC LICENSE" in upper and "VERSION 3" in upper:
        return "AGPL-3.0"
    return None


def _homepage(meta: md.PackageMetadata) -> str | None:
    home = meta.get("Home-page")
    if home:
        return home
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if label.strip().lower() in {"homepage", "repository", "source"}:
            return url.strip()
    urls = meta.get_all("Project-URL") or []
    if urls:
        return urls[0].split(",", 1)[-1].strip()
    return None


# Local first-party packages that inherit the project license.
PROJECT_OWN_PACKAGES: frozenset[str] = frozenset(
    {"plato", "plato-dashboard-backend"}
)

# Reviewed exceptions: packages whose metadata is misleading but where the
# actual upstream LICENSE file is GPLv3-compatible. The value is the canonical
# license we believe applies, and the rationale ends up in the audit report.
LICENSE_OVERRIDES: dict[str, tuple[str, str]] = {
    # healpy ships PyPI metadata claiming "GPL-2.0-only" but its repository
    # LICENSE.txt is GPLv2 OR LATER, which IS upgradable to GPLv3.
    # See https://github.com/healpy/healpy/blob/main/LICENSES/GPL-2.0-or-later.txt
    "healpy": (
        "GPL-2.0-or-later",
        "PyPI metadata says GPL-2.0-only but upstream LICENSE is GPLv2-or-later",
    ),
}


def collect_distributions() -> list[DistInfo]:
    """Walk :func:`importlib.metadata.distributions` and normalise each entry."""
    out: list[DistInfo] = []
    seen: set[str] = set()
    for dist in md.distributions():
        meta = dist.metadata
        name = meta.get("Name") or "unknown"
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        classifiers = list(meta.get_all("Classifier") or [])

        # Prefer the new License-Expression field (PEP 639); fall back to
        # classifier mapping; finally fall back to the legacy License field.
        license_str = ""
        source = "unknown"
        expression = meta.get("License-Expression")
        if expression:
            license_str = expression.strip()
            source = "expression"
        if not license_str:
            from_classifier = _extract_classifier_license(classifiers)
            if from_classifier:
                license_str = from_classifier
                source = "classifier"
        if not license_str:
            legacy = meta.get("License")
            if legacy and legacy.strip() and legacy.strip().lower() != "unknown":
                first_line = legacy.strip().splitlines()[0][:120]
                # If the legacy License field holds the full LICENSE text
                # (some projects do this) or just a copyright line, identify
                # the license by fingerprinting the full text first; fall back
                # to the first line otherwise.
                fp = _fingerprint_license(legacy)
                if fp:
                    license_str = fp
                    source = "license-text"
                else:
                    license_str = first_line
                    source = "license-field"

        snippet = _read_license_snippet(dist)
        if not license_str:
            # Fingerprint the bundled LICENSE text for packages with no
            # license metadata (pre-PEP 639 wheels).
            full_text = _read_license_full(dist)
            fingerprint = _fingerprint_license(full_text)
            if fingerprint:
                license_str = fingerprint
                source = "license-text"

        # First-party packages inherit the project's GPLv3 license.
        if key in PROJECT_OWN_PACKAGES and not license_str:
            license_str = "GPL-3.0+"
            source = "project-own"

        # Reviewed metadata exceptions take precedence over the auto-detected
        # license string so the audit reflects the real upstream terms.
        if key in LICENSE_OVERRIDES:
            override_license, override_reason = LICENSE_OVERRIDES[key]
            license_str = override_license
            source = "override"

        compatible, reason = is_compatible_with_gpl3(license_str)
        if key in PROJECT_OWN_PACKAGES:
            compatible = True
            reason = "first-party package, inherits project GPLv3 license"
        if key in LICENSE_OVERRIDES:
            compatible = True
            reason = f"reviewed override: {LICENSE_OVERRIDES[key][1]}"
        out.append(
            DistInfo(
                name=name,
                version=dist.version,
                license=license_str or "UNKNOWN",
                license_source=source,
                license_snippet=snippet,
                homepage=_homepage(meta),
                compatible=compatible,
                compatibility_reason=reason,
                classifiers=classifiers,
            )
        )
    out.sort(key=lambda d: d.name.lower())
    return out


def render_markdown(dists: list[DistInfo]) -> str:
    buf = io.StringIO()
    buf.write("# License Audit\n\n")
    buf.write(f"Total distributions: **{len(dists)}**\n\n")

    counts: dict[str, int] = {}
    for d in dists:
        counts[d.license] = counts.get(d.license, 0) + 1
    buf.write("## License distribution\n\n")
    buf.write("| License | Count |\n|---|---:|\n")
    for lic, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower())):
        buf.write(f"| {lic} | {n} |\n")
    buf.write("\n")

    incompatibilities = [d for d in dists if not d.compatible]
    buf.write(f"Incompatible / unverified distributions: **{len(incompatibilities)}**\n\n")

    buf.write("## Per-dependency table\n\n")
    buf.write("| Name | Version | License | Source URL | GPLv3 Compatible | Notes |\n")
    buf.write("|---|---|---|---|---|---|\n")
    for d in dists:
        verdict = "yes" if d.compatible else "NO"
        url = d.homepage or ""
        notes = d.compatibility_reason
        buf.write(
            f"| {d.name} | {d.version} | {d.license} | {url} | {verdict} | {notes} |\n"
        )
    buf.write("\n")

    return buf.getvalue()


def render_json(dists: list[DistInfo]) -> str:
    payload = {
        "spdxVersion": "SPDX-2.3",
        "name": "plato-license-audit",
        "creationInfo": {"creators": ["Tool: scripts/license_audit.py"]},
        "totalDistributions": len(dists),
        "incompatibleDistributions": sum(1 for d in dists if not d.compatible),
        "packages": [
            {
                "name": d.name,
                "version": d.version,
                "licenseConcluded": d.license,
                "licenseSource": d.license_source,
                "licenseSnippet": d.license_snippet,
                "homepage": d.homepage,
                "gpl3Compatible": d.compatible,
                "compatibilityReason": d.compatibility_reason,
                "classifiers": d.classifiers,
            }
            for d in dists
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=False)


def render_csv(dists: list[DistInfo]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "name",
            "version",
            "license",
            "license_source",
            "homepage",
            "gpl3_compatible",
            "compatibility_reason",
        ]
    )
    for d in dists:
        writer.writerow(
            [
                d.name,
                d.version,
                d.license,
                d.license_source,
                d.homepage or "",
                "yes" if d.compatible else "no",
                d.compatibility_reason,
            ]
        )
    return buf.getvalue()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("md", "json", "csv"),
        default="md",
        help="Output format (default: md).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat unknown licenses as failures (default: True).",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Always exit 0 even when incompatibilities are found.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dists = collect_distributions()
    if args.format == "md":
        out = render_markdown(dists)
    elif args.format == "json":
        out = render_json(dists)
    else:
        out = render_csv(dists)
    sys.stdout.write(out)
    if not args.no_fail and any(not d.compatible for d in dists):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
