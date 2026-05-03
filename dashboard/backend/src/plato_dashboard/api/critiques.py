"""Reviewer-panel critique + redraft-iteration endpoints.

The R6 reviewer panel writes per-axis critiques (methodology / statistics /
novelty / writing) into LangGraph state and the redraft loop tracks
``revision_state.iteration`` / ``max_iterations``. We surface both for the
``/runs/[runId]/reviews`` page in the dashboard.

Source-of-truth layering (first hit wins):

1. ``<run_dir>/critiques.json`` — the canonical sidecar the reviewer panel
   writes when it lands. Schema:

   ```
   {
     "critiques": {
       "methodology": {"severity": int, "issues": [...], "rationale": str},
       "statistics":  {...},
       "novelty":     {...},
       "writing":     {...}
     },
     "digest": {"max_severity": int, "issues": [...], "iteration": int},
     "revision_state": {"iteration": int, "max_iterations": int}
   }
   ```

2. ``<run_dir>/manifest.json`` — pre-sidecar runs stash the same shape under
   ``manifest["extra"]["critiques"]`` and ``manifest["extra"]["revision_state"]``
   so the dashboard works on legacy runs without a backfill.

We reuse ``_find_run_dir`` / ``_user_id`` / ``_read_json`` from the manifest
router so both endpoints share one disk-walk and one tenant-guard.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..domain.models import JsonObjectResponse
from ..settings import Settings, get_settings
from .manifests import _find_run_dir, _read_json, _user_id


router = APIRouter()


_AXES: tuple[str, ...] = ("methodology", "statistics", "novelty", "writing")


def _normalize_axes(raw: Any) -> dict[str, Any]:
    """Coerce arbitrary critique payloads into the 4-axis shape.

    Missing axes become ``None``; non-dict entries are dropped. The frontend
    renders ``null`` as the empty-state card, so silent drops are the
    correct user-visible behaviour.
    """
    out: dict[str, Any] = {axis: None for axis in _AXES}
    if not isinstance(raw, dict):
        return out
    for axis in _AXES:
        value = raw.get(axis)
        if isinstance(value, dict):
            out[axis] = value
    return out


def _enforce_tenant(run_dir: Path, requester: str | None) -> None:
    """Refuse cross-tenant access in required-mode.

    Mirrors the ``_enforce_run_tenant`` policy from server.py:

    - When ``PLATO_AUTH=enabled``, the run's manifest must exist and its
      ``user_id`` must match the requester. Anything else is 403.
    - Otherwise (legacy single-user mode), no-op.

    We only block on a positive mismatch — a missing manifest in optional
    mode is treated as "pre-multitenant run" and allowed through.
    """
    settings = get_settings()
    if not settings.is_auth_required and requester is None:
        return

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        if settings.is_auth_required:
            raise HTTPException(403, detail={"code": "run_forbidden"})
        return

    manifest = _read_json(manifest_path)
    if not isinstance(manifest, dict):
        return
    owner = manifest.get("user_id")
    if not isinstance(owner, str):
        return
    if requester is not None and owner != requester:
        raise HTTPException(403, detail={"code": "run_forbidden"})


@router.get("/runs/{run_id}/critiques", response_model=JsonObjectResponse)
def get_critiques(
    run_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    run_dir = _find_run_dir(settings.project_root, run_id)
    if run_dir is None:
        raise HTTPException(404, detail={"code": "run_not_found", "run_id": run_id})

    _enforce_tenant(run_dir, _user_id(request))

    sidecar = run_dir / "critiques.json"
    if sidecar.is_file():
        payload = _read_json(sidecar)
        if isinstance(payload, dict):
            return {
                "critiques": _normalize_axes(payload.get("critiques")),
                "digest": payload.get("digest")
                if isinstance(payload.get("digest"), dict)
                else None,
                "revision_state": payload.get("revision_state")
                if isinstance(payload.get("revision_state"), dict)
                else None,
            }

    manifest_path = run_dir / "manifest.json"
    if manifest_path.is_file():
        manifest = _read_json(manifest_path)
        extra = manifest.get("extra") if isinstance(manifest, dict) else None
        if isinstance(extra, dict):
            return {
                "critiques": _normalize_axes(extra.get("critiques")),
                "digest": extra.get("digest")
                if isinstance(extra.get("digest"), dict)
                else None,
                "revision_state": extra.get("revision_state")
                if isinstance(extra.get("revision_state"), dict)
                else None,
            }

    return {"critiques": {}, "digest": None, "revision_state": None}


# Architectural-plan alias. The plan document specifies
# ``/api/v1/runs/{run_id}/reviews`` as the route name; the existing
# implementation lives under ``/critiques``. Rather than break clients
# that already use ``/critiques``, expose ``/reviews`` as a sibling
# alias that delegates to the same handler.
@router.get("/runs/{run_id}/reviews", response_model=JsonObjectResponse)
def get_reviews(
    run_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Alias for ``GET /runs/{run_id}/critiques`` (same payload)."""
    return get_critiques(run_id=run_id, request=request, settings=settings)


__all__ = ["router"]
