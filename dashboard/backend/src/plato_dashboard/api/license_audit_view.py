"""Read-only views over Phase 5's license matrix and CycloneDX SBOM.

Two endpoints:

``GET /api/v1/license_audit``
    Summarises ``scripts/license_audit.collect_distributions`` into a shape
    the dashboard can render directly: aggregate counts, per-license
    rollup, and the full per-distribution table (name, version, license,
    GPLv3 compatibility, source URL).

``GET /api/v1/sbom``
    Returns the CycloneDX JSON SBOM. Prefers a pre-generated ``sbom.json``
    at the repo root (cheap, deterministic, what CI ships); otherwise
    shells out to ``scripts/generate_sbom.py`` on demand. Returns 503 if
    neither path is available — most commonly because ``cyclonedx-bom``
    isn't installed.

Both endpoints are read-only and idempotent. The license audit is cached
in-process for five minutes; the installed-distribution set rarely
changes mid-process and re-walking ``importlib.metadata`` for every page
load would be wasteful.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse


router = APIRouter()


# Five minutes is long enough that an unchanging environment doesn't pay
# the audit cost on every request, and short enough that a freshly-pinned
# dependency shows up promptly without a server restart.
_CACHE_TTL_SECONDS = 300.0
_cache_lock = threading.Lock()
_cache_payload: dict | None = None
_cache_expires_at: float = 0.0


def _repo_root() -> Path:
    """Walk up from this file to the repository root.

    Layout: ``<repo>/dashboard/backend/src/plato_dashboard/api/this_file.py``.
    ``parents[5]`` is the repo. Tests can monkeypatch this if they need a
    different root.
    """
    return Path(__file__).resolve().parents[5]


def _build_audit_payload() -> dict:
    """Call into ``scripts/license_audit`` and shape its output for the API.

    Imported lazily so a missing script (e.g. wrong branch checked out)
    surfaces as a 500 from the route rather than a server-startup error.
    Falls through to an HTTPException the route handler converts.
    """
    try:
        from scripts.license_audit import collect_distributions  # type: ignore[import-not-found]
    except Exception as exc:  # ImportError, ModuleNotFoundError, or ImportErrors raised inside the script.
        raise HTTPException(
            status_code=500,
            detail={"error": "license_audit script not available", "reason": str(exc)},
        ) from exc

    dists = collect_distributions()

    by_license_counts: dict[str, dict[str, Any]] = {}
    distributions: list[dict[str, Any]] = []
    compatible = 0
    incompatible = 0
    unknown = 0

    for d in dists:
        license_label = (d.license or "UNKNOWN").strip() or "UNKNOWN"
        is_unknown = license_label.upper() == "UNKNOWN"
        if is_unknown:
            unknown += 1
        elif d.compatible:
            compatible += 1
        else:
            incompatible += 1

        bucket = by_license_counts.setdefault(
            license_label,
            {"license": license_label, "count": 0, "gpl3_compatible": d.compatible},
        )
        bucket["count"] += 1
        # Mixed buckets (same license string but a known override flips
        # one entry) are rare; bias to "compatible" so the badge is
        # green when at least one representative says so.
        bucket["gpl3_compatible"] = bucket["gpl3_compatible"] or d.compatible

        distributions.append(
            {
                "name": d.name,
                "version": d.version,
                "license": None if is_unknown else license_label,
                "gpl3_compatible": d.compatible,
                "source_url": d.homepage,
            }
        )

    distributions.sort(key=lambda r: (r["name"] or "").lower())
    by_license = sorted(
        by_license_counts.values(),
        key=lambda r: (-r["count"], r["license"].lower()),
    )

    return {
        "summary": {
            "total": len(dists),
            "compatible": compatible,
            "incompatible": incompatible,
            "unknown": unknown,
        },
        "by_license": by_license,
        "distributions": distributions,
    }


def _reset_cache() -> None:
    """Clear the in-memory cache. Exposed for tests."""
    global _cache_payload, _cache_expires_at
    with _cache_lock:
        _cache_payload = None
        _cache_expires_at = 0.0


def _get_cached_audit() -> dict:
    """Return the cached audit payload, regenerating if it's stale."""
    global _cache_payload, _cache_expires_at
    with _cache_lock:
        now = time.monotonic()
        if _cache_payload is not None and now < _cache_expires_at:
            return _cache_payload
    # Build outside the lock so concurrent callers don't queue on a slow audit;
    # a brief duplicate compute is preferable to serialising every request.
    payload = _build_audit_payload()
    with _cache_lock:
        _cache_payload = payload
        _cache_expires_at = time.monotonic() + _CACHE_TTL_SECONDS
        return _cache_payload


@router.get("/license_audit")
def license_audit() -> dict:
    return _get_cached_audit()


def _read_prebuilt_sbom() -> dict | None:
    """Return the pre-generated ``sbom.json`` if it exists at the repo root."""
    candidate = _repo_root() / "sbom.json"
    if not candidate.is_file():
        return None
    try:
        return json.loads(candidate.read_text())
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "sbom.json is corrupt", "reason": str(exc)},
        ) from exc


def _generate_sbom_via_subprocess() -> dict:
    """Invoke ``scripts/generate_sbom.py`` and parse its output.

    The script writes the SBOM to ``--output``; we hand it a temp file
    path inside the working tree, then read+parse it. A non-zero exit
    means cyclonedx-bom isn't installed (the script returns 2) or the
    underlying tool failed (any other code) — both surface to the route
    handler as a 503 with a helpful hint.
    """
    repo = _repo_root()
    script = repo / "scripts" / "generate_sbom.py"
    if not script.is_file():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "sbom_unavailable",
                "message": "Neither sbom.json nor scripts/generate_sbom.py is available.",
            },
        )

    out_path = repo / ".sbom_cache.json"
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--output", str(out_path)],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "sbom_unavailable",
                "message": f"Failed to invoke generator: {exc}",
            },
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "sbom_timeout",
                "message": "SBOM generation timed out.",
            },
        ) from exc

    if result.returncode != 0:
        # rc=2 from generate_sbom.py means cyclonedx-bom is missing.
        hint = (
            "Install with: pip install cyclonedx-bom"
            if result.returncode == 2
            else f"Generator exited with status {result.returncode}"
        )
        stderr_tail = (result.stderr or "").strip().splitlines()[-1:] or [""]
        raise HTTPException(
            status_code=503,
            detail={
                "error": "sbom_generation_failed",
                "message": stderr_tail[0] or hint,
                "hint": hint,
            },
        )

    if not out_path.is_file():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "sbom_missing_output",
                "message": "Generator reported success but produced no file.",
            },
        )
    try:
        return json.loads(out_path.read_text())
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "sbom_corrupt", "reason": str(exc)},
        ) from exc


@router.get("/sbom")
def sbom() -> JSONResponse:
    """Return the CycloneDX SBOM as JSON.

    Reads ``<repo>/sbom.json`` first; falls back to running the generator
    in-process. The dashboard's "Download SBOM" button hits this endpoint
    and saves the body verbatim, so the response body itself must be the
    CycloneDX document — no envelope.
    """
    prebuilt = _read_prebuilt_sbom()
    if prebuilt is not None:
        return JSONResponse(content=prebuilt)
    generated = _generate_sbom_via_subprocess()
    return JSONResponse(content=generated)


__all__ = ["router"]
