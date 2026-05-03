"""
Opt-in, local-only telemetry sink.

Every successful or failed run can append a one-line summary to
``~/.plato/telemetry.jsonl`` so users can answer "how many runs did I do
this week, how many tokens did that cost?" without standing up an
external service. The file never leaves the machine.

The collector is gated three ways, any of which suppresses the write:

* ``PLATO_TELEMETRY_DISABLED=1`` env var (kill switch for CI / opt-out).
* ``telemetry_enabled=False`` in the user-prefs file the dashboard's
  Settings panel writes.
* Any IO error during append (we log via ``logging`` and swallow — a
  crashing telemetry layer must never crash a workflow).

The on-disk record is a flat dict; we deliberately avoid pydantic here
to keep the import graph small (this file is touched on every run flush).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


_DISABLE_ENV = "PLATO_TELEMETRY_DISABLED"


def _default_path() -> Path:
    """Resolve the telemetry sink lazily.

    ``Path.home()`` is intentionally called per-invocation so tests (and any
    future runtime) can monkeypatch the home directory and have writes land
    under the patched root instead of a frozen module-import value.
    """
    return Path.home() / ".plato" / "telemetry.jsonl"


# Whitelisted keys we'll persist. Anything else in ``run_summary`` is
# dropped — keeps the schema honest and prevents future RunManifest
# fields (which may carry user prompts or paths) from leaking into a
# file the user thinks only contains aggregate metrics.
#
# The first eight fields are the original Phase-1 schema and remain the
# stable contract for parsers. The trailing ones (``project_id``,
# ``user_id``, ``model``, ``started_at``, ``finished_at``, ``error``)
# were added when the dashboard collector landed; they're optional, so
# older JSONL files keep parsing.
_ALLOWED_FIELDS = (
    "timestamp",
    "run_id",
    "workflow",
    "duration_seconds",
    "tokens_in",
    "tokens_out",
    "cost_usd",
    "status",
    "project_id",
    "user_id",
    "model",
    "started_at",
    "finished_at",
    "error",
)


def _user_prefs_telemetry_enabled() -> bool:
    """Read the dashboard's ``telemetry_enabled`` flag.

    The dashboard persists per-user preferences at
    ``<project_root>/users/<uid>/preferences.json``. We look at the anon
    profile under the standard ``~/.plato/users/__anon__/preferences.json``
    path because the manifest layer doesn't know about authed users — when
    auth is enabled, the dashboard's GET/PUT routes work against the
    user's own file; the per-user file naturally takes precedence in that
    flow because the dashboard is what flips the toggle. For the
    single-user CLI path, the anon file is the source of truth.

    Default is ``True`` (opt-in is via the env kill switch + the toggle
    that defaults to enabled). If the file or key is missing, we treat
    that as "user hasn't opted out" and proceed.
    """
    candidates = [
        Path.home() / ".plato" / "users" / "__anon__" / "preferences.json",
        Path.home() / ".plato" / "preferences.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and "telemetry_enabled" in data:
            return bool(data["telemetry_enabled"])
    return True


def is_enabled() -> bool:
    """Single source of truth for "should we write telemetry right now?"."""
    if os.environ.get(_DISABLE_ENV) == "1":
        return False
    return _user_prefs_telemetry_enabled()


def append_run_summary(
    run_summary: dict[str, Any],
    dest_path: Optional[Path] = None,
) -> None:
    """Append one JSON line to the telemetry log if the user opted in.

    Failures are logged at DEBUG and swallowed — this path runs from
    ``ManifestRecorder.finish`` which must never raise.
    """
    if not is_enabled():
        return

    record = {k: run_summary.get(k) for k in _ALLOWED_FIELDS if k in run_summary}
    if not record:
        return

    target = dest_path or _default_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError as exc:
        logger.debug("telemetry append failed (%s): %s", target, exc)


def read_recent(
    n: int = 30,
    src_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Return the last ``n`` summaries, oldest-first.

    Used by the dashboard ``GET /telemetry/preferences`` endpoint to
    render the "last 30 runs" card. Lines that fail to parse are
    skipped silently — a single bad line shouldn't blank the panel.
    """
    target = src_path or _default_path()
    if not target.exists():
        return []
    try:
        raw = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in raw[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


__all__ = ["append_run_summary", "read_recent", "is_enabled"]
