"""TelemetryCollector class facade over the JSONL sink."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from plato.state.manifest import ManifestRecorder
from plato.state.telemetry_collector import TelemetryCollector


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``Path.home()`` so default-path resolution lands in tmp."""
    monkeypatch.delenv("PLATO_TELEMETRY_DISABLED", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def test_record_run_summary_round_trips_a_real_manifest(
    isolated_home: Path, tmp_path: Path
):
    """End-to-end: ManifestRecorder writes manifest.json -> collector picks it up.

    This proves the collector's parser matches what the recorder
    actually persists (no silent schema drift between the two).
    """
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    sink = isolated_home / "telemetry.jsonl"
    collector = TelemetryCollector(storage_path=sink)

    rec = ManifestRecorder.start(
        project_dir=str(project_dir),
        workflow="get_idea_fast",
        user_id="alice",
        project_id="proj-1",
    )
    rec.update(models={"idea_maker": "gpt-4.1"})
    rec.add_tokens(input_tokens=120, output_tokens=240, cost_usd=0.0042)
    rec.finish("success")

    # The recorder's own _emit_telemetry hits the default ~/.plato path
    # (which is the patched isolated_home), not our explicit sink.
    # Reset and replay through the collector to exercise its parser.
    sink.write_text("")  # clear

    wrote = collector.record_run_summary(rec.path)
    assert wrote is True
    lines = [json.loads(line) for line in sink.read_text().splitlines() if line]
    assert len(lines) == 1
    record = lines[0]

    assert record["run_id"] == rec.manifest.run_id
    assert record["workflow"] == "get_idea_fast"
    assert record["status"] == "success"
    assert record["tokens_in"] == 120
    assert record["tokens_out"] == 240
    assert record["cost_usd"] == pytest.approx(0.0042)
    assert record["user_id"] == "alice"
    assert record["project_id"] == "proj-1"
    assert record["model"] == "gpt-4.1"
    assert record["duration_seconds"] is not None and record["duration_seconds"] >= 0
    # No leakage of fields outside the whitelist.
    assert "domain" not in record
    assert "git_sha" not in record
    assert "tokens_per_node" not in record


def test_record_run_summary_no_op_when_disabled(
    isolated_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PLATO_TELEMETRY_DISABLED", "1")
    sink = isolated_home / "telemetry.jsonl"
    collector = TelemetryCollector(storage_path=sink)

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": "rid",
                "workflow": "wf",
                "status": "success",
                "started_at": "2026-05-02T12:00:00+00:00",
                "ended_at": "2026-05-02T12:00:05+00:00",
                "tokens_in": 1,
                "tokens_out": 2,
                "cost_usd": 0.0,
            }
        )
    )
    assert collector.record_run_summary(manifest_path) is False
    assert not sink.exists()


def test_record_run_summary_handles_missing_manifest(
    isolated_home: Path, tmp_path: Path
):
    """Bad path → returns False, no crash, no file written."""
    sink = isolated_home / "telemetry.jsonl"
    collector = TelemetryCollector(storage_path=sink)
    assert collector.record_run_summary(tmp_path / "does-not-exist.json") is False
    assert not sink.exists()


def test_record_run_summary_handles_corrupt_manifest(
    isolated_home: Path, tmp_path: Path
):
    """Garbled manifest → returns False, never raises."""
    sink = isolated_home / "telemetry.jsonl"
    bad = tmp_path / "manifest.json"
    bad.write_text("{not valid json")
    collector = TelemetryCollector(storage_path=sink)
    assert collector.record_run_summary(bad) is False
    assert not sink.exists()


def test_read_recent_returns_newest_first_with_limit(
    isolated_home: Path,
):
    sink = isolated_home / "telemetry.jsonl"
    sink.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({"run_id": f"rid-{i}", "workflow": "wf", "status": "success"})
        for i in range(10)
    ]
    sink.write_text("\n".join(lines) + "\n")

    collector = TelemetryCollector(storage_path=sink)
    recent = collector.read_recent(limit=3)
    assert [r["run_id"] for r in recent] == ["rid-9", "rid-8", "rid-7"]


def test_read_recent_skips_malformed_lines(isolated_home: Path):
    """A garbage line must not blank the slice for everyone after it."""
    sink = isolated_home / "telemetry.jsonl"
    sink.parent.mkdir(parents=True, exist_ok=True)
    sink.write_text(
        '{"run_id":"a","workflow":"wf"}\n'
        "this is not json\n"
        '{"run_id":"b","workflow":"wf"}\n'
        '"a string, not an object"\n'
        '{"run_id":"c","workflow":"wf"}\n'
    )
    collector = TelemetryCollector(storage_path=sink)
    recent = collector.read_recent(limit=10)
    # Newest-first: c, b, a.
    assert [r["run_id"] for r in recent] == ["c", "b", "a"]


def test_read_recent_returns_empty_for_missing_file(isolated_home: Path):
    sink = isolated_home / "telemetry.jsonl"
    collector = TelemetryCollector(storage_path=sink)
    assert collector.read_recent(limit=10) == []


def test_read_recent_zero_limit_short_circuits(isolated_home: Path):
    """``limit=0`` returns [] without touching disk."""
    sink = isolated_home / "telemetry.jsonl"
    sink.parent.mkdir(parents=True, exist_ok=True)
    sink.write_text(
        '{"run_id":"a","workflow":"wf"}\n'
    )
    collector = TelemetryCollector(storage_path=sink)
    assert collector.read_recent(limit=0) == []


def test_storage_path_falls_back_to_default(
    isolated_home: Path,
):
    """Default ctor → ``~/.plato/telemetry.jsonl`` under the patched home."""
    collector = TelemetryCollector()
    assert collector.storage_path == isolated_home / ".plato" / "telemetry.jsonl"
