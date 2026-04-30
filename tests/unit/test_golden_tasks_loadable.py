"""Programmatic sweep over evals/golden/*.json — catches typos in any one file."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.tasks import GoldenTask, discover_tasks, load_task


REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "evals" / "golden"


def _golden_paths() -> list[Path]:
    return sorted(GOLDEN_DIR.glob("*.json"))


def test_golden_directory_has_at_least_five_tasks():
    """R7 acceptance criterion: at least 5 golden tasks ship in-repo."""
    paths = _golden_paths()
    assert len(paths) >= 5, f"expected ≥5 golden tasks, got {len(paths)}: {[p.name for p in paths]}"


@pytest.mark.parametrize("path", _golden_paths(), ids=lambda p: p.stem)
def test_golden_task_validates_against_schema(path: Path):
    """Every JSON in evals/golden/ validates against the GoldenTask pydantic schema."""
    payload = json.loads(path.read_text())
    task = GoldenTask.model_validate(payload)
    # File stem must match the task id so discovery + cross-references stay sane.
    assert task.id == path.stem, f"id {task.id!r} != filename stem {path.stem!r}"


@pytest.mark.parametrize("path", _golden_paths(), ids=lambda p: p.stem)
def test_golden_task_has_idea_keywords_and_data_description(path: Path):
    """Each task carries at least one expected_idea_keyword and a non-empty data_description."""
    task = load_task(path)
    assert task.data_description.strip(), f"{path.name}: empty data_description"
    assert len(task.expected_idea_keywords) >= 1, (
        f"{path.name}: expected_idea_keywords must have ≥1 entry"
    )


@pytest.mark.parametrize("path", _golden_paths(), ids=lambda p: p.stem)
def test_golden_task_domain_is_known(path: Path):
    """Domain string must be one of the registered DomainProfiles."""
    from plato.domain import list_domains

    task = load_task(path)
    assert task.domain in list_domains(), (
        f"{path.name}: domain={task.domain!r} not in registered domains {list_domains()}"
    )


def test_discover_tasks_picks_up_all_files():
    """discover_tasks() returns one entry per JSON file under evals/golden/."""
    tasks = discover_tasks(GOLDEN_DIR)
    assert len(tasks) == len(_golden_paths())
    # Sorted by id, deterministic ordering.
    ids = [t.id for t in tasks]
    assert ids == sorted(ids)


def test_at_least_one_biology_task_present():
    """Phase 5 acceptance: at least one non-astro DomainProfile task ships."""
    tasks = discover_tasks(GOLDEN_DIR)
    by_domain: dict[str, list[str]] = {}
    for t in tasks:
        by_domain.setdefault(t.domain, []).append(t.id)
    assert "biology" in by_domain, f"no biology task found; domains={list(by_domain)}"
