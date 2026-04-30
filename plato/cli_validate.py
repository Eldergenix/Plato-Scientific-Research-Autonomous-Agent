"""Phase 5 — standalone citation validation CLI.

Walks a Plato project on disk, pulls every reference it can find
(``runs/*/manifest.json`` source records and ``paper/refs.bib`` BibTeX),
runs them through :class:`~plato.tools.citation_validator.CitationValidator`,
and writes ``validation_report.json`` next to the most recent run.

Two entry points share this module:

- ``plato validate <project_dir>`` — invoked from :mod:`plato.cli`.
- ``plato run --validate-citations`` — fired after the main pipeline so the
  on-disk artifacts are present.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from plato.paper_agents.citation_validator_node import _parse_bibtex_entries
from plato.state.models import Source
from plato.tools.citation_validator import CitationValidator


_DEFAULT_THRESHOLD = 1.0


def _entry_to_source(entry: dict[str, Any], idx: int) -> Source | None:
    """Coerce a heterogeneous dict (BibTeX-parsed or sources.json) to a Source.

    Mirrors the priority used by the citation_validator_node so behaviour is
    consistent between graph runs and standalone runs.
    """
    if not isinstance(entry, dict):
        return None

    doi = entry.get("doi") or None
    arxiv_id = (
        entry.get("arxiv_id")
        or entry.get("arxiv")
        or entry.get("eprint")
        or None
    )
    title = entry.get("title") or entry.get("key") or f"reference-{idx}"
    url = entry.get("url") or entry.get("pdf_url") or None
    src_id = entry.get("id") or entry.get("key") or f"ref-{idx}"

    retrieved_via = entry.get("retrieved_via")
    if retrieved_via not in {
        "semantic_scholar",
        "arxiv",
        "openalex",
        "ads",
        "crossref",
        "pubmed",
    }:
        retrieved_via = "arxiv" if arxiv_id else "crossref"

    fetched_at_raw = entry.get("fetched_at")
    if isinstance(fetched_at_raw, str):
        try:
            fetched_at = datetime.fromisoformat(fetched_at_raw.replace("Z", "+00:00"))
        except ValueError:
            fetched_at = datetime.now(timezone.utc)
    else:
        fetched_at = datetime.now(timezone.utc)

    return Source(
        id=str(src_id),
        doi=doi,
        arxiv_id=arxiv_id,
        title=str(title),
        url=url,
        retrieved_via=retrieved_via,
        fetched_at=fetched_at,
    )


def _load_run_sources(run_dir: Path) -> list[Source]:
    """Pull Source records from a single run directory.

    Looks for two sidecars in priority order:
    - ``sources.json``: a JSON list of Source-shaped dicts (preferred — has
      DOIs/arxiv ids, so the validator can do real work).
    - ``manifest.json``: read for completeness, but ``source_ids`` are opaque
      strings without metadata, so they only contribute placeholders if no
      ``sources.json`` exists.
    """
    sources_path = run_dir / "sources.json"
    if sources_path.is_file():
        try:
            payload = json.loads(sources_path.read_text())
        except (OSError, ValueError):
            return []
        if not isinstance(payload, list):
            return []
        out: list[Source] = []
        for idx, entry in enumerate(payload):
            src = _entry_to_source(entry, idx)
            if src is not None:
                out.append(src)
        return out
    return []


def collect_sources_from_project(project_dir: Path) -> list[Source]:
    """Collect every validatable reference from a Plato project on disk.

    Walks ``<project_dir>/runs/*/`` for per-run sources sidecars and parses
    ``<project_dir>/paper/refs.bib`` for the canonical BibTeX. Deduplicates
    by ``Source.id`` so the same paper isn't validated twice when it shows
    up in both the run record and the bibliography.
    """
    project_dir = Path(project_dir)
    seen_ids: set[str] = set()
    out: list[Source] = []

    runs_dir = project_dir / "runs"
    if runs_dir.is_dir():
        for manifest_path in sorted(runs_dir.glob("*/manifest.json")):
            run_dir = manifest_path.parent
            for src in _load_run_sources(run_dir):
                if src.id in seen_ids:
                    continue
                seen_ids.add(src.id)
                out.append(src)

    bib_path = project_dir / "paper" / "refs.bib"
    if bib_path.is_file():
        try:
            blob = bib_path.read_text()
        except OSError:
            blob = ""
        for idx, entry in enumerate(_parse_bibtex_entries(blob)):
            src = _entry_to_source(entry, idx)
            if src is None:
                continue
            if src.id in seen_ids:
                continue
            seen_ids.add(src.id)
            out.append(src)

    return out


def _latest_run_dir(project_dir: Path) -> Path | None:
    runs_dir = project_dir / "runs"
    if not runs_dir.is_dir():
        return None
    candidates = [p for p in runs_dir.iterdir() if p.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _passed(result) -> bool:
    return bool(result.doi_resolved or result.arxiv_resolved)


async def run_validation(
    project_dir: Path,
    *,
    output: Path | None = None,
) -> dict[str, Any]:
    """Validate every source in ``project_dir`` and write a JSON report.

    Returns a summary dict with ``validation_rate``, ``total``, ``passed``,
    and ``failures``. Identical schema to the citation_validator_node sidecar
    so downstream consumers can read either.
    """
    project_dir = Path(project_dir)
    sources = collect_sources_from_project(project_dir)

    if not sources:
        report: dict[str, Any] = {
            "validation_rate": 0.0,
            "total": 0,
            "passed": 0,
            "failures": [],
        }
    else:
        async with CitationValidator() as validator:
            results = await validator.validate_batch(sources)

        failures: list[dict[str, Any]] = []
        passed_count = 0
        for src, result in zip(sources, results):
            if _passed(result):
                passed_count += 1
            else:
                failures.append(
                    {
                        "source_id": src.id,
                        "doi": src.doi,
                        "arxiv_id": src.arxiv_id,
                        "title": src.title,
                        "error": result.error,
                    }
                )
        total = len(sources)
        report = {
            "validation_rate": passed_count / total if total else 0.0,
            "total": total,
            "passed": passed_count,
            "failures": failures,
        }

    if output is not None:
        out_path = Path(output)
    else:
        latest = _latest_run_dir(project_dir)
        if latest is None:
            # No runs dir yet — drop the report at the project root so the
            # user always has somewhere to inspect.
            out_path = project_dir / "validation_report.json"
        else:
            out_path = latest / "validation_report.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    return report


def main(argv: list[str] | None = None) -> int:
    """Argparse entry for ``plato validate <project_dir>``."""
    parser = argparse.ArgumentParser(
        prog="plato validate",
        description="Validate every citation in a Plato project against Crossref/arXiv/URL liveness.",
    )
    parser.add_argument(
        "project_dir",
        type=Path,
        help="Path to a Plato project directory (must contain runs/ and/or paper/refs.bib).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Override the report output path. Defaults to <project_dir>/runs/<latest>/validation_report.json.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=_DEFAULT_THRESHOLD,
        help="Minimum validation_rate to count as passing (default: 1.0). Below this the CLI exits 1.",
    )

    args = parser.parse_args(argv)

    project_dir: Path = args.project_dir
    if not project_dir.is_dir():
        print(f"error: project directory does not exist: {project_dir}", file=sys.stderr)
        return 2

    report = asyncio.run(run_validation(project_dir, output=args.output))
    print(
        f"validated {report['total']} refs: "
        f"{report['passed']} passed, {len(report['failures'])} failed "
        f"(rate={report['validation_rate']:.3f})"
    )
    if report["validation_rate"] < args.threshold:
        return 1
    return 0


__all__ = [
    "collect_sources_from_project",
    "run_validation",
    "main",
]
