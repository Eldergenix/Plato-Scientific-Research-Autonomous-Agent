"""Novelty score endpoint.

Workflow #9 (``plato/novelty/{embedding_scorer,composite_scorer}.py``)
emits a scalar novelty score per run. We expose it here so the dashboard
can render the F4 panel. The score has two underlying signals — an LLM
judge and an embedding-distance score — plus a composite. The frontend
shows all three so a user can see whether the two methods agree.

We prefer ``<run_dir>/novelty.json``; fall back to
``manifest.extra.novelty``; otherwise return an all-null 200 so the
panel can render its empty state instead of a red error card.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import auth_required, extract_user_id
from ..domain.models import JsonObjectResponse
from ..settings import Settings, get_settings
from .manifests import _find_run_dir, _read_json


router = APIRouter()


_EMPTY_PAYLOAD: dict[str, Any] = {
    "score": None,
    "max_similarity": None,
    "nearest_source_id": None,
    "llm_score": None,
    "embedding_score": None,
    "agreement": None,
}


def _load_manifest(run_dir: Path) -> dict | None:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        return json.loads(manifest_path.read_text())
    except json.JSONDecodeError:
        return None


def _enforce_run_tenant(
    run_dir: Path, requester_user_id: str | None
) -> None:
    """Mirror the cross-tenant guard used by retrieval_summary / server.py."""
    if requester_user_id is None and not auth_required():
        return

    manifest = _load_manifest(run_dir)
    manifest_user = manifest.get("user_id") if isinstance(manifest, dict) else None
    if not isinstance(manifest_user, str):
        manifest_user = None

    if manifest_user is None:
        if auth_required():
            raise HTTPException(403, detail={"code": "run_forbidden"})
        return

    if manifest_user != requester_user_id:
        status = 403 if auth_required() else 404
        raise HTTPException(
            status,
            detail={
                "code": "run_forbidden" if status == 403 else "run_not_found"
            },
        )


def _coerce_unit(value: Any) -> float | None:
    """Coerce a number to a float in [0, 1]; ``None`` if the input is junk."""
    if value is None:
        return None
    if isinstance(value, bool):  # bool is a subclass of int — guard explicitly.
        return None
    if not isinstance(value, (int, float)):
        return None
    if value != value:  # NaN
        return None
    return max(0.0, min(1.0, float(value)))


def _coerce_agreement(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _coerce_source_id(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _build_payload(raw: dict) -> dict[str, Any]:
    return {
        "score": _coerce_unit(raw.get("score")),
        "max_similarity": _coerce_unit(raw.get("max_similarity")),
        "nearest_source_id": _coerce_source_id(raw.get("nearest_source_id")),
        "llm_score": _coerce_unit(raw.get("llm_score")),
        "embedding_score": _coerce_unit(raw.get("embedding_score")),
        "agreement": _coerce_agreement(raw.get("agreement")),
    }


def _from_manifest_extra(manifest: dict) -> dict[str, Any] | None:
    extra = manifest.get("extra")
    if not isinstance(extra, dict):
        return None
    novelty = extra.get("novelty")
    if not isinstance(novelty, dict):
        return None
    return _build_payload(novelty)


@router.get("/runs/{run_id}/novelty", response_model=JsonObjectResponse)
def get_novelty(
    run_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    requester = extract_user_id(request)
    run_dir = _find_run_dir(settings.project_root, run_id)
    if run_dir is None:
        raise HTTPException(404, detail={"code": "run_not_found", "run_id": run_id})

    _enforce_run_tenant(run_dir, requester)

    novelty_path = run_dir / "novelty.json"
    if novelty_path.is_file():
        raw = _read_json(novelty_path)
        if isinstance(raw, dict):
            return _build_payload(raw)

    manifest = _load_manifest(run_dir)
    if manifest is not None:
        from_extra = _from_manifest_extra(manifest)
        if from_extra is not None:
            return from_extra

    return dict(_EMPTY_PAYLOAD)


__all__ = ["router"]
