#!/usr/bin/env python3
"""Generate a CycloneDX-format SBOM for the active Python environment.

Run::

    python scripts/generate_sbom.py [--output sbom.json]

The script lazy-imports :mod:`cyclonedx_bom`. If it isn't installed, we print
the install hint and exit non-zero so CI surfaces the missing dependency.
"""
from __future__ import annotations

import argparse
import importlib
import shutil
import subprocess
import sys
from pathlib import Path

INSTALL_HINT = "pip install cyclonedx-bom"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("sbom.json"),
        help="Path to write the CycloneDX JSON SBOM (default: sbom.json).",
    )
    parser.add_argument(
        "--format",
        choices=("json", "xml"),
        default="json",
        help="CycloneDX output format (default: json).",
    )
    return parser.parse_args(argv)


def _have_module(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not _have_module("cyclonedx_py"):
        sys.stderr.write(
            "cyclonedx-bom is required to generate the SBOM.\n"
            f"Install it with: {INSTALL_HINT}\n"
        )
        return 2

    cyclonedx_cli = shutil.which("cyclonedx-py")
    base = (
        [cyclonedx_cli]
        if cyclonedx_cli
        else [sys.executable, "-m", "cyclonedx_py"]
    )
    cmd = [
        *base,
        "environment",
        "--of",
        args.format.upper(),
        "-o",
        str(args.output),
        sys.executable,
    ]

    try:
        result = subprocess.run(cmd, check=False)
    except FileNotFoundError as exc:
        sys.stderr.write(f"Failed to invoke cyclonedx-bom: {exc}\n")
        sys.stderr.write(f"Hint: {INSTALL_HINT}\n")
        return 2

    if result.returncode != 0:
        sys.stderr.write(
            f"cyclonedx-bom exited with status {result.returncode}\n"
        )
        return result.returncode

    sys.stdout.write(f"Wrote SBOM to {args.output}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
