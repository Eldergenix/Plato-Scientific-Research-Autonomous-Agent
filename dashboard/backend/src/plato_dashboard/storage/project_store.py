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
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiofiles

from ..domain.models import Project, Stage, StageId, StageContent, utcnow

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
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ paths
    def project_dir(self, pid: str) -> Path:
        return self.root / pid

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
        return Project.model_validate(data)

    def save(self, project: Project) -> Project:
        project.updated_at = utcnow()
        d = self.project_dir(project.id)
        d.mkdir(parents=True, exist_ok=True)
        (self.input_files_dir(project.id)).mkdir(exist_ok=True)
        (self.plots_dir(project.id)).mkdir(exist_ok=True)
        (self.history_dir(project.id)).mkdir(exist_ok=True)
        (self.runs_dir(project.id)).mkdir(exist_ok=True)
        with self.meta_path(project.id).open("w") as f:
            json.dump(project.model_dump(mode="json"), f, indent=2, default=str)
        return project

    def create(self, name: str = "Untitled project", initial_data_description: str | None = None) -> Project:
        project = Project.empty(name=name)
        self.save(project)
        if initial_data_description is not None:
            self.write_stage_sync(project.id, "data", initial_data_description)
            project.stages["data"].status = "done"
            project.stages["data"].origin = "edited"
            project.stages["data"].last_run_at = utcnow()
            self.save(project)
        return project

    def delete(self, pid: str) -> None:
        d = self.project_dir(pid)
        if d.exists():
            shutil.rmtree(d)

    # ------------------------------------------------------------ stage IO
    async def read_stage(self, pid: str, stage: StageId) -> Optional[StageContent]:
        if stage == "paper":
            # Paper is a binary, served separately
            return None
        path = self.stage_path(pid, stage)
        if not path.exists():
            return None
        async with aiofiles.open(path, "r") as f:
            text = await f.read()
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        proj = self.load(pid)
        origin = proj.stages.get(stage).origin if proj.stages.get(stage) else "ai"
        return StageContent(stage=stage, markdown=text, updated_at=mtime, origin=origin or "ai")

    async def write_stage(self, pid: str, stage: StageId, markdown: str, origin: str = "edited") -> StageContent:
        return await self._write_stage_async(pid, stage, markdown, origin)

    async def _write_stage_async(self, pid: str, stage: StageId, markdown: str, origin: str) -> StageContent:
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
        """Synchronous version used during project creation / migration."""
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
