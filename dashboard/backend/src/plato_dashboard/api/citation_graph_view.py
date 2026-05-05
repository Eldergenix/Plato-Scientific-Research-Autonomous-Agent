"""Citation-graph view endpoint.

Exposes ``GET /api/v1/runs/{run_id}/citation_graph`` so the dashboard can
visualise the 1-hop expansion produced by
``plato.retrieval.citation_graph.expand_citations``.

The route reads two on-disk artefacts (in priority order):

1. ``<run_dir>/citation_graph.json`` — canonical, written by the retrieval
   pipeline.
2. ``<run_dir>/manifest.json`` with ``manifest.extra.citation_graph`` —
   fallback for older runs that piggy-backed on the manifest.

Both inputs are coerced into the same response shape so the frontend
can render either source uniformly.

The router is intentionally local here. ``server.py`` is sealed by spec,
so :mod:`plato_dashboard.api.__init__` wraps ``create_app`` to attach
this router after construction.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..domain.models import JsonObjectResponse
from ..settings import Settings, get_settings


router = APIRouter()


# --------------------------------------------------------------------------- #
# Helpers — delegate to the manifest router so tenant scoping stays in one
# place. The bare ``X-Plato-User`` lookup at this layer used to bypass
# ``auth._is_safe_user_id`` and the per-user namespace; the imports below
# fix both leaks at once.
# --------------------------------------------------------------------------- #
from ..auth import auth_required, extract_user_id as _user_id  # noqa: E402
from .manifests import _find_run_dir  # noqa: E402


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "citation_graph_corrupt", "message": str(exc)},
        ) from exc


# --------------------------------------------------------------------------- #
# Payload normalisation
# --------------------------------------------------------------------------- #
def _empty_payload() -> dict:
    return {
        "seeds": [],
        "expanded": [],
        "edges": [],
        "stats": {
            "seed_count": 0,
            "expanded_count": 0,
            "edge_count": 0,
            "duplicates_filtered": 0,
        },
    }


def _coerce_node(raw: Any) -> dict | None:
    """Best-effort conversion of one source-record dict into the node shape.

    Producers vary: some write the raw OpenAlex ``Source`` (with
    ``openalex_id``), others write a slim ``{id, title}`` projection. We
    accept either and fill missing fields with ``None``.
    """
    if not isinstance(raw, dict):
        return None
    node_id = raw.get("id") or raw.get("openalex_id") or raw.get("doi")
    if not node_id:
        return None
    return {
        "id": str(node_id),
        "title": str(raw.get("title") or "(untitled)"),
        "doi": raw.get("doi") if isinstance(raw.get("doi"), str) else None,
        "openalex_id": (
            raw.get("openalex_id") if isinstance(raw.get("openalex_id"), str) else None
        ),
    }


def _coerce_edge(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    src = raw.get("from") or raw.get("source")
    dst = raw.get("to") or raw.get("target")
    kind = raw.get("kind") or raw.get("direction") or "references"
    if not src or not dst:
        return None
    if kind not in ("references", "cited_by"):
        kind = "references"
    return {"from": str(src), "to": str(dst), "kind": kind}


def _normalise_payload(raw: Any) -> dict:
    """Coerce whatever shape we read off disk into the API contract.

    The retrieval pipeline writes a permissive structure — we tighten it
    here so the frontend never sees half-typed records.
    """
    if not isinstance(raw, dict):
        return _empty_payload()

    seeds_raw = raw.get("seeds") or []
    expanded_raw = raw.get("expanded") or raw.get("expansion") or []
    edges_raw = raw.get("edges") or []
    stats_raw = raw.get("stats") or {}

    seeds = [n for n in (_coerce_node(s) for s in seeds_raw) if n is not None]
    expanded = [n for n in (_coerce_node(e) for e in expanded_raw) if n is not None]

    # Drop expanded nodes that collide with a seed id — the retrieval
    # layer already does this, but defending here makes the response
    # self-consistent even if someone hand-edits the JSON.
    seed_ids = {n["id"] for n in seeds}
    duplicates_filtered = int(stats_raw.get("duplicates_filtered") or 0)
    pre_dedup = len(expanded)
    expanded = [n for n in expanded if n["id"] not in seed_ids]
    duplicates_filtered += pre_dedup - len(expanded)

    valid_ids = seed_ids | {n["id"] for n in expanded}
    edges: list[dict] = []
    for raw_edge in edges_raw:
        edge = _coerce_edge(raw_edge)
        if edge is None:
            continue
        if edge["from"] not in valid_ids or edge["to"] not in valid_ids:
            continue
        edges.append(edge)

    return {
        "seeds": seeds,
        "expanded": expanded,
        "edges": edges,
        "stats": {
            "seed_count": len(seeds),
            "expanded_count": len(expanded),
            "edge_count": len(edges),
            "duplicates_filtered": duplicates_filtered,
        },
    }


def _read_graph_payload(run_dir: Path) -> dict:
    """Load the canonical file, falling back to the manifest sidecar."""
    canonical = run_dir / "citation_graph.json"
    if canonical.is_file():
        return _normalise_payload(_read_json(canonical))

    manifest_path = run_dir / "manifest.json"
    if manifest_path.is_file():
        manifest = _read_json(manifest_path)
        if isinstance(manifest, dict):
            extra = manifest.get("extra")
            if isinstance(extra, dict) and isinstance(extra.get("citation_graph"), dict):
                return _normalise_payload(extra["citation_graph"])

    return _empty_payload()


def _check_tenant(run_dir: Path, request_user: str | None) -> None:
    """403 if the run's manifest disagrees with the requesting user.

    Posture matches the manifest router:
    - Auth required + header missing → 401-equivalent (caller never gets
      here because ``extract_user_id`` returns ``None`` and the route
      404s through the empty per-user namespace).
    - Manifest with a ``user_id`` that doesn't match → 403.
    - Manifest with no ``user_id`` (legacy un-namespaced run) → 403 only
      when auth is required; otherwise allowed (single-user install).
    """
    manifest_path = run_dir / "manifest.json"
    manifest: dict[str, Any] | None = None
    if manifest_path.is_file():
        try:
            loaded = json.loads(manifest_path.read_text())
            if isinstance(loaded, dict):
                manifest = loaded
        except json.JSONDecodeError:
            manifest = None

    owner = (manifest or {}).get("user_id")
    if isinstance(owner, str) and owner:
        if request_user is None or owner != request_user:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "cross_tenant_blocked",
                    "message": "This run belongs to a different user.",
                },
            )
        return

    # Manifest missing or has no user_id — refuse in auth-required mode so
    # legacy runs don't become world-readable on a multi-tenant deploy.
    if auth_required():
        raise HTTPException(
            status_code=403,
            detail={"code": "run_forbidden", "message": "Run has no owner record."},
        )


# --------------------------------------------------------------------------- #
# Route
# --------------------------------------------------------------------------- #
@router.get("/runs/{run_id}/citation_graph", response_model=JsonObjectResponse)
def get_citation_graph(
    run_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    requester = _user_id(request)
    run_dir = _find_run_dir(settings.project_root, run_id, requester)
    if run_dir is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "run_not_found", "run_id": run_id},
        )
    _check_tenant(run_dir, requester)
    return _read_graph_payload(run_dir)


__all__ = ["router"]
