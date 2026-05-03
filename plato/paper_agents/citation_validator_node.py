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
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from langchain_core.runnables import RunnableConfig

from ..quality.retraction_db import RetractionDB
from ..state.models import Source, ValidationResult
from ..tools.citation_validator import CitationValidator

logger = logging.getLogger(__name__)


def _load_retraction_db(state: "GraphState") -> RetractionDB:
    """Load the retraction DB from state, env var, or fall back to empty.

    Resolution order:
      1. ``state["retraction_db"]`` if a :class:`RetractionDB` is already set.
      2. ``state["retraction_db_path"]`` (string path) if provided.
      3. ``$PLATO_RETRACTION_DB_PATH`` environment variable.
    Missing or unreadable files log a warning and return an empty DB so the
    graph never crashes on a misconfigured path.
    """
    # ``state`` is the GraphState TypedDict (always a dict at runtime);
    # the previous ``isinstance(state, dict)`` was defensive scaffolding
    # mypy correctly flags as dead.
    existing = state.get("retraction_db")
    if isinstance(existing, RetractionDB):
        return existing
    path: Any = state.get("retraction_db_path")

    if not path:
        path = os.environ.get("PLATO_RETRACTION_DB_PATH")

    if not path:
        return RetractionDB.empty()

    try:
        return RetractionDB.from_csv(str(path))
    except (FileNotFoundError, OSError, ValueError) as exc:
        logger.warning(
            "RetractionDB load failed for %s (%s); continuing with empty DB.",
            path, exc,
        )
        return RetractionDB.empty()

if TYPE_CHECKING:  # pragma: no cover — annotation only
    from .parameters import GraphState


_BIB_ENTRY_HEAD_RE = re.compile(r"@(\w+)\s*\{")
_BIB_FIELD_NAME_RE = re.compile(r"(\w+)\s*=\s*")


def _scan_balanced(text: str, start: int, opener: str = "{", closer: str = "}") -> int:
    """Return the index of the closer that balances ``text[start]`` (the opener).

    Returns ``-1`` if no balanced closer exists. Handles backslash-escapes
    so ``\\{`` / ``\\}`` are treated as literal characters, not bracket
    structure (e.g. ``{title = {Sub \\{brace\\} value}}`` parses correctly).
    """
    if start >= len(text) or text[start] != opener:
        return -1
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            i += 2  # skip the escape and the next character verbatim
            continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _strip_bib_quotes(value: str) -> str:
    """Strip surrounding ``{...}`` or ``"..."`` BibTeX delimiters."""
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"',):
        return v[1:-1].strip()
    if v.startswith("{") and v.endswith("}"):
        # Already-balanced brace pair — strip exactly one layer.
        return v[1:-1].strip()
    return v


def _parse_bibtex_fields(body: str) -> dict[str, str]:
    """Pull ``key = {value}`` pairs out of an entry body.

    Handles brace-quoted values, double-quoted values, nested braces, and
    backslash-escaped delimiters. Unknown bare-word values (e.g. integer
    years like ``year = 2024``) are captured verbatim up to the next comma.
    """
    fields: dict[str, str] = {}
    i = 0
    n = len(body)
    while i < n:
        # Skip whitespace + leading commas.
        while i < n and body[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        m = _BIB_FIELD_NAME_RE.match(body, i)
        if not m:
            # Unparseable garbage — skip to the next comma at depth 0.
            depth = 0
            while i < n and not (body[i] == "," and depth == 0):
                if body[i] == "{":
                    depth += 1
                elif body[i] == "}" and depth > 0:
                    depth -= 1
                i += 1
            continue
        name = m.group(1).strip().lower()
        i = m.end()
        if i >= n:
            break
        if body[i] == "{":
            close = _scan_balanced(body, i, "{", "}")
            if close == -1:
                break  # unbalanced; bail out
            value = body[i + 1 : close]
            i = close + 1
        elif body[i] == '"':
            # Find the matching quote, skipping backslash escapes.
            j = i + 1
            while j < n and body[j] != '"':
                if body[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                j += 1
            if j >= n:
                break
            value = body[i + 1 : j]
            i = j + 1
        else:
            # Bare word: read until next comma at depth 0 or EOL.
            depth = 0
            j = i
            while j < n and not (body[j] == "," and depth == 0):
                if body[j] == "{":
                    depth += 1
                elif body[j] == "}" and depth > 0:
                    depth -= 1
                j += 1
            value = body[i:j].strip()
            i = j
        fields[name] = _strip_bib_quotes(value)
    return fields


def _parse_bibtex_entries(blob: str) -> list[dict[str, str]]:
    """Parse a BibTeX blob into a list of ``{key, doi, arxiv, title, url}`` dicts.

    Brace-counting parser (handles nested braces and escapes); not a
    full BibTeX implementation, but robust enough for citation validation.
    Entry types like ``@string`` and ``@comment`` are skipped.
    """
    out: list[dict[str, str]] = []
    if not blob or not isinstance(blob, str):
        return out

    pos = 0
    while pos < len(blob):
        m = _BIB_ENTRY_HEAD_RE.search(blob, pos)
        if not m:
            break
        entry_type = m.group(1).lower()
        # Find the opening brace and its matching closer.
        brace_open = blob.find("{", m.end() - 1)
        if brace_open == -1:
            break
        brace_close = _scan_balanced(blob, brace_open, "{", "}")
        if brace_close == -1:
            break
        inner = blob[brace_open + 1 : brace_close]
        pos = brace_close + 1

        # Skip non-bibliographic entries.
        if entry_type in {"string", "preamble", "comment"}:
            continue

        # First token before the first top-level comma is the entry key.
        depth = 0
        comma_idx = -1
        for j, ch in enumerate(inner):
            if ch == "{":
                depth += 1
            elif ch == "}" and depth > 0:
                depth -= 1
            elif ch == "," and depth == 0:
                comma_idx = j
                break
        if comma_idx == -1:
            # No fields, just a key — record what we have.
            out.append({"key": inner.strip()})
            continue
        key = inner[:comma_idx].strip()
        body = inner[comma_idx + 1 :]
        fields = _parse_bibtex_fields(body)
        fields["key"] = key
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


def _collect_sources(state: Mapping[str, Any]) -> list[Source]:
    """Pick the most informative reference list available on the state."""
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


def _resolve_run_dir(state: Mapping[str, Any]) -> tuple[str, Path | None]:
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


async def citation_validator_node(
    state: "GraphState",
    config: RunnableConfig | None = None,
) -> dict:
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

    retraction_db = _load_retraction_db(state)
    async with CitationValidator(retraction_db=set(retraction_db)) as validator:
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
        # ``unverified_count`` mirrors the architectural-plan acceptance
        # criterion ("unverified_count must equal 0" in the Phase-2
        # gate). It is total minus passed so a failure_url-only entry
        # still counts as unverified.
        "unverified_count": total - passed_count,
        "failures": failures,
    }

    if run_dir is not None:
        (run_dir / "validation_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True)
        )

    return {"validation_report": report, "run_id": run_id}


__all__ = ["citation_validator_node"]
