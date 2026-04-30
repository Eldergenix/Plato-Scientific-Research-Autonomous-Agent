"""Paper metadata sidecar (Workflow #18).

Drops a structured ``paper/metadata.json`` next to the generated PDF/TeX
so downstream tools (the dashboard, indexers, training-data pipelines)
have a single, machine-readable view of what's in the paper without
having to parse LaTeX.

Idempotent: write_paper_metadata can be called repeatedly and will leave
``paper/metadata.json`` reflecting whatever the latest call produced.
The write is atomic (temp + ``os.replace``) so a crash never leaves a
half-written sidecar behind.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# Section-name aliases we accept in the input ``paper_state`` dict.
_SECTION_KEYS = {
    "abstract": ("abstract",),
    "intro": ("intro", "introduction"),
    "methods": ("methods", "method"),
    "results": ("results",),
    "conclusions": ("conclusions", "conclusion"),
}

# Cap each section excerpt at ~4 KB so the sidecar stays small even for
# verbose drafts. Downstream consumers read the LaTeX for the full text.
_EXCERPT_CHARS = 4096


def _excerpt(text: Any, limit: int = _EXCERPT_CHARS) -> str:
    if not isinstance(text, str):
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _first(state: dict, names: Iterable[str]) -> Any:
    for n in names:
        if n in state and state[n]:
            return state[n]
    paper = state.get("paper")
    if isinstance(paper, dict):
        for n in names:
            if n in paper and paper[n]:
                return paper[n]
    return ""


def _section_excerpts(paper_state: dict) -> dict[str, str]:
    return {
        canonical: _excerpt(_first(paper_state, aliases))
        for canonical, aliases in _SECTION_KEYS.items()
    }


def _figure_paths(paper_state: dict) -> list[str]:
    candidates: list[Any] = []
    for key in ("plot_paths", "figures", "plots"):
        v = paper_state.get(key)
        if v:
            candidates = list(v) if isinstance(v, (list, tuple)) else [v]
            break
    if not candidates:
        files = paper_state.get("files")
        if isinstance(files, dict):
            v = files.get("plot_paths") or files.get("Plots")
            if v:
                candidates = list(v) if isinstance(v, (list, tuple)) else [v]
    return [str(p) for p in candidates if p]


def _normalize_references(references: list[Any] | None) -> list[dict[str, Any]]:
    """Pull DOI / arxiv / title fields out of whatever the caller hands us.

    Accepts a list of dicts (preferred), pydantic models with
    ``model_dump``, or plain strings (treated as titles).
    """
    out: list[dict[str, Any]] = []
    if not references:
        return out
    for ref in references:
        if hasattr(ref, "model_dump") and callable(ref.model_dump):
            ref = ref.model_dump()
        if isinstance(ref, str):
            out.append({"title": ref})
            continue
        if not isinstance(ref, dict):
            continue
        entry: dict[str, Any] = {}
        for field in ("doi", "arxiv_id", "arxiv", "title", "authors", "year", "url", "venue"):
            v = ref.get(field)
            if v:
                entry[field] = v
        if entry:
            out.append(entry)
    return out


def _validation_summary(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not report:
        return None
    summary: dict[str, Any] = {}
    for field in (
        "claims_total",
        "claims_supported",
        "claims_unsupported",
        "citations_total",
        "citations_valid",
        "citations_invalid",
        "score",
        "passed",
        "issues",
    ):
        if field in report:
            summary[field] = report[field]
    # Always carry the raw report under a stable key so we don't lose
    # caller-specific extras.
    summary["raw"] = report
    return summary


def write_paper_metadata(
    project_dir: Path | str,
    paper_state: dict,
    references: list | None = None,
    validation_report: dict | None = None,
) -> Path:
    """Write ``<project_dir>/paper/metadata.json`` and return its path.

    The write is atomic via ``os.replace``. Calling this twice in a row
    leaves the same final bytes (less the embedded ``generated_at``
    timestamp), and the second call never observes the first one in
    half-written form.
    """
    project_dir = Path(project_dir)
    paper_dir = project_dir / "paper"
    paper_dir.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sections": _section_excerpts(paper_state or {}),
        "figures": _figure_paths(paper_state or {}),
        "references": _normalize_references(references),
        "validation": _validation_summary(validation_report),
    }

    target = paper_dir / "metadata.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.replace(tmp, target)
    return target


__all__ = ["write_paper_metadata"]
