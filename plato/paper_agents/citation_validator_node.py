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
from typing import TYPE_CHECKING, Any, Optional, cast

from langchain_core.runnables import RunnableConfig

from ..state.models import RetrievedVia, Source
from ..tools.citation_matching import coerce_authors, coerce_year
from ..tools.citation_reports import STRICT_ACCURACY_THRESHOLD
from ..tools.citation_validator import CitationValidator, build_validation_report

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
    arxiv_id = (
        entry.get("arxiv_id") or entry.get("arxiv") or entry.get("eprint") or None
    )
    title = entry.get("title") or entry.get("key") or f"reference-{idx}"
    url = entry.get("url") or entry.get("pdf_url") or None
    src_id = entry.get("id") or entry.get("key") or f"ref-{idx}"
    authors = coerce_authors(entry.get("authors") or entry.get("author"))
    year = coerce_year(entry.get("year"))
    venue = entry.get("venue") or entry.get("journal") or entry.get("booktitle") or None

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
        authors=authors,
        year=year,
        venue=str(venue) if venue else None,
        url=url,
        retrieved_via=cast(RetrievedVia, retrieved_via),
        fetched_at=now,
    )


def _collect_sources(state: Any) -> list[Source]:
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


def _resolve_run_dir(state: Any) -> tuple[str, Path | None]:
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


async def citation_validator_node(
    state: "GraphState",
    config: Optional[RunnableConfig] = None,
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
            "total_references": 0,
            "verified_references": 0,
            "unverified_count": 0,
            "likely_hallucinations": 0,
            "accuracy_gate": {
                "threshold": STRICT_ACCURACY_THRESHOLD,
                "passed": False,
                "reason": "no references were available for validation",
            },
            "failures": [],
            "warnings": [],
            "references": [],
        }
        if run_dir is not None:
            (run_dir / "validation_report.json").write_text(
                json.dumps(report, indent=2, sort_keys=True)
            )
        return {"validation_report": report, "run_id": run_id}

    async with CitationValidator() as validator:
        results = await validator.validate_batch(sources)

    store = state.get("store") if isinstance(state, dict) else None
    for src, result in zip(sources, results):
        if store is not None:
            try:
                store.add_validation(result)
            except Exception:
                # Persistence is best-effort; never crash the graph on store error.
                pass

    report = build_validation_report(run_id, sources, results)

    if run_dir is not None:
        (run_dir / "validation_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True)
        )

    gate = cast(dict[str, Any], report.get("accuracy_gate") or {})
    if gate.get("passed") is False and state.get("enforce_reference_gate", True):
        raise RuntimeError(
            "Reference verification failed: "
            f"{report['passed']}/{report['total']} references passed; "
            f"{report['likely_hallucinations']} likely hallucinations."
        )

    return {"validation_report": report, "run_id": run_id}


__all__ = ["citation_validator_node"]
