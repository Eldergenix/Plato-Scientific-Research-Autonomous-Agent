"""Local-only telemetry sink (plato.state.telemetry)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from plato.state.telemetry import append_run_summary, is_enabled, read_recent
from plato.state.manifest import ManifestRecorder


@pytest.fixture
def isolated_dest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Use a tmp telemetry file and clear the disable env var."""
    monkeypatch.delenv("PLATO_TELEMETRY_DISABLED", raising=False)
    # Override Path.home() so any preferences-file lookup or default-dest
    # resolution lands under tmp_path instead of the developer's real
    # ~/.plato. ``HOME`` env var alone isn't enough on macOS — Python's
    # Path.home() falls back to pwd.getpwuid().
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path / "telemetry.jsonl"


def test_append_writes_one_jsonl_line_per_call(isolated_dest: Path):
    summary = {
        "timestamp": "2026-05-02T12:00:00+00:00",
        "run_id": "abc123",
        "workflow": "get_idea_fast",
        "duration_seconds": 4.2,
        "tokens_in": 100,
        "tokens_out": 50,
        "cost_usd": 0.0015,
        "status": "success",
    }
    append_run_summary(summary, dest_path=isolated_dest)
    append_run_summary({**summary, "run_id": "def456"}, dest_path=isolated_dest)

    lines = isolated_dest.read_text().strip().splitlines()
    assert len(lines) == 2
    decoded = [json.loads(line) for line in lines]
    assert decoded[0]["run_id"] == "abc123"
    assert decoded[1]["run_id"] == "def456"
    assert decoded[0]["status"] == "success"


def test_append_drops_unknown_fields(isolated_dest: Path):
    """Anything outside the whitelist is silently stripped."""
    append_run_summary(
        {
            "timestamp": "2026-05-02T12:00:00+00:00",
            "run_id": "rid",
            "workflow": "wf",
            "tokens_in": 1,
            "tokens_out": 2,
            "cost_usd": 0.0,
            "status": "success",
            "user_prompt": "should NOT be persisted",
            "secret_token": "leak",
        },
        dest_path=isolated_dest,
    )
    record = json.loads(isolated_dest.read_text().strip())
    assert "user_prompt" not in record
    assert "secret_token" not in record


def test_env_kill_switch_skips_write(isolated_dest: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATO_TELEMETRY_DISABLED", "1")
    assert is_enabled() is False
    append_run_summary(
        {"run_id": "x", "workflow": "wf", "status": "success"},
        dest_path=isolated_dest,
    )
    assert not isolated_dest.exists()


def test_user_prefs_disabled_skips_write(
    isolated_dest: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """When user_preferences.json sets telemetry_enabled=False, no write."""
    prefs_dir = tmp_path / ".plato" / "users" / "__anon__"
    prefs_dir.mkdir(parents=True)
    (prefs_dir / "preferences.json").write_text(
        json.dumps({"telemetry_enabled": False})
    )

    assert is_enabled() is False
    append_run_summary(
        {"run_id": "x", "workflow": "wf", "status": "success"},
        dest_path=isolated_dest,
    )
    assert not isolated_dest.exists()


def test_read_recent_returns_last_n(isolated_dest: Path):
    for i in range(50):
        append_run_summary(
            {
                "timestamp": f"2026-05-02T12:00:{i:02d}+00:00",
                "run_id": f"rid-{i}",
                "workflow": "wf",
                "tokens_in": i,
                "tokens_out": i,
                "cost_usd": 0.001 * i,
                "status": "success",
            },
            dest_path=isolated_dest,
        )

    recent = read_recent(n=30, src_path=isolated_dest)
    assert len(recent) == 30
    assert recent[0]["run_id"] == "rid-20"
    assert recent[-1]["run_id"] == "rid-49"


def test_read_recent_skips_corrupt_lines(isolated_dest: Path):
    """A garbled line shouldn't blank the whole panel."""
    isolated_dest.parent.mkdir(parents=True, exist_ok=True)
    isolated_dest.write_text(
        '{"run_id":"a","workflow":"wf"}\n'
        "this is not json\n"
        '{"run_id":"b","workflow":"wf"}\n'
    )
    recent = read_recent(n=10, src_path=isolated_dest)
    assert [r["run_id"] for r in recent] == ["a", "b"]


def test_manifest_finish_appends_summary(
    isolated_dest: Path,
    tmp_path: Path,
):
    """End-to-end: ManifestRecorder.finish() should write through to the sink."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    rec = ManifestRecorder.start(project_dir=str(project_dir), workflow="wf_xyz")
    rec.add_tokens(input_tokens=10, output_tokens=20, cost_usd=0.01)
    rec.finish("success")

    default_path = tmp_path / ".plato" / "telemetry.jsonl"
    assert default_path.exists()
    line = json.loads(default_path.read_text().strip().splitlines()[-1])
    assert line["workflow"] == "wf_xyz"
    assert line["tokens_in"] == 10
    assert line["tokens_out"] == 20
    assert line["status"] == "success"
    assert line["duration_seconds"] is not None and line["duration_seconds"] >= 0
