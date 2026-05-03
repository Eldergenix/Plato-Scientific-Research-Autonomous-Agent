"""Retrieval source breakdown endpoint.

R4 fans out to six retrieval adapters (arxiv, openalex, crossref, ads,
pubmed, semantic_scholar). The orchestrator dedupes results before they
hit the manifest, which means the dashboard never sees per-adapter
contribution counts. This route surfaces them.

We prefer a dedicated ``<run_dir>/retrieval_summary.json`` when the
orchestrator has written one; otherwise we walk
``manifest.extra.retrieval_log`` if it has the right shape. When neither
is present we return an empty 200 — the panel renders its own empty
state instead of the page showing a red error.
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
    "by_adapter": [],
    "total_unique": 0,
    "total_returned": 0,
    "queries": [],
    "samples": [],
}


def _load_manifest(run_dir: Path) -> dict | None:
    """Return the parsed manifest or ``None`` if it isn't on disk yet."""
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
    """Refuse cross-tenant run access — same shape as the server-level guard.

    The retrieval-summary file lives next to ``manifest.json``; we read
    the manifest's ``user_id`` field to decide whether the requester is
    allowed to see the summary. Single-user mode (no header, auth not
    required) is a no-op so legacy installs keep working.
    """
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


def _coerce_adapter_row(record: Any) -> dict | None:
    """Validate a single ``{adapter, count, deduped}`` shape."""
    if not isinstance(record, dict):
        return None
    adapter = record.get("adapter")
    count = record.get("count")
    deduped = record.get("deduped", 0)
    if not isinstance(adapter, str) or not adapter:
        return None
    if not isinstance(count, int) or count < 0:
        return None
    if not isinstance(deduped, int) or deduped < 0:
        deduped = 0
    return {"adapter": adapter, "count": count, "deduped": deduped}


def _coerce_sample(record: Any) -> dict | None:
    if not isinstance(record, dict):
        return None
    source_id = record.get("source_id") or record.get("id")
    title = record.get("title", "")
    adapter = record.get("adapter", "")
    if not isinstance(source_id, str) or not source_id:
        return None
    return {
        "source_id": source_id,
        "title": str(title) if title is not None else "",
        "adapter": str(adapter) if adapter is not None else "",
    }


def _build_payload(raw: dict) -> dict[str, Any]:
    """Normalise an arbitrary dict into our response contract."""
    by_adapter_in = raw.get("by_adapter", [])
    rows: list[dict] = []
    if isinstance(by_adapter_in, list):
        for record in by_adapter_in:
            row = _coerce_adapter_row(record)
            if row is not None:
                rows.append(row)
    rows.sort(key=lambda r: r["count"], reverse=True)

    total_returned = raw.get("total_returned")
    if not isinstance(total_returned, int):
        total_returned = sum(r["count"] for r in rows)

    total_unique = raw.get("total_unique")
    if not isinstance(total_unique, int):
        # Fallback: returned minus the deduped overlap.
        deduped_total = sum(r["deduped"] for r in rows)
        total_unique = max(0, total_returned - deduped_total)

    queries_in = raw.get("queries", [])
    queries: list[str] = []
    if isinstance(queries_in, list):
        for q in queries_in:
            if isinstance(q, str):
                queries.append(q)

    samples_in = raw.get("samples", [])
    samples: list[dict] = []
    if isinstance(samples_in, list):
        for record in samples_in[:5]:
            sample = _coerce_sample(record)
            if sample is not None:
                samples.append(sample)

    return {
        "by_adapter": rows,
        "total_unique": total_unique,
        "total_returned": total_returned,
        "queries": queries,
        "samples": samples,
    }


def _from_manifest_extra(manifest: dict) -> dict[str, Any] | None:
    """Pull a retrieval-shaped dict out of ``manifest.extra.retrieval_log``."""
    extra = manifest.get("extra")
    if not isinstance(extra, dict):
        return None
    log = extra.get("retrieval_log")
    if not isinstance(log, dict):
        return None
    # ``retrieval_log`` is the same shape as the dedicated file, so no
    # special-casing needed — _build_payload tolerates partial input.
    return _build_payload(log)


@router.get("/runs/{run_id}/retrieval_summary", response_model=JsonObjectResponse)
def get_retrieval_summary(
    run_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    requester = extract_user_id(request)
    run_dir = _find_run_dir(settings.project_root, run_id)
    if run_dir is None:
        raise HTTPException(404, detail={"code": "run_not_found", "run_id": run_id})

    _enforce_run_tenant(run_dir, requester)

    summary_path = run_dir / "retrieval_summary.json"
    if summary_path.is_file():
        raw = _read_json(summary_path)
        if isinstance(raw, dict):
            return _build_payload(raw)

    manifest = _load_manifest(run_dir)
    if manifest is not None:
        from_extra = _from_manifest_extra(manifest)
        if from_extra is not None:
            return from_extra

    return dict(_EMPTY_PAYLOAD)


__all__ = ["router"]
