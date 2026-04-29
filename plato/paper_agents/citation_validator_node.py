"""Phase 2 — R3: citation-validation LangGraph node.

This node wraps :class:`plato.tools.citation_validator.CitationValidator` so
the paper-writing graph can validate every reference against authoritative
external services (Crossref, arXiv, URL liveness, retraction signals) before
the reviewer panel sees the draft.

The node is intentionally tolerant about *where* references live in the
graph state. In the current paper graph, citations land in
``state["paper"]["References"]`` as a BibTeX blob; in newer flows that use
the Phase 2 retrieval adapters, callers can pre-populate ``state["sources"]``
with :class:`Source` objects, or pass a structured ``state["references"]``
list of dicts/Source objects. This node inspects them in priority order and
falls back gracefully when none are present.

A ``validation_report.json`` is always written to
``<project_dir>/runs/<run_id>/`` (creating the directory if needed). When
``state["store"]`` is wired (a :class:`plato.state.store.Store`), each
``ValidationResult`` is also persisted via ``Store.add_validation``.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig

from ..state.models import Source, ValidationResult
from ..tools.citation_validator import CitationValidator


_BIB_ENTRY_RE = re.compile(r"@\w+\s*\{([^,]+),(.*?)\n\}", re.DOTALL)
_BIB_FIELD_RE = re.compile(r"(\w+)\s*=\s*\{(.+?)\}\s*,?", re.DOTALL)


def _parse_bibtex_entries(blob: str) -> list[dict[str, str]]:
    """Parse a BibTeX blob into a list of ``{key, doi, arxiv, title, url}`` dicts.

    The parser is forgiving: it pulls out fields it recognises and ignores
    the rest. This is enough to feed citation validation, not to round-trip
    a .bib file.
    """
    out: list[dict[str, str]] = []
    if not blob or not isinstance(blob, str):
        return out
    for match in _BIB_ENTRY_RE.finditer(blob):
        key = match.group(1).strip()
        body = match.group(2)
        fields: dict[str, str] = {"key": key}
        for fmatch in _BIB_FIELD_RE.finditer(body):
            fname = fmatch.group(1).strip().lower()
            fval = fmatch.group(2).strip()
            fields[fname] = fval
        # arXiv entries on Crossref-style BibTeX often use "eprint" for the id.
        if "eprint" in fields and "arxiv" not in fields:
            fields["arxiv"] = fields["eprint"]
        out.append(fields)
    return out


def _entry_to_source(entry: Any, idx: int) -> Source | None:
    """Coerce a heterogeneous reference record into a :class:`Source`.

    Accepted shapes:
    - :class:`Source` (returned as-is).
    - ``dict`` with optional ``id``/``doi``/``arxiv``/``arxiv_id``/``title``/``url``.
    - ``str`` BibTeX entry — parsed via :func:`_parse_bibtex_entries`.
    """
    now = datetime.now(timezone.utc)

    if isinstance(entry, Source):
        return entry

    if isinstance(entry, str):
        parsed = _parse_bibtex_entries(entry)
        if not parsed:
            return None
        entry = parsed[0]

    if not isinstance(entry, dict):
        return None

    doi = entry.get("doi") or None
    arxiv_id = entry.get("arxiv_id") or entry.get("arxiv") or entry.get("eprint") or None
    title = entry.get("title") or entry.get("key") or f"reference-{idx}"
    url = entry.get("url") or entry.get("pdf_url") or None
    src_id = entry.get("id") or entry.get("key") or f"ref-{idx}"

    if doi:
        retrieved_via = "crossref"
    elif arxiv_id:
        retrieved_via = "arxiv"
    else:
        # Sentinel: we still want validators to see this ref, but we can only
        # check URL liveness. ``crossref`` is the safe fallback Literal value.
        retrieved_via = "crossref"

    return Source(
        id=str(src_id),
        doi=doi,
        arxiv_id=arxiv_id,
        title=str(title),
        url=url,
        retrieved_via=retrieved_via,
        fetched_at=now,
    )


def _collect_sources(state: dict) -> list[Source]:
    """Pick the most informative reference list available on the state."""
    if not isinstance(state, dict):
        return []

    # Priority 1: explicit Source objects from the retrieval pipeline.
    sources = state.get("sources")
    if sources:
        out: list[Source] = []
        for idx, entry in enumerate(sources):
            src = _entry_to_source(entry, idx)
            if src is not None:
                out.append(src)
        if out:
            return out

    # Priority 2: a structured references list (dicts or Source objects).
    refs = state.get("references")
    if refs:
        out_refs: list[Source] = []
        for idx, entry in enumerate(refs):
            src = _entry_to_source(entry, idx)
            if src is not None:
                out_refs.append(src)
        if out_refs:
            return out_refs

    # Priority 3: BibTeX blob in state["paper"]["References"].
    paper = state.get("paper") or {}
    blob = paper.get("References") if isinstance(paper, dict) else None
    if blob:
        parsed = _parse_bibtex_entries(blob)
        out_bib: list[Source] = []
        for idx, entry in enumerate(parsed):
            src = _entry_to_source(entry, idx)
            if src is not None:
                out_bib.append(src)
        if out_bib:
            return out_bib

    return []


def _resolve_run_dir(state: dict) -> tuple[str, Path | None]:
    """Return ``(run_id, run_dir)`` — directory is None if no project folder."""
    run_id = state.get("run_id") if isinstance(state, dict) else None
    if not run_id:
        run_id = uuid.uuid4().hex[:12]

    files = state.get("files") if isinstance(state, dict) else None
    folder = files.get("Folder") if isinstance(files, dict) else None
    if not folder:
        return run_id, None

    run_dir = Path(folder) / "runs" / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_id, run_dir


def _passed(result: ValidationResult) -> bool:
    """A reference passes if its DOI or arXiv id resolves."""
    return bool(result.doi_resolved or result.arxiv_resolved)


async def citation_validator_node(state: dict, config: RunnableConfig = None) -> dict:
    """LangGraph node: validate references and emit ``validation_report.json``.

    Returns a partial state update with ``validation_report`` populated.
    Persistence to a SQL :class:`Store` happens iff ``state["store"]`` is
    set; otherwise we only write the JSON sidecar.
    """
    sources = _collect_sources(state)
    run_id, run_dir = _resolve_run_dir(state)

    if not sources:
        report = {
            "run_id": run_id,
            "validation_rate": 0.0,
            "total": 0,
            "passed": 0,
            "failures": [],
        }
        if run_dir is not None:
            (run_dir / "validation_report.json").write_text(
                json.dumps(report, indent=2, sort_keys=True)
            )
        return {"validation_report": report, "run_id": run_id}

    async with CitationValidator() as validator:
        results = await validator.validate_batch(sources)

    store = state.get("store") if isinstance(state, dict) else None
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
        if store is not None:
            try:
                store.add_validation(result)
            except Exception:
                # Persistence is best-effort; never crash the graph on store error.
                pass

    total = len(sources)
    rate = passed_count / total if total else 0.0
    report = {
        "run_id": run_id,
        "validation_rate": rate,
        "total": total,
        "passed": passed_count,
        "failures": failures,
    }

    if run_dir is not None:
        (run_dir / "validation_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True)
        )

    return {"validation_report": report, "run_id": run_id}


__all__ = ["citation_validator_node"]
