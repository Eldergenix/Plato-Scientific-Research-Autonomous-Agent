"""Claim extraction LangGraph node (Phase 2, R5 stream B).

This node consumes the literature gathered earlier in the graph and extracts
atomic factual claims from each source's abstract. Each claim is materialised
as a :class:`plato.state.models.Claim` with provenance back to its
``source_id`` and a character-offset ``quote_span`` into the abstract — the
foundation that downstream evidence-link reasoning (R5 stream A) consumes.

Design notes
------------
- Inputs: prefer ``state["sources"]`` (a list of ``Source`` Pydantic objects
  produced by the new retrieval adapters) when present. Fall back to the
  legacy ``state["literature"]["papers"]`` list of free-form paper-info
  strings produced by the existing ``semantic_scholar`` node so this node
  composes either way.
- LLM call: uses ``LLM_call_stream`` from ``..paper_agents.tools``, exactly
  like ``literature.semantic_scholar`` and ``literature.novelty_decider``.
  The retry loop (3 tries) guards against malformed JSON output.
- Quote span: ``span_text`` from the LLM is matched verbatim against the
  abstract via ``str.find``. If unfindable, ``quote_span`` is left ``None``
  rather than fabricated.
- State update: this node returns ``{"claims": existing + new}`` so prior
  claims (e.g. drafted by other nodes) are preserved.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig

import json5

from .parameters import GraphState
from .prompts import claim_extraction_prompt
from ..paper_agents.tools import LLM_call_stream  # noqa: F401  (re-export point for tests)
from ..state.models import Claim, Source


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CLAIM_RETRIES = 3


def _parse_claims_json(text: str) -> list[dict[str, Any]]:
    """Extract a JSON array of claim dicts from an LLM response.

    The shared ``json_parser3`` helper only locates ``{...}`` objects, but the
    claim-extraction prompt asks for a top-level JSON array. We try a few
    strategies in order: fenced ```json blocks, fenced generic blocks, raw
    array search, then ``json5`` for slightly malformed output.
    """

    # 1) ```json [ ... ] ```
    m = re.search(r"```json\s*(\[.*?\])\s*```", text, re.DOTALL | re.IGNORECASE)
    if not m:
        # 2) ``` [ ... ] ``` (any fenced block)
        m = re.search(r"```\s*(\[.*?\])\s*```", text, re.DOTALL)
    if not m:
        # 3) bare top-level array, anywhere in the text
        m = re.search(r"(\[\s*(?:\{.*?\}\s*,?\s*)*\])", text, re.DOTALL)
    if not m:
        raise ValueError("No JSON array found in LLM response.")

    payload = m.group(1)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        # tolerant fallback for trailing commas / single quotes
        data = json5.loads(payload)

    if not isinstance(data, list):
        raise ValueError("Expected a JSON array of claim objects.")
    return data


def _abstract_for(source_or_str: Source | str) -> str:
    """Resolve the text we'll extract claims from."""
    if isinstance(source_or_str, Source):
        return source_or_str.abstract or ""
    # legacy paper-info string from semantic_scholar: try to slice the abstract
    text = str(source_or_str)
    m = re.search(r"Abstract:\s*(.*?)(?:\nURL:|\narXiv link:|\npdf:|$)", text, re.DOTALL)
    return m.group(1).strip() if m else text


def _source_id_for(source_or_str: Source | str, fallback_index: int) -> str:
    if isinstance(source_or_str, Source):
        return source_or_str.id
    # synthesise a stable-ish id for legacy strings
    return f"literature-{fallback_index}"


def _coerce_quote_span(abstract: str, span_text: str | None) -> tuple[int, int] | None:
    if not span_text or not abstract:
        return None
    start = abstract.find(span_text)
    if start < 0:
        return None
    return (start, start + len(span_text))


def _iter_inputs(state: GraphState) -> list[Source | str]:
    """Pick sources or fall back to the legacy paper-info strings."""
    sources = state.get("sources") if isinstance(state, dict) else None
    if sources:
        return list(sources)

    literature = state.get("literature") if isinstance(state, dict) else None
    if literature and literature.get("papers"):
        papers = literature["papers"]
        if isinstance(papers, list):
            return [p for p in papers if p]
    return []


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

async def claim_extractor(state: GraphState, config: Optional[RunnableConfig] = None):
    # Note: ``Optional[RunnableConfig]`` (not ``RunnableConfig | None``)
    # because LangGraph's annotation introspection only whitelists the
    # ``Optional[...]`` and bare-``RunnableConfig`` forms; the PEP-604
    # union form trips a UserWarning on every ``add_node`` call.
    """LangGraph node: extract claims from each source/abstract in ``state``.

    Returns a partial state update with the appended ``claims`` list. The
    function is async to match the LangGraph convention for I/O-bound nodes,
    even though ``LLM_call_stream`` is synchronous — this keeps the signature
    compatible with the rest of the Phase 2 graph.
    """

    inputs = _iter_inputs(state)
    existing = list(state.get("claims") or []) if isinstance(state, dict) else []
    new_claims: list[Claim] = []

    for idx, item in enumerate(inputs):
        abstract = _abstract_for(item)
        if not abstract:
            continue

        source_id = _source_id_for(item, idx)
        prompt = claim_extraction_prompt(state, abstract)

        parsed: list[dict[str, Any]] | None = None
        for attempt in range(_CLAIM_RETRIES):
            state, raw = LLM_call_stream(prompt, state, node_name="claim_extractor")
            try:
                parsed = _parse_claims_json(raw)
                break
            except Exception:
                # brief backoff then retry; mirrors the literature.py pattern
                time.sleep(0.1)
                parsed = None

        if not parsed:
            # 3 failed attempts → skip this source rather than abort the graph
            continue

        for claim_dict in parsed:
            text = (claim_dict.get("text") or "").strip()
            if not text:
                continue
            span_text = claim_dict.get("span_text")
            quote_span = _coerce_quote_span(abstract, span_text)
            new_claims.append(
                Claim(
                    id=uuid.uuid4().hex[:12],
                    text=text,
                    source_id=source_id,
                    quote_span=quote_span,
                    section="abstract",
                )
            )

    return {"claims": existing + new_claims}


__all__ = ["claim_extractor"]
