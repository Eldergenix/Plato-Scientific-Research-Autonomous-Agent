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


# --- Added edge-case tests below this line ---------------------------------


def test_record_prompt_hash_is_stable_across_calls() -> None:
    """Same prompt + same node must produce byte-identical digests on repeat."""
    rec1 = _FakeRecorder()
    rec2 = _FakeRecorder()
    state1 = {"recorder": rec1, "_last_prompt": "deterministic input"}
    state2 = {"recorder": rec2, "_last_prompt": "deterministic input"}

    _record_prompt_hash(state1, node_name="n")
    _record_prompt_hash(state2, node_name="n")

    assert rec1.calls[0]["prompt_hashes"]["n"] == rec2.calls[0]["prompt_hashes"]["n"]


def test_record_prompt_hash_distinguishes_different_prompts() -> None:
    """Different prompts must produce different digests."""
    rec = _FakeRecorder()
    state_a = {"recorder": rec, "_last_prompt": "prompt A"}
    state_b = {"recorder": rec, "_last_prompt": "prompt B"}

    _record_prompt_hash(state_a, node_name="n")
    _record_prompt_hash(state_b, node_name="n")

    assert rec.calls[0]["prompt_hashes"]["n"] != rec.calls[1]["prompt_hashes"]["n"]


def test_record_prompt_hash_empty_prompt_falls_back_to_empty_string() -> None:
    """Missing _last_prompt key defaults to empty string and still hashes."""
    rec = _FakeRecorder()
    state: dict = {"recorder": rec}  # no _last_prompt at all

    _record_prompt_hash(state, node_name="cold_start")

    assert len(rec.calls) == 1
    expected = hashlib.sha256(b"").hexdigest()
    assert rec.calls[0]["prompt_hashes"]["cold_start"] == expected


def test_record_prompt_hash_empty_node_name_string_is_noop() -> None:
    """An empty-string node_name is falsy and must skip recording."""
    rec = _FakeRecorder()
    state = {"recorder": rec, "_last_prompt": "x"}
    _record_prompt_hash(state, node_name="")
    assert rec.calls == []


def test_record_prompt_hash_unicode_prompt_uses_utf8_encoding() -> None:
    """Non-ASCII prompt must round-trip through utf-8 cleanly."""
    rec = _FakeRecorder()
    prompt = "résumé 你好 🚀"
    state = {"recorder": rec, "_last_prompt": prompt}

    _record_prompt_hash(state, node_name="i18n")

    expected = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert rec.calls[0]["prompt_hashes"]["i18n"] == expected


def test_record_prompt_hash_none_state_is_noop() -> None:
    """A None state should hit the isinstance check and silently no-op."""
    _record_prompt_hash(None, node_name="any")  # type: ignore[arg-type]


def test_record_prompt_hash_dict_state_with_no_recorder_key_is_noop() -> None:
    """state.get('recorder') returns None when the key is absent — no raise."""
    state = {"_last_prompt": "no recorder field at all"}
    _record_prompt_hash(state, node_name="n")
    # Test passes by virtue of not raising.
    assert "recorder" not in state
