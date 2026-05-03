"""Object-oriented facade over the run-summary telemetry sink.

The function-level API in :mod:`plato.state.telemetry` is the cheap
import path that ``ManifestRecorder.finish`` uses on the hot run-flush
loop. This module wraps that API in a class so callers that need to
plug a different storage location (tests, the dashboard backend) can
do so without monkeypatching module globals.

The class deliberately keeps the same opt-in gating as the module
helpers — :func:`plato.state.telemetry.is_enabled` is the single source
of truth so the env kill-switch and the dashboard's ``telemetry_enabled``
toggle govern both code paths identically.

Schema (each JSONL line)::

    run_id           str   — RunManifest.run_id
    workflow         str   — workflow name (e.g. ``get_idea_fast``)
    status           str   — running | success | error
    timestamp        str   — ISO-8601 of finished_at (or started_at)
    started_at       str?  — optional ISO-8601 start
    finished_at      str?  — optional ISO-8601 end
    duration_seconds float? — finished_at - started_at, when both exist
    tokens_in        int   — accumulated input tokens
    tokens_out       int   — accumulated output tokens
    cost_usd         float — accumulated USD cost
    project_id       str?  — optional project identifier
    user_id          str?  — optional X-Plato-User submitter
    model            str?  — primary model id (best-effort, may be empty)
    error            str?  — error message when status != "success"

Older lines without the optional fields parse the same way; readers
must treat every key beyond ``status`` as possibly missing.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .telemetry import _ALLOWED_FIELDS, _default_path, append_run_summary, is_enabled

logger = logging.getLogger(__name__)


class TelemetryCollector:
    """Records per-run summaries to a JSONL file.

    Stateless apart from the configured ``storage_path`` — every call
    re-reads ``is_enabled()`` so toggling the dashboard preference takes
    effect on the next run without restarting the process.
    """

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self._storage_path = storage_path

    @property
    def storage_path(self) -> Path:
        """Resolved path; defers to ``~/.plato/telemetry.jsonl`` by default."""
        return self._storage_path or _default_path()

    def is_enabled(self) -> bool:
        """Mirror of the module-level gate so callers don't import twice."""
        return is_enabled()

    def record_run_summary(self, manifest_path: str | Path) -> bool:
        """Append a summary derived from ``runs/<run_id>/manifest.json``.

        Returns ``True`` when a line was written, ``False`` when the
        record was skipped (telemetry disabled, manifest unreadable, no
        whitelisted fields). Never raises — telemetry must not crash a
        finishing run.
        """
        if not self.is_enabled():
            return False
        try:
            payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("telemetry: cannot read manifest %s: %s", manifest_path, exc)
            return False
        summary = self._summary_from_manifest(payload)
        if not summary:
            return False
        append_run_summary(summary, dest_path=self._storage_path)
        return True

    def read_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return at most ``limit`` summaries, most-recent first.

        The on-disk file is append-only, so the tail is the newest
        slice. We reverse before returning so the dashboard renders the
        latest run at the top without sorting client-side. Malformed
        lines are skipped with a debug log so a single corrupted entry
        doesn't blank the panel.
        """
        if limit <= 0:
            return []
        target = self.storage_path
        if not target.exists():
            return []
        try:
            raw = target.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.debug("telemetry: cannot read %s: %s", target, exc)
            return []

        out: list[dict[str, Any]] = []
        # Walk from the end so we collect the newest ``limit`` valid rows
        # without parsing the whole file when it's much larger.
        for line in reversed(raw):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("telemetry: skipping malformed line in %s", target)
                continue
            if not isinstance(obj, dict):
                continue
            out.append(obj)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _summary_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
        """Map a RunManifest dict into the JSONL schema.

        Only whitelisted keys survive — see ``_ALLOWED_FIELDS`` in
        :mod:`plato.state.telemetry`. We compute ``duration_seconds``
        and pick a primary ``model`` here so the on-disk record is
        directly usable by the dashboard without re-parsing nested
        dicts.
        """
        if not isinstance(manifest, dict):
            return {}

        started_raw = manifest.get("started_at")
        ended_raw = manifest.get("ended_at")
        duration = _duration_seconds(started_raw, ended_raw)
        timestamp = ended_raw or started_raw

        models = manifest.get("models") or {}
        # Pick a stable representative model. The dashboard displays a
        # single string, so we surface the first deterministic value
        # rather than concatenating every node's model.
        model = ""
        if isinstance(models, dict) and models:
            model = next(iter(sorted(models.values())), "") or ""

        candidate = {
            "timestamp": timestamp,
            "run_id": manifest.get("run_id"),
            "workflow": manifest.get("workflow"),
            "duration_seconds": duration,
            "tokens_in": int(manifest.get("tokens_in") or 0),
            "tokens_out": int(manifest.get("tokens_out") or 0),
            "cost_usd": float(manifest.get("cost_usd") or 0.0),
            "status": manifest.get("status") or "running",
            "project_id": manifest.get("project_id"),
            "user_id": manifest.get("user_id"),
            "model": model or None,
            "started_at": started_raw,
            "finished_at": ended_raw,
            "error": manifest.get("error"),
        }
        # Strip Nones so optional fields don't bloat the JSONL.
        return {
            k: v
            for k, v in candidate.items()
            if k in _ALLOWED_FIELDS and v is not None
        }


def _duration_seconds(started: Any, ended: Any) -> Optional[float]:
    """Parse two ISO-8601-ish timestamps into a non-negative duration.

    Returns ``None`` when either side is missing or unparseable. We
    accept naive strings by attaching UTC because that's what
    ``RunManifest`` writes (``datetime.now(timezone.utc)``).
    """
    s = _parse_dt(started)
    e = _parse_dt(ended)
    if s is None or e is None:
        return None
    return max((e - s).total_seconds(), 0.0)


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    # Python <3.11 doesn't accept the trailing 'Z' in fromisoformat.
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


__all__ = ["TelemetryCollector"]
