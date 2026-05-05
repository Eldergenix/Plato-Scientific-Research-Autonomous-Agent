"""
Reproducibility manifest.

Every workflow invocation (``get_idea``, ``get_method``, ``get_paper`` …)
opens a ``RunManifest`` and writes it to
``<project_dir>/runs/<run_id>/manifest.json``. The recorder is idempotent
under repeated ``flush()`` calls — fields are merged, not overwritten,
so partial-run crashes still leave a useful manifest behind.

Phase 1 ships the schema, the recorder, and entry-point hooks in
``Plato``. Per-node telemetry (tokens/costs/source ids per node) lands
in Phase 3 with the eval harness.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class RunManifest(BaseModel):
    """Per-run reproducibility metadata. Persisted as ``manifest.json``."""

    run_id: str
    workflow: str = Field(description="e.g. 'get_idea_fast', 'get_paper'")
    started_at: datetime
    ended_at: datetime | None = None
    status: str = "running"  # running | success | error
    domain: str = "astro"
    git_sha: str = ""
    project_sha: str = ""
    user_id: str | None = None
    models: dict[str, str] = Field(default_factory=dict)
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    seeds: dict[str, int] = Field(default_factory=dict)
    source_ids: list[str] = Field(default_factory=list)
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    error: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


def _git_sha(repo_dir: str | os.PathLike[str]) -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return out.decode().strip()
    except Exception:
        return ""


_VOLATILE_TOPLEVEL = frozenset({"runs", "plots", "paper", "temp"})
"""Top-level dirs whose contents change every run; excluded from project SHA.

Names are matched case-insensitively (macOS APFS is case-insensitive by
default while Linux ext4 is case-sensitive — without lowercasing,
``Plots`` and ``plots`` would be treated as different on Linux and
identical on macOS, producing platform-dependent project SHAs).
"""


def _project_sha(project_dir: str | os.PathLike[str]) -> str:
    """Stable SHA-256 over input file contents (sorted), excluding volatile dirs.

    Excludes: ``runs/``, ``plots/`` (any case), ``paper/``, ``temp/`` so the
    SHA is stable across runs and across platforms with different
    filesystem case sensitivity.
    """
    project_path = Path(project_dir)
    if not project_path.exists():
        return ""
    h = hashlib.sha256()
    for p in sorted(project_path.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(project_path).parts
        if rel_parts and rel_parts[0].lower() in _VOLATILE_TOPLEVEL:
            continue
        rel = "/".join(rel_parts)
        h.update(rel.encode())
        h.update(b"\0")
        try:
            h.update(p.read_bytes())
        except OSError:
            continue
        h.update(b"\0\0")
    return h.hexdigest()


class ManifestRecorder:
    """
    Build a RunManifest as a workflow progresses and flush atomically to disk.

    Usage::

        recorder = ManifestRecorder.start(
            project_dir="./project",
            workflow="get_idea_fast",
            domain="astro",
        )
        recorder.update(models={"idea_maker": "gemini-2.0-flash"})
        recorder.add_tokens(input_tokens=120, output_tokens=200)
        recorder.finish(status="success")
    """

    def __init__(self, project_dir: str | os.PathLike[str], manifest: RunManifest) -> None:
        self.project_dir = Path(project_dir)
        self.manifest = manifest
        self._dir = self.project_dir / "runs" / manifest.run_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "manifest.json"
        # Iter-3: serialise add_tokens / update / flush. LangGraph fans
        # out parallel chains (literature_summary + counter_evidence
        # search) whose on_llm_end callbacks each call ``add_tokens``;
        # without this lock the tokens_in/tokens_out/cost_usd
        # read-modify-writes race and lose deltas. The lock also covers
        # ``flush()`` so two concurrent atomic-rename writes can't clobber
        # each other's tmp file.
        self._lock = threading.RLock()
        self.flush()

    @classmethod
    def start(
        cls,
        project_dir: str | os.PathLike[str],
        workflow: str,
        *,
        domain: str = "astro",
        run_id: str | None = None,
        repo_dir: str | os.PathLike[str] | None = None,
        user_id: str | None = None,
    ) -> "ManifestRecorder":
        manifest = RunManifest(
            run_id=run_id or uuid.uuid4().hex[:12],
            workflow=workflow,
            started_at=datetime.now(timezone.utc),
            domain=domain,
            git_sha=_git_sha(repo_dir or os.getcwd()),
            project_sha=_project_sha(project_dir),
            user_id=user_id,
        )
        return cls(project_dir=project_dir, manifest=manifest)

    @property
    def path(self) -> Path:
        return self._path

    def update(self, **fields: Any) -> None:
        # Iter-5 thread-safety parity with ``add_tokens`` / ``finish``.
        # Without the lock, a concurrent ``add_tokens`` on the callback
        # thread can clobber tokens_in / cost_usd between the read and
        # the flush — and two ``update`` calls hitting the same dict
        # field can race on the dict-update + flush.
        with self._lock:
            for key, value in fields.items():
                if key in {"models", "prompt_hashes", "seeds", "extra"}:
                    getattr(self.manifest, key).update(value)
                elif key == "source_ids":
                    seen = set(self.manifest.source_ids)
                    for sid in value:
                        if sid not in seen:
                            self.manifest.source_ids.append(sid)
                            seen.add(sid)
                else:
                    setattr(self.manifest, key, value)
            self.flush()

    def add_tokens(self, *, input_tokens: int = 0, output_tokens: int = 0, cost_usd: float = 0.0) -> None:
        with self._lock:
            self.manifest.tokens_in += input_tokens
            self.manifest.tokens_out += output_tokens
            self.manifest.cost_usd += cost_usd
            self.flush()

    def finish(self, status: str = "success", error: str | None = None) -> None:
        with self._lock:
            self.manifest.status = status
            self.manifest.ended_at = datetime.now(timezone.utc)
            if error:
                self.manifest.error = error
            self.flush()

    def flush(self) -> None:
        """Atomic write via temp-file rename so partial writes never leave junk.

        Locked because two concurrent flush()es can both write the same
        tmp path and one's os.replace can race with the other's write,
        producing a torn JSON file. ``threading.RLock`` so add_tokens /
        update can call into flush() without deadlocking.
        """
        with self._lock:
            payload = self.manifest.model_dump(mode="json")
            tmp = self._path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
            os.replace(tmp, self._path)


__all__ = ["RunManifest", "ManifestRecorder"]
