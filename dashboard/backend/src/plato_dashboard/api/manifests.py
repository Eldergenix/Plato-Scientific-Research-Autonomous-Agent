"""Run manifest / evidence matrix / validation report endpoints.

These three routes expose the per-run reproducibility artefacts that
``plato/state/manifest.py`` and the Phase 2 retrieval pipeline write
into ``<project_root>/runs/<run_id>/`` (or, for legacy projects, into
``<project_root>/<project>/runs/<run_id>/``). The dashboard renders them
on ``/runs/[runId]``.

The router is intentionally small: each endpoint is a file lookup and a
JSON parse. We accept either layout — flat ``runs/<id>/`` directly under
``project_root``, or nested ``<project>/runs/<id>/`` — so the dashboard
works regardless of how the user runs Plato.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..settings import Settings, get_settings


router = APIRouter()


def _user_id(req: Request) -> str | None:
    """Extract the requester's user id from ``X-Plato-User``.

    Delegates to the canonical ``plato_dashboard.auth.extract_user_id``
    so this router cannot drift from the rest of the dashboard's auth
    contract (validation regex, header name, fallback rules).
    """
    from ..auth import extract_user_id

    return extract_user_id(req)


def _enforce_tenant(run_dir: Path, run_id: str, requester: str | None) -> None:
    """Refuse cross-tenant manifest reads.

    Behaviour mirrors ``server._enforce_run_tenant``:

    - If the run has no manifest yet, allow when auth isn't required.
    - If the manifest's ``user_id`` differs from the requester, raise
      403 (auth required) or 404 (auth optional, to avoid leaking the
      run's existence).
    """
    from ..auth import auth_required as _auth_required

    required = _auth_required()
    if requester is None and not required:
        return

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        if required:
            raise HTTPException(403, detail={"code": "run_forbidden"})
        return

    try:
        manifest_user = json.loads(manifest_path.read_text()).get("user_id")
    except json.JSONDecodeError:
        # A corrupt manifest is the manifest endpoint's own problem to
        # surface — for tenant enforcement, fail closed.
        raise HTTPException(403, detail={"code": "run_forbidden"})

    if manifest_user is None:
        # Pre-multi-tenant runs: allow only when auth isn't required.
        if required:
            raise HTTPException(403, detail={"code": "run_forbidden"})
        return

    if manifest_user != requester:
        status = 403 if required else 404
        code = "run_forbidden" if status == 403 else "run_not_found"
        raise HTTPException(status, detail={"code": code, "run_id": run_id})


def _find_run_dir(project_root: Path, run_id: str) -> Path | None:
    """Locate ``runs/<run_id>`` under ``project_root``.

    Looks at two layouts:
    - ``<project_root>/runs/<run_id>/`` — when the project root *is* the
      project directory (single-project install).
    - ``<project_root>/<project>/runs/<run_id>/`` — when the dashboard
      manages multiple projects (the normal case).

    Returns the first match or ``None``.
    """
    if not project_root.exists():
        return None

    flat = project_root / "runs" / run_id
    if flat.is_dir():
        return flat

    # Multi-project layout: scan one level deep.
    for child in project_root.iterdir():
        if not child.is_dir():
            continue
        candidate = child / "runs" / run_id
        if candidate.is_dir():
            return candidate
    return None


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "manifest_corrupt", "message": str(exc)},
        ) from exc


@router.get("/runs/{run_id}/manifest")
def get_manifest(
    run_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    requester = _user_id(request)
    run_dir = _find_run_dir(settings.project_root, run_id)
    if run_dir is None:
        raise HTTPException(404, detail={"code": "run_not_found", "run_id": run_id})
    _enforce_tenant(run_dir, run_id, requester)
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise HTTPException(404, detail={"code": "manifest_not_found", "run_id": run_id})
    return _read_json(manifest_path)


@router.get("/runs/{run_id}/evidence_matrix")
def get_evidence_matrix(
    run_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Walk every ``evidence_matrix.jsonl`` under the run dir and merge.

    Each line is one of two shapes — a Claim row or an EvidenceLink row.
    We classify by shape (presence of ``text`` vs. ``support``) so the
    writer doesn't have to commit to a single record type per file.
    """
    requester = _user_id(request)
    run_dir = _find_run_dir(settings.project_root, run_id)
    if run_dir is None:
        raise HTTPException(404, detail={"code": "run_not_found", "run_id": run_id})
    _enforce_tenant(run_dir, run_id, requester)

    claims: list[dict] = []
    links: list[dict] = []

    for jsonl_path in sorted(run_dir.rglob("evidence_matrix.jsonl")):
        with jsonl_path.open() as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    # Skip malformed lines rather than 500 — partial
                    # writes are common with crash-recovery code paths.
                    continue
                if not isinstance(record, dict):
                    continue
                if "support" in record and "claim_id" in record:
                    links.append(record)
                elif "text" in record and "id" in record:
                    claims.append(record)

    return {"claims": claims, "evidence_links": links}


@router.get("/runs/{run_id}/validation_report")
def get_validation_report(
    run_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict:
    requester = _user_id(request)
    run_dir = _find_run_dir(settings.project_root, run_id)
    if run_dir is None:
        raise HTTPException(404, detail={"code": "run_not_found", "run_id": run_id})
    _enforce_tenant(run_dir, run_id, requester)
    report_path = run_dir / "validation_report.json"
    if not report_path.is_file():
        raise HTTPException(
            404,
            detail={"code": "validation_report_not_found", "run_id": run_id},
        )
    return _read_json(report_path)


__all__ = ["router"]
