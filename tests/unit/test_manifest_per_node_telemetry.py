"""Phase 3 telemetry — verify per-node token/cost breakdown lands on the manifest.

Covers the full path:
- ``_record_node_tokens`` accumulates calls/tokens/cost into the right bucket.
- ``LLM_call`` invokes the helper with the supplied ``node_name`` so totals on
  the manifest line up with the LangChain callback.
- The new ``tokens_per_node`` field is backwards-compatible: a manifest
  written before the field existed must still validate.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from plato.paper_agents.tools import LLM_call, _record_node_tokens
from plato.state.manifest import ManifestRecorder, RunManifest


def _fake_state(tmp_path: Path, recorder: ManifestRecorder, llm) -> dict:
    """Build the minimum state dict LLM_call touches."""
    log = tmp_path / "llm_calls.log"
    log.touch()
    return {
        "recorder": recorder,
        "llm": {"llm": llm, "max_output_tokens": 10_000},
        "tokens": {"i": 0, "o": 0, "ti": 0, "to": 0},
        "files": {"LLM_calls": str(log)},
    }


def _fake_message(input_tokens: int, output_tokens: int, content: str = "ok"):
    return SimpleNamespace(
        content=content,
        usage_metadata={"input_tokens": input_tokens, "output_tokens": output_tokens},
    )


def test_record_node_tokens_accumulates_calls(tmp_path: Path) -> None:
    """Two calls under the same node_name → calls=2 and tokens summed."""
    rec = ManifestRecorder.start(project_dir=str(tmp_path), workflow="wf")
    rec.update(models={"idea": "gpt-4o-mini"})

    state = {"recorder": rec}
    _record_node_tokens(state, "my_node", 100, 50)
    _record_node_tokens(state, "my_node", 200, 75)

    bucket = rec.manifest.tokens_per_node["my_node"]
    assert bucket["calls"] == 2
    assert bucket["ti"] == 300
    assert bucket["to"] == 125
    # gpt-4o-mini: $0.15 in / $0.60 out per 1M tokens
    expected_cost = (300 * 0.15 + 125 * 0.60) / 1_000_000
    assert bucket["cost_usd"] == pytest.approx(expected_cost)


def test_record_node_tokens_separates_by_node_name(tmp_path: Path) -> None:
    rec = ManifestRecorder.start(project_dir=str(tmp_path), workflow="wf")
    rec.update(models={"idea": "gpt-4o-mini"})

    state = {"recorder": rec}
    _record_node_tokens(state, "node_a", 10, 5)
    _record_node_tokens(state, "node_b", 20, 10)
    _record_node_tokens(state, "node_a", 30, 15)

    per_node = rec.manifest.tokens_per_node
    assert set(per_node.keys()) == {"node_a", "node_b"}
    assert per_node["node_a"]["calls"] == 2
    assert per_node["node_a"]["ti"] == 40
    assert per_node["node_b"]["calls"] == 1
    assert per_node["node_b"]["ti"] == 20


def test_record_node_tokens_no_recorder_is_noop() -> None:
    # No recorder in state: must not raise.
    _record_node_tokens({}, "x", 1, 1)


def test_record_node_tokens_no_node_name_is_noop(tmp_path: Path) -> None:
    rec = ManifestRecorder.start(project_dir=str(tmp_path), workflow="wf")
    _record_node_tokens({"recorder": rec}, None, 1, 1)
    assert rec.manifest.tokens_per_node == {}


def test_llm_call_records_per_node_telemetry(tmp_path: Path) -> None:
    """LLM_call invoked twice with same node_name → calls=2 on the manifest."""
    rec = ManifestRecorder.start(project_dir=str(tmp_path), workflow="wf")
    rec.update(models={"idea": "gpt-4o-mini"})

    llm = MagicMock()
    llm.invoke.side_effect = [
        _fake_message(input_tokens=100, output_tokens=40),
        _fake_message(input_tokens=120, output_tokens=60),
    ]
    state = _fake_state(tmp_path, rec, llm)

    state, _ = LLM_call("hello", state, node_name="my_node")
    state, _ = LLM_call("world", state, node_name="my_node")

    bucket = rec.manifest.tokens_per_node["my_node"]
    assert bucket["calls"] == 2
    assert bucket["ti"] == 220
    assert bucket["to"] == 100


def test_llm_call_separates_distinct_node_names(tmp_path: Path) -> None:
    rec = ManifestRecorder.start(project_dir=str(tmp_path), workflow="wf")
    rec.update(models={"idea": "gpt-4o-mini"})

    llm = MagicMock()
    llm.invoke.side_effect = [
        _fake_message(input_tokens=10, output_tokens=5),
        _fake_message(input_tokens=20, output_tokens=10),
    ]
    state = _fake_state(tmp_path, rec, llm)

    state, _ = LLM_call("p1", state, node_name="alpha")
    state, _ = LLM_call("p2", state, node_name="beta")

    per_node = rec.manifest.tokens_per_node
    assert per_node["alpha"]["calls"] == 1
    assert per_node["alpha"]["ti"] == 10
    assert per_node["beta"]["calls"] == 1
    assert per_node["beta"]["ti"] == 20


def test_llm_call_without_node_name_skips_telemetry(tmp_path: Path) -> None:
    rec = ManifestRecorder.start(project_dir=str(tmp_path), workflow="wf")
    rec.update(models={"idea": "gpt-4o-mini"})

    llm = MagicMock()
    llm.invoke.return_value = _fake_message(input_tokens=10, output_tokens=5)
    state = _fake_state(tmp_path, rec, llm)

    state, _ = LLM_call("p", state)

    assert rec.manifest.tokens_per_node == {}


def test_manifest_persists_tokens_per_node(tmp_path: Path) -> None:
    """The new field round-trips through the on-disk JSON."""
    rec = ManifestRecorder.start(project_dir=str(tmp_path), workflow="wf")
    rec.update(models={"idea": "gpt-4o-mini"})
    _record_node_tokens({"recorder": rec}, "n", 10, 5)

    payload = json.loads(rec.path.read_text())
    assert "tokens_per_node" in payload
    assert payload["tokens_per_node"]["n"]["calls"] == 1
    assert payload["tokens_per_node"]["n"]["ti"] == 10
    assert payload["tokens_per_node"]["n"]["to"] == 5


def test_legacy_manifest_without_tokens_per_node_loads(tmp_path: Path) -> None:
    """Backwards-compat: a pre-Phase-3 manifest dict still validates.

    Pydantic uses the ``default_factory=dict`` so the missing key resolves to
    an empty dict — no migration required.
    """
    legacy = {
        "run_id": "abc123",
        "workflow": "get_idea_fast",
        "started_at": "2026-04-01T00:00:00+00:00",
        "domain": "astro",
        "git_sha": "",
        "project_sha": "",
        "models": {"idea": "gpt-4o-mini"},
        "prompt_hashes": {},
        "seeds": {},
        "source_ids": [],
        "cost_usd": 0.0,
        "tokens_in": 0,
        "tokens_out": 0,
        # NOTE: no tokens_per_node key.
        "extra": {},
    }
    m = RunManifest.model_validate(legacy)
    assert m.tokens_per_node == {}
    assert m.run_id == "abc123"
