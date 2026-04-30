"""Phase 5 — Plato class plumbs ``user_id`` into every workflow's manifest.

The Plato constructor accepts ``user_id`` as an optional kwarg. The value
is stored on the instance and propagated through ``_start_manifest`` so
that ``RunManifest.user_id`` reflects the requesting tenant in every
``runs/<run_id>/manifest.json`` written during a workflow.
"""
from __future__ import annotations

import json
from pathlib import Path

from plato.plato import Plato


def _make_plato(tmp_path: Path, **kwargs) -> Plato:
    """Build a Plato instance pointed at a clean tmp project_dir.

    We avoid Plato's default ``./project`` CWD pollution and skip
    research-pipeline plumbing by passing only the constructor kwargs
    we care about. Plato's ``__init__`` does some on-disk setup but
    nothing that requires network or LLM keys.
    """
    return Plato(project_dir=str(tmp_path), **kwargs)


def test_user_id_default_is_none(tmp_path: Path) -> None:
    plato = _make_plato(tmp_path)
    assert plato.user_id is None


def test_user_id_stored_on_instance(tmp_path: Path) -> None:
    plato = _make_plato(tmp_path, user_id="alice")
    assert plato.user_id == "alice"


def test_user_id_lands_on_manifest(tmp_path: Path) -> None:
    """``_start_manifest`` forwards ``self.user_id`` into the manifest."""
    plato = _make_plato(tmp_path, user_id="alice")
    recorder = plato._start_manifest("test_workflow")

    assert recorder.manifest.user_id == "alice"
    payload = json.loads(recorder.path.read_text())
    assert payload["user_id"] == "alice"


def test_no_user_id_leaves_manifest_unset(tmp_path: Path) -> None:
    """Single-user installs (no user_id) keep manifests un-namespaced."""
    plato = _make_plato(tmp_path)
    recorder = plato._start_manifest("test_workflow")

    assert recorder.manifest.user_id is None
    payload = json.loads(recorder.path.read_text())
    assert payload["user_id"] is None


def test_each_workflow_inherits_user_id(tmp_path: Path) -> None:
    """Two manifests started by the same Plato carry the same user_id."""
    plato = _make_plato(tmp_path, user_id="bob")
    r1 = plato._start_manifest("workflow_one")
    r2 = plato._start_manifest("workflow_two")

    assert r1.manifest.user_id == "bob"
    assert r2.manifest.user_id == "bob"
    # Two distinct runs, both isolated under runs/<id>/.
    assert r1.manifest.run_id != r2.manifest.run_id
