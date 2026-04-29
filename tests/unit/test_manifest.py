"""Phase 1 — R9: RunManifest + ManifestRecorder."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from plato.state.manifest import ManifestRecorder, RunManifest, _project_sha


def test_recorder_writes_manifest_immediately(tmp_path: Path):
    """`start()` flushes the manifest to disk so a crash leaves a usable trace."""
    rec = ManifestRecorder.start(
        project_dir=str(tmp_path),
        workflow="test_workflow",
        domain="astro",
    )
    assert rec.path.exists()
    payload = json.loads(rec.path.read_text())
    assert payload["workflow"] == "test_workflow"
    assert payload["domain"] == "astro"
    assert payload["status"] == "running"
    assert "started_at" in payload
    assert payload["run_id"] == rec.manifest.run_id


def test_update_merges_dict_fields(tmp_path: Path):
    """update() merges into models/prompt_hashes/extra rather than overwriting."""
    rec = ManifestRecorder.start(project_dir=str(tmp_path), workflow="wf")
    rec.update(models={"idea": "gpt-4o"})
    rec.update(models={"hater": "o3-mini"})
    payload = json.loads(rec.path.read_text())
    assert payload["models"] == {"idea": "gpt-4o", "hater": "o3-mini"}


def test_add_tokens_accumulates(tmp_path: Path):
    rec = ManifestRecorder.start(project_dir=str(tmp_path), workflow="wf")
    rec.add_tokens(input_tokens=100, output_tokens=50, cost_usd=0.001)
    rec.add_tokens(input_tokens=10, output_tokens=5, cost_usd=0.0005)
    payload = json.loads(rec.path.read_text())
    assert payload["tokens_in"] == 110
    assert payload["tokens_out"] == 55
    assert payload["cost_usd"] == pytest.approx(0.0015)


def test_finish_sets_status_and_ended_at(tmp_path: Path):
    rec = ManifestRecorder.start(project_dir=str(tmp_path), workflow="wf")
    rec.finish("success")
    payload = json.loads(rec.path.read_text())
    assert payload["status"] == "success"
    assert payload["ended_at"] is not None


def test_finish_with_error_records_error(tmp_path: Path):
    rec = ManifestRecorder.start(project_dir=str(tmp_path), workflow="wf")
    rec.finish("error", error="boom")
    payload = json.loads(rec.path.read_text())
    assert payload["status"] == "error"
    assert payload["error"] == "boom"


def test_source_ids_dedup(tmp_path: Path):
    rec = ManifestRecorder.start(project_dir=str(tmp_path), workflow="wf")
    rec.update(source_ids=["s1", "s2"])
    rec.update(source_ids=["s2", "s3"])
    payload = json.loads(rec.path.read_text())
    assert payload["source_ids"] == ["s1", "s2", "s3"]


def test_runs_directory_layout(tmp_path: Path):
    rec = ManifestRecorder.start(project_dir=str(tmp_path), workflow="wf")
    expected = tmp_path / "runs" / rec.manifest.run_id / "manifest.json"
    assert expected == rec.path


def test_project_sha_excludes_runs_directory(tmp_path: Path):
    """Adding a manifest under runs/ must not change the project SHA."""
    (tmp_path / "input_files").mkdir()
    (tmp_path / "input_files" / "data_description.md").write_text("hello")

    sha_before = _project_sha(tmp_path)
    ManifestRecorder.start(project_dir=str(tmp_path), workflow="wf")
    sha_after = _project_sha(tmp_path)
    assert sha_before == sha_after, "runs/ contents must not contribute to project SHA"


def test_run_manifest_pydantic_round_trip():
    """RunManifest serializes and deserializes via Pydantic JSON mode."""
    from datetime import datetime, timezone

    m = RunManifest(
        run_id="x" * 12,
        workflow="get_paper",
        started_at=datetime.now(timezone.utc),
    )
    payload = m.model_dump(mode="json")
    restored = RunManifest.model_validate(payload)
    assert restored.run_id == m.run_id
    assert restored.workflow == m.workflow
