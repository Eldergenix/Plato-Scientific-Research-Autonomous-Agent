"""PRISMA-style systematic literature review screening node.

Runs after :func:`literature_summary` whenever
``state['literature']['run_slr']`` is True. The node consumes the
sources already retrieved by :func:`semantic_scholar` (so we do not
re-hit any external APIs), asks an LLM to score each paper 1-10 and
group it into a subtopic, and writes both a structured JSON report
and a human-readable Markdown summary into the run folder.

The PRISMA stages map onto the existing graph as follows:

* Identification → existing retrieval adapters (``semantic_scholar``).
* Screening      → this node (LLM scores + include/exclude decision).
* Eligibility    → this node (subtopic grouping; excluded papers
                   carry a short ``exclude_reason``).
* Inclusion      → ``state['literature']['slr']['included']`` plus the
                   regenerated summary in ``input_files/slr.md``.

Design constraints:

* Re-uses Plato's safety wrappers so untrusted abstract text is
  surfaced inside ``<external>`` markers and the prompt's instructions
  cannot be hijacked.
* Caps the screening batch at 50 papers — large enough for any sane
  retrieval cap but small enough that the prompt fits comfortably
  inside a single LLM call.
* Returns a partial state update so the SQLite checkpointer captures
  the SLR output for resume.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from ..paper_agents.tools import LLM_call_stream, json_parser3
from ..safety import wrap_external
from .parameters import GraphState
from .prompts import slr_screening_prompt


logger = logging.getLogger(__name__)


# Cap batch size so the screening prompt always fits in a single call.
# semantic_scholar caps retrieval at 20 today, but the cap is configurable
# and we want headroom rather than a silent truncation.
_SLR_PAPER_CAP = 50


def _render_papers_block(sources: list[Any]) -> tuple[str, list[dict[str, Any]]]:
    """Render retrieved sources as a numbered block + return per-id metadata.

    The metadata list mirrors the ids exposed in the prompt so the
    downstream JSON output (``screened[i].id``) can be joined back to
    the original ``Source`` records when writing the JSON report.
    """
    rows: list[str] = []
    metadata: list[dict[str, Any]] = []
    for i, paper in enumerate(sources[:_SLR_PAPER_CAP], 1):
        title = getattr(paper, "title", "") or ""
        year = getattr(paper, "year", "") or ""
        authors = ", ".join(getattr(paper, "authors", []) or [])
        abstract = getattr(paper, "abstract", "") or ""
        url = getattr(paper, "url", "") or ""

        wrapped_abstract = wrap_external(abstract, "abstract") if abstract else "(no abstract)"
        rows.append(
            f"[{i}] {title} ({year})\n"
            f"    Authors: {authors}\n"
            f"    URL: {url}\n"
            f"    Abstract: {wrapped_abstract}"
        )
        metadata.append({
            "id": i,
            "title": title,
            "year": year,
            "authors": authors,
            "url": url,
            "source_id": getattr(paper, "id", None),
        })
    return "\n\n".join(rows), metadata


def _empty_slr_result(reason: str) -> dict[str, Any]:
    """Shape used when the run skips screening (no sources, parse failure)."""
    return {
        "status": "skipped",
        "reason": reason,
        "screened": [],
        "subtopics": [],
        "included": [],
        "excluded": [],
    }


def slr_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    """Screen the retrieved corpus, group by subtopic, persist the report."""

    print("Running PRISMA-style SLR screening...", end="", flush=True)

    literature = state['literature']
    raw_sources = literature.get("sources")
    sources: list[Any] = list(raw_sources) if isinstance(raw_sources, list) else []

    if not sources:
        logger.info("slr_node: no sources to screen; emitting skipped report.")
        slr_result = _empty_slr_result("no sources retrieved")
        return {"literature": {**literature, "slr": slr_result}}

    papers_block, metadata = _render_papers_block(sources)
    PROMPT = slr_screening_prompt(state, papers_block)

    state, raw = LLM_call_stream(PROMPT, state, node_name="slr_node")

    try:
        parsed = json_parser3(raw)
    except Exception as exc:  # parser raises on malformed JSON
        logger.warning("slr_node: failed to parse LLM JSON output (%s).", exc)
        slr_result = _empty_slr_result(f"json parse failed: {exc}")
        return {"literature": {**literature, "slr": slr_result}}

    screened = parsed.get("screened", []) if isinstance(parsed, dict) else []
    subtopics = parsed.get("subtopics", []) if isinstance(parsed, dict) else []

    # Join the LLM scores back to the source metadata.
    by_id = {m["id"]: m for m in metadata}
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row in screened:
        if not isinstance(row, dict):
            continue
        pid = row.get("id")
        meta = by_id.get(pid, {})
        merged = {
            **meta,
            "score": row.get("score"),
            "subtopic": row.get("subtopic", ""),
            "rationale": row.get("rationale", ""),
            "exclude_reason": row.get("exclude_reason", ""),
        }
        if row.get("include"):
            included.append(merged)
        else:
            excluded.append(merged)

    slr_result = {
        "status": "ok",
        "screened": screened,
        "subtopics": subtopics,
        "included": included,
        "excluded": excluded,
    }

    # Persist the structured JSON report (machine-consumable) and the
    # human-readable Markdown summary (consumed by writing-stage prompts
    # via state['literature']['summary'] downstream consumers).
    folder = state['files'].get("Folder") if state.get('files') else None
    if folder:
        json_path = f"{folder}/literature_output/slr.json"
        with open(json_path, "w") as f:
            json.dump(slr_result, f, indent=2, ensure_ascii=False)

        md_path = f"{folder}/input_files/slr.md"
        with open(md_path, "w") as f:
            f.write("# Systematic Literature Review (PRISMA screening)\n\n")
            f.write(f"- Retrieved: {len(metadata)}\n")
            f.write(f"- Included: {len(included)}\n")
            f.write(f"- Excluded: {len(excluded)}\n\n")

            if subtopics:
                f.write("## Subtopics\n\n")
                for st in subtopics:
                    if not isinstance(st, dict):
                        continue
                    name = st.get("name", "(unnamed)")
                    ids = st.get("paper_ids", []) or []
                    f.write(f"- **{name}** — {len(ids)} paper(s)\n")
                f.write("\n")

            if included:
                f.write("## Included papers\n\n")
                for p in sorted(included, key=lambda r: -(r.get("score") or 0)):
                    f.write(
                        f"- [{p.get('score', '?')}] {p.get('title', '')} "
                        f"({p.get('year', '')}) — *{p.get('subtopic', '')}*\n"
                        f"  {p.get('rationale', '')}\n"
                    )

    print(f"done {state['tokens']['ti']} {state['tokens']['to']}")

    return {"literature": {**literature, "slr": slr_result}}
