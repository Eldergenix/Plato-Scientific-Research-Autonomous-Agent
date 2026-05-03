"""Counter-evidence and research-gap signals for a run.

The R5 / Workflow-#11 / Workflow-#12 nodes write two artefacts into the
LangGraph state:

- ``state['counter_evidence_sources']`` — list of :class:`Source` records
  that the disconfirming-search node found.
- ``state['gaps']`` — list of ``{kind, description, severity, evidence}``
  dicts the gap-detector emits.

The worker either persists them to dedicated files
(``counter_evidence.json``, ``gaps.json``) under ``runs/<run_id>/`` or
folds them into ``manifest.extra``. We try the dedicated file first and
fall back to the manifest, which keeps the API stable across either
storage layout.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..domain.models import JsonObjectResponse
from ..settings import Settings, get_settings
from .manifests import _find_run_dir, _read_json, _user_id


router = APIRouter(tags=["research_signals"])

_RUN_GUARDS: dict[int | str, dict] = {
    404: {"description": "Run dir not found under any project root."},
    403: {"description": "Run belongs to a different tenant (auth-required mode)."},
}


# Steering phrases the counter-evidence node appends to the seed query.
# Mirrored here so the response can attribute each source to the trigger
# phrase that surfaced it; keep in sync with
# ``plato.langgraph_agents.counter_evidence._VARIANT_PHRASES``.
_TRIGGER_PHRASES = (
    "fail to replicate",
    "null result",
    "limitations",
    "do not support",
    "contradicts",
)


def _coerce_source(raw: Any) -> dict[str, Any] | None:
    """Reduce a Source-like dict to the fields the dashboard renders."""
    if not isinstance(raw, dict):
        return None
    sid = raw.get("id")
    title = raw.get("title")
    if not isinstance(sid, str) or not isinstance(title, str):
        return None
    return {
        "id": sid,
        "title": title,
        "venue": raw.get("venue"),
        "year": raw.get("year"),
        "doi": raw.get("doi"),
        "arxiv_id": raw.get("arxiv_id"),
        "url": raw.get("url"),
    }


def _coerce_gap(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind")
    description = raw.get("description")
    if not isinstance(kind, str) or not isinstance(description, str):
        return None
    severity = raw.get("severity", 0)
    if not isinstance(severity, (int, float)):
        severity = 0
    evidence = raw.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = []
    return {
        "kind": kind,
        "description": description,
        "severity": int(severity),
        "evidence": evidence,
    }


def _manifest_extra(run_dir: Path) -> dict[str, Any]:
    """Return ``manifest.extra`` if the manifest exists, else ``{}``."""
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        return {}
    payload = _read_json(manifest_path)
    if not isinstance(payload, dict):
        return {}
    extra = payload.get("extra")
    return extra if isinstance(extra, dict) else {}


def _check_tenant(run_dir: Path, request: Request, settings: Settings) -> None:
    """When auth is required, 403 if the caller's user differs from the run owner."""
    if not settings.is_auth_required:
        return
    caller = _user_id(request)
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        return
    payload = _read_json(manifest_path)
    owner = payload.get("user_id") if isinstance(payload, dict) else None
    if owner is None:
        return
    if caller != owner:
        raise HTTPException(
            status_code=403,
            detail={"code": "cross_tenant", "run_id": run_dir.name},
        )


@router.get(
    "/runs/{run_id}/counter_evidence",
    response_model=JsonObjectResponse,
    summary="Disconfirming sources for a run",
    responses=_RUN_GUARDS,
)
def get_counter_evidence(
    run_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return counter-evidence sources and the queries that surfaced them."""
    run_dir = _find_run_dir(settings.project_root, run_id)
    if run_dir is None:
        raise HTTPException(404, detail={"code": "run_not_found", "run_id": run_id})

    _check_tenant(run_dir, request, settings)

    payload: dict[str, Any] | None = None
    dedicated = run_dir / "counter_evidence.json"
    if dedicated.is_file():
        loaded = _read_json(dedicated)
        if isinstance(loaded, dict):
            payload = loaded
        elif isinstance(loaded, list):
            # Legacy shape: a bare list of sources.
            payload = {"sources": loaded, "queries_used": []}

    if payload is None:
        extra = _manifest_extra(run_dir)
        ce = extra.get("counter_evidence")
        if isinstance(ce, dict):
            payload = ce
        elif isinstance(ce, list):
            payload = {"sources": ce, "queries_used": []}

    if payload is None:
        return {"sources": [], "queries_used": []}

    raw_sources = payload.get("sources") or []
    sources = [s for s in (_coerce_source(r) for r in raw_sources) if s is not None]

    raw_queries = payload.get("queries_used") or []
    queries_used = [q for q in raw_queries if isinstance(q, str)]
    if not queries_used:
        # Backfill the trigger phrases so the dashboard can still render
        # the per-source "supporting query" badge.
        queries_used = list(_TRIGGER_PHRASES[:3])

    return {"sources": sources, "queries_used": queries_used}


@router.get(
    "/runs/{run_id}/gaps",
    response_model=JsonObjectResponse,
    summary="Detected research gaps for a run",
    responses=_RUN_GUARDS,
)
def get_gaps(
    run_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return the gap-detector's `{kind, description, severity, evidence}` rows."""
    run_dir = _find_run_dir(settings.project_root, run_id)
    if run_dir is None:
        raise HTTPException(404, detail={"code": "run_not_found", "run_id": run_id})

    _check_tenant(run_dir, request, settings)

    raw_gaps: list[Any] = []
    dedicated = run_dir / "gaps.json"
    if dedicated.is_file():
        loaded = _read_json(dedicated)
        if isinstance(loaded, list):
            raw_gaps = loaded
        elif isinstance(loaded, dict) and isinstance(loaded.get("gaps"), list):
            raw_gaps = loaded["gaps"]
    else:
        extra = _manifest_extra(run_dir)
        if isinstance(extra.get("gaps"), list):
            raw_gaps = extra["gaps"]

    gaps = [g for g in (_coerce_gap(r) for r in raw_gaps) if g is not None]
    return {"gaps": gaps}


__all__ = ["router"]
