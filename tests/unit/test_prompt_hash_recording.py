"""R9 — verify LLM_call / LLM_call_stream record sha256(prompt) when a recorder is in scope."""
from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from plato.paper_agents.tools import _record_prompt_hash


class _FakeRecorder:
    """Minimal stand-in for ManifestRecorder that records updates."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def update(self, **fields) -> None:
        self.calls.append(fields)


def test_record_prompt_hash_writes_sha256_under_node_name() -> None:
    rec = _FakeRecorder()
    state = {"recorder": rec, "_last_prompt": "Hello, world."}

    _record_prompt_hash(state, node_name="my_node")

    assert len(rec.calls) == 1
    payload = rec.calls[0]["prompt_hashes"]
    expected = hashlib.sha256(b"Hello, world.").hexdigest()
    assert payload == {"my_node": expected}


def test_record_prompt_hash_no_recorder_is_noop() -> None:
    state = {"_last_prompt": "x"}
    # Doesn't raise — silently skips when recorder is missing.
    _record_prompt_hash(state, node_name="any")


def test_record_prompt_hash_no_node_name_is_noop() -> None:
    rec = _FakeRecorder()
    state = {"recorder": rec, "_last_prompt": "x"}
    _record_prompt_hash(state, node_name=None)
    assert rec.calls == []


def test_record_prompt_hash_handles_list_prompt() -> None:
    """LangChain-style list-of-message prompts must hash the str repr."""
    rec = _FakeRecorder()
    msg1 = MagicMock()
    msg1.__repr__ = lambda self: "Sys"
    msg2 = MagicMock()
    msg2.__repr__ = lambda self: "Hum"
    state = {"recorder": rec, "_last_prompt": [msg1, msg2]}

    _record_prompt_hash(state, node_name="literature")

    digest = rec.calls[0]["prompt_hashes"]["literature"]
    expected = hashlib.sha256(str([msg1, msg2]).encode("utf-8")).hexdigest()
    assert digest == expected


def test_record_prompt_hash_recorder_failure_is_swallowed() -> None:
    """A recorder that raises must not crash the LLM call path."""
    rec = MagicMock()
    rec.update.side_effect = RuntimeError("manifest write failed")
    state = {"recorder": rec, "_last_prompt": "x"}

    # Should not raise.
    _record_prompt_hash(state, node_name="boom")


def test_record_prompt_hash_string_state_is_noop() -> None:
    """Defensive: non-dict state must not crash."""
    _record_prompt_hash("not a dict", node_name="any")  # type: ignore[arg-type]
