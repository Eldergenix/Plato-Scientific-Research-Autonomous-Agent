"""
Phase 3 — R7: Golden tasks for the evaluation harness.

A ``GoldenTask`` is a small, reproducible scientific-research prompt with
known-good signals (idea keywords, method signals, gold sources). Tasks
live as plain JSON under ``evals/golden/`` so they can be diffed in PRs
without touching Python.

The harness loads every JSON file in the directory, validates each
against ``GoldenTask``, and feeds the resulting list into ``EvalRunner``.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class GoldenTask(BaseModel):
    """A reproducible scientific-research prompt with known-good signals."""

    id: str
    data_description: str
    expected_idea_keywords: list[str] = Field(default_factory=list)
    expected_method_signals: list[str] = Field(default_factory=list)
    gold_sources: list[str] = Field(
        default_factory=list,
        description="DOIs or arxiv ids that an ideal run should cite.",
    )
    domain: str = "astro"


def load_task(path: str | Path) -> GoldenTask:
    """Load and validate a single golden task from a JSON file."""
    p = Path(path)
    payload = json.loads(p.read_text())
    return GoldenTask.model_validate(payload)


def discover_tasks(directory: str | Path = "evals/golden") -> list[GoldenTask]:
    """Discover and load every ``*.json`` golden task under ``directory``.

    Tasks are returned sorted by ``id`` for stable ordering across runs.
    Missing directories return an empty list — callers decide whether
    that is an error.
    """
    d = Path(directory)
    if not d.exists() or not d.is_dir():
        return []
    tasks: list[GoldenTask] = []
    for json_path in sorted(d.glob("*.json")):
        tasks.append(load_task(json_path))
    tasks.sort(key=lambda t: t.id)
    return tasks


__all__ = ["GoldenTask", "load_task", "discover_tasks"]
