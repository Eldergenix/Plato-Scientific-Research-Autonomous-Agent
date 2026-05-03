"""Unit tests for the GoldenTask gold_sources coercion shim (iter 12).

iter 10 added structured ``GoldSource`` reads inside
``EvalRunner._score_against_task`` but the existing golden tasks
shipped ``gold_sources`` as bare strings. iter 12 added a
``GoldSource.from_any`` coercer + a custom ``GoldenTask.model_validate``
to keep both shapes loadable. These tests pin that contract so a
future refactor can't regress.
"""
from __future__ import annotations

import pytest

from evals.tasks import GoldenTask, GoldSource


def test_from_any_string_with_slash_becomes_doi() -> None:
    src = GoldSource.from_any("10.1093/mnras/stu943")
    assert src.doi == "10.1093/mnras/stu943"
    assert src.arxiv_id is None
    assert src.note is None


def test_from_any_string_without_slash_becomes_arxiv() -> None:
    src = GoldSource.from_any("1212.0667")
    assert src.arxiv_id == "1212.0667"
    assert src.doi is None


def test_from_any_string_with_arxiv_substring_becomes_arxiv() -> None:
    """A bare arxiv id like ``arxiv:1212.0667`` must not match the DOI branch."""
    src = GoldSource.from_any("arxiv:1212.0667")
    assert src.arxiv_id == "arxiv:1212.0667"
    assert src.doi is None


def test_from_any_dict_round_trips() -> None:
    src = GoldSource.from_any(
        {"doi": "10.1119/1.10903", "note": "Nelson & Olsson 1986"}
    )
    assert src.doi == "10.1119/1.10903"
    assert src.note == "Nelson & Olsson 1986"
    assert src.arxiv_id is None


def test_from_any_dict_arxiv_only() -> None:
    src = GoldSource.from_any({"arxiv_id": "1212.0667"})
    assert src.arxiv_id == "1212.0667"
    assert src.doi is None
    assert src.note is None


def test_legacy_task_with_string_gold_sources() -> None:
    """Existing JSON files keep loading without modification."""
    task = GoldenTask.model_validate(
        {
            "id": "legacy-stub",
            "data_description": "x",
            "gold_sources": ["10.1038/s41586-021-03819-2", "1234.5678"],
        }
    )
    assert len(task.gold_sources) == 2
    assert task.gold_sources[0].doi == "10.1038/s41586-021-03819-2"
    assert task.gold_sources[0].arxiv_id is None
    assert task.gold_sources[1].arxiv_id == "1234.5678"
    assert task.gold_sources[1].doi is None


def test_new_task_with_structured_gold_sources() -> None:
    """New JSON files ship the rich form with optional notes."""
    task = GoldenTask.model_validate(
        {
            "id": "rich-task",
            "data_description": "y",
            "gold_sources": [
                {"doi": "10.1119/1.10903", "note": "Nelson 1986"},
                {"arxiv_id": "1212.0667", "note": "QF preprint"},
            ],
        }
    )
    assert len(task.gold_sources) == 2
    assert task.gold_sources[0].note == "Nelson 1986"
    assert task.gold_sources[1].arxiv_id == "1212.0667"
    assert task.gold_sources[1].note == "QF preprint"


def test_mixed_legacy_and_structured_gold_sources() -> None:
    """A task can mix the two shapes — coercer normalises both."""
    task = GoldenTask.model_validate(
        {
            "id": "mixed",
            "data_description": "z",
            "gold_sources": [
                "10.1038/s41586-021-03819-2",
                {"doi": "10.1119/1.10903", "note": "x"},
            ],
        }
    )
    assert all(isinstance(g, GoldSource) for g in task.gold_sources)
    assert task.gold_sources[0].doi == "10.1038/s41586-021-03819-2"
    assert task.gold_sources[1].note == "x"


def test_empty_gold_sources_default() -> None:
    task = GoldenTask.model_validate(
        {"id": "empty", "data_description": "no sources"}
    )
    assert task.gold_sources == []


def test_invalid_gold_source_type_raises() -> None:
    """Pydantic should reject an int / list / None inside gold_sources."""
    with pytest.raises(Exception):
        GoldenTask.model_validate(
            {
                "id": "bad",
                "data_description": "x",
                "gold_sources": [42],
            }
        )
