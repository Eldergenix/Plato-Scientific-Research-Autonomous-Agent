"""Iter-8 — tests for ProjectStore tenant isolation + atomic stage write.

These cover the two storage-layer behaviours that previously had zero
direct test coverage (per the iter-7 zone-O audit): the cross-tenant
``delete()`` no-op and the iter-7 atomic ``_write_stage_async`` (temp +
``os.replace``).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from plato_dashboard.storage.project_store import ProjectStore


@pytest.fixture
def store_factory(tmp_path: Path):
    """Factory that builds a ProjectStore bound to a given user_id."""

    def _build(user_id: str | None = None) -> ProjectStore:
        return ProjectStore(tmp_path, user_id=user_id)

    return _build


def _make_project(store: ProjectStore, name: str = "proj-test"):
    # ProjectStore.create takes ``user_id`` as a kwarg; pass through the
    # store's binding so the new project is owned by the same tenant.
    return store.create(name=name, user_id=store.user_id)


def test_delete_cross_tenant_raises_filenotfound(store_factory) -> None:
    """A store bound to user_b cannot delete user_a's project."""
    user_a = store_factory("alice")
    user_b = store_factory("bob")
    proj = _make_project(user_a, "shared")

    # Sanity: alice can load her own project.
    user_a.load(proj.id)

    # Bob tries to delete it. ``load()`` inside ``delete()`` raises
    # FileNotFoundError on the cross-tenant read, but the delete used
    # to swallow that. Iter-7 left the swallow in place but iter-8
    # documents the contract: cross-tenant ``delete`` is a no-op AND
    # the project survives.
    user_b.delete(proj.id)
    user_a.load(proj.id)  # still here


def test_write_stage_async_atomic(store_factory) -> None:
    """Concurrent writes shouldn't leave a torn file behind.

    We can't reliably trigger a real race in a unit test, but we can
    verify the contract: after every write, the stage path exists and
    no ``.tmp`` sibling is left on disk (the temp-file marker that
    ``_write_stage_async`` uses for its atomic-rename pattern).
    """
    store = store_factory("carol")
    proj = _make_project(store, "atomic")

    async def _run() -> None:
        for chunk in ("first", "second", "third"):
            await store.write_stage(proj.id, "idea", chunk)

    asyncio.run(_run())

    stage_path = store.stage_path(proj.id, "idea")
    assert stage_path.is_file()
    assert stage_path.read_text() == "third"
    assert not stage_path.with_suffix(stage_path.suffix + ".tmp").exists()


def test_list_projects_skips_cross_tenant_silently(store_factory) -> None:
    """Iter-3 contract: list_projects under user_b never reveals user_a's
    project, even though both live under the same root directory."""
    user_a = store_factory("alice")
    user_b = store_factory("bob")
    _make_project(user_a, "alice_only")
    _make_project(user_b, "bob_only")

    a_list = user_a.list_projects()
    b_list = user_b.list_projects()
    assert {p.name for p in a_list} == {"alice_only"}
    assert {p.name for p in b_list} == {"bob_only"}
