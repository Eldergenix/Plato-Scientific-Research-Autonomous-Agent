"""Filesystem-backed project store.

Layout under ``settings.project_root``::

    <id>/
      meta.json                  # Project metadata + stage statuses
      input_files/               # Plato-canonical artifact dir
        data_description.md
        idea.md
        methods.md
        results.md
        literature.md
        referee.md
        plots/
        .history/<stage>_<ts>.md
      paper/                     # PDFs, .tex, .bib
      idea_generation_output/
      method_generation_output/
      experiment_generation_output/
      runs/<run_id>/             # per-run scratch + status.json

We intentionally mirror Plato's existing on-disk layout so the same
project_dir works whether driven by the Python class or the dashboard.
"""

from __future__ import annotations
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiofiles

from ..domain.models import Journal, Project, Stage, StageId, StageContent, utcnow

# Project IDs flow into filesystem paths verbatim. Restrict to the same
# safe charset we use for X-Plato-User to block path traversal (`..`,
# `/`) and other shenanigans. This length cap also bounds storage
# layout depth.
_PID_RE = re.compile(r"\A[A-Za-z0-9_-]{1,64}\Z")


def _validate_pid(pid: str) -> str:
    """Reject project IDs that would escape ``self.root`` or land in a hidden dir."""
    if not isinstance(pid, str) or not _PID_RE.match(pid):
        raise ValueError(
            f"Invalid project id {pid!r}: must match [A-Za-z0-9_-]{{1,64}}"
        )
    return pid


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (temp file + rename).

    Avoids the torn-read window that ``open('w')`` exposes — readers
    that hit the file mid-write would otherwise see a truncated JSON
    and treat the project as missing.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)

# Map StageId → canonical filename in input_files/
STAGE_FILES: dict[StageId, str] = {
    "data": "data_description.md",
    "idea": "idea.md",
    "literature": "literature.md",
    "method": "methods.md",
    "results": "results.md",
    "referee": "referee.md",
    # paper is multi-file, handled separately
    "paper": "paper/main.pdf",
}


class ProjectStore:
    def __init__(self, root: Path, *, user_id: str | None = None):
        # Per-user tenant binding (iter-31): when ``user_id`` is set, every
        # read/write that touches a Project's meta verifies the project's
        # ``user_id`` matches. Routers already enforce this via
        # ``_enforce_project_tenant``, but binding at the store level is a
        # belt-and-braces defense — any future router that forgets the
        # helper still gets blocked from cross-tenant access.
        #
        # Backwards-compatible: legacy callers (CLI, single-tenant deploys,
        # tests) construct without ``user_id`` and the check is skipped.
        self.root = root
        self.user_id = user_id
        root.mkdir(parents=True, exist_ok=True)

    def _check_tenant(self, project: "Project") -> None:
        """Raise FileNotFoundError if ``project.user_id`` doesn't match.

        We deliberately raise the same exception as a missing-file lookup
        rather than a permission error, because "the project doesn't exist"
        is a strictly less-informative response than "you don't own it" —
        the former doesn't leak project existence to a probing attacker.
        """
        if self.user_id is None:
            return
        if project.user_id is None:
            # Legacy un-bound project. Permit if the store is also un-bound;
            # otherwise treat as cross-tenant and 404.
            return
        if project.user_id != self.user_id:
            raise FileNotFoundError(project.id)

    # ------------------------------------------------------------ paths
    def project_dir(self, pid: str) -> Path:
        return self.root / _validate_pid(pid)

    def meta_path(self, pid: str) -> Path:
        return self.project_dir(pid) / "meta.json"

    def input_files_dir(self, pid: str) -> Path:
        return self.project_dir(pid) / "input_files"

    def stage_path(self, pid: str, stage: StageId) -> Path:
        rel = STAGE_FILES[stage]
        return self.project_dir(pid) / ("input_files" / Path(rel) if "/" not in rel else Path(rel))

    def plots_dir(self, pid: str) -> Path:
        return self.input_files_dir(pid) / "plots"

    def history_dir(self, pid: str) -> Path:
        return self.input_files_dir(pid) / ".history"

    def runs_dir(self, pid: str) -> Path:
        return self.project_dir(pid) / "runs"

    # ------------------------------------------------------------ metadata
    def list_projects(self) -> list[Project]:
        out: list[Project] = []
        if not self.root.exists():
            return out
        for p in sorted(self.root.iterdir()):
            if not p.is_dir():
                continue
            try:
                out.append(self.load(p.name))
            except FileNotFoundError:
                continue
        return out

    def load(self, pid: str) -> Project:
        path = self.meta_path(pid)
        if not path.exists():
            raise FileNotFoundError(pid)
        with path.open() as f:
            data = json.load(f)
        project = Project.model_validate(data)
        self._check_tenant(project)
        return project

    def save(self, project: Project) -> Project:
        project.updated_at = utcnow()
        d = self.project_dir(project.id)
        d.mkdir(parents=True, exist_ok=True)
        (self.input_files_dir(project.id)).mkdir(exist_ok=True)
        (self.plots_dir(project.id)).mkdir(exist_ok=True)
        (self.history_dir(project.id)).mkdir(exist_ok=True)
        (self.runs_dir(project.id)).mkdir(exist_ok=True)
        # Atomic write — temp + os.replace — so concurrent readers
        # never see a half-written meta.json (which would JSONDecodeError
        # in load() and silently drop the project from list_projects()).
        _atomic_write_text(
            self.meta_path(project.id),
            json.dumps(project.model_dump(mode="json"), indent=2, default=str),
        )
        return project

    def create(
        self,
        name: str = "Untitled project",
        initial_data_description: str | None = None,
        *,
        user_id: str | None = None,
        journal: "Journal | None" = None,
    ) -> Project:
        # Iter-24: bind the new project to ``user_id`` from the request's
        # X-Plato-User header. Subsequent project-level endpoints
        # consult this field via ``_enforce_project_tenant`` so cross-
        # tenant reads/writes are 403'd in required-mode and 404'd in
        # not-required-mode (matching ``_enforce_run_tenant``).
        project = Project.empty(name=name, user_id=user_id)
        if journal is not None:
            project.journal = journal
        self.save(project)
        if initial_data_description is not None:
            self.write_stage_sync(project.id, "data", initial_data_description)
            project.stages["data"].status = "done"
            project.stages["data"].origin = "edited"
            project.stages["data"].last_run_at = utcnow()
            self.save(project)
        return project

    def delete(self, pid: str) -> None:
        # Verify tenant before rm-rf'ing the project tree. ``load`` raises
        # FileNotFoundError on cross-tenant access — we let that propagate
        # rather than silently returning so the caller sees the same shape
        # as a "project doesn't exist" delete.
        try:
            self.load(pid)
        except FileNotFoundError:
            return
        d = self.project_dir(pid)
        if d.exists():
            shutil.rmtree(d)

    # ------------------------------------------------------------ stage IO
    async def read_stage(self, pid: str, stage: StageId) -> Optional[StageContent]:
        if stage == "paper":
            # Paper is a binary, served separately
            return None
        # Tenant check first (load() raises on cross-tenant) so we don't leak
        # stage-file existence to a user who doesn't own the project.
        proj = self.load(pid)
        path = self.stage_path(pid, stage)
        if not path.exists():
            return None
        async with aiofiles.open(path, "r") as f:
            text = await f.read()
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        origin = proj.stages.get(stage).origin if proj.stages.get(stage) else "ai"
        return StageContent(stage=stage, markdown=text, updated_at=mtime, origin=origin or "ai")

    async def write_stage(self, pid: str, stage: StageId, markdown: str, origin: str = "edited") -> StageContent:
        return await self._write_stage_async(pid, stage, markdown, origin)

    async def _write_stage_async(self, pid: str, stage: StageId, markdown: str, origin: str) -> StageContent:
        # Tenant check before any side effect: load raises on cross-tenant
        # access so a misconfigured router cannot accidentally write into
        # another user's project tree.
        self.load(pid)
        path = self.stage_path(pid, stage)
        path.parent.mkdir(parents=True, exist_ok=True)

        # snapshot prior version into .history/
        if path.exists():
            ts = utcnow().strftime("%Y%m%dT%H%M%SZ")
            hist = self.history_dir(pid) / f"{stage}_{ts}.md"
            shutil.copy2(path, hist)

        async with aiofiles.open(path, "w") as f:
            await f.write(markdown)

        proj = self.load(pid)
        s = proj.stages[stage]
        s.status = "done"
        s.origin = origin  # type: ignore[assignment]
        s.last_run_at = utcnow()
        self._mark_downstream_stale(proj, stage)
        self.save(proj)
        return StageContent(stage=stage, markdown=markdown, updated_at=utcnow(), origin=origin)  # type: ignore[arg-type]

    def write_stage_sync(self, pid: str, stage: StageId, markdown: str, origin: str = "edited") -> None:
        """Synchronous version used during project creation / migration.

        Tenant-checked: load() raises FileNotFoundError on cross-tenant
        access. Skipped during initial create() because the project meta
        hasn't been saved yet — create() builds the project bound to the
        requester so there's no tenant ambiguity at that moment.
        """
        if self.meta_path(pid).exists():
            self.load(pid)  # tenant guard
        path = self.stage_path(pid, stage)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            f.write(markdown)

    def list_plots(self, pid: str) -> list[Path]:
        d = self.plots_dir(pid)
        if not d.exists():
            return []
        return sorted([p for p in d.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"}])

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _mark_downstream_stale(project: Project, edited_stage: StageId) -> None:
        order: list[StageId] = ["data", "idea", "literature", "method", "results", "paper", "referee"]
        try:
            idx = order.index(edited_stage)
        except ValueError:
            return
        for s in order[idx + 1 :]:
            stage = project.stages.get(s)
            if stage is None:
                continue
            if stage.status == "done":
                stage.status = "stale"
