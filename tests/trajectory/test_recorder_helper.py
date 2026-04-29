"""Unit tests for the trajectory recorder helper itself."""
from __future__ import annotations

import asyncio

from tests.trajectory._recorder import TrajectoryRecorder, ordered_substring


def test_wrap_sync_preserves_return_value():
    rec = TrajectoryRecorder()

    def node(state, config):
        return {"echo": state["x"]}

    wrapped = rec.wrap("node", node)
    out = wrapped({"x": 7}, {})
    assert out == {"echo": 7}
    assert rec.calls == ["node"]


def test_wrap_async_preserves_return_value():
    rec = TrajectoryRecorder()

    async def node(state, config):
        return {"echo": state["x"] * 2}

    wrapped = rec.wrap("anode", node)
    out = asyncio.run(wrapped({"x": 5}, {}))
    assert out == {"echo": 10}
    assert rec.calls == ["anode"]


def test_wrap_records_in_call_order():
    rec = TrajectoryRecorder()

    def a(state, config): return state
    def b(state, config): return state

    wa = rec.wrap("a", a)
    wb = rec.wrap("b", b)

    wa({}, {}); wb({}, {}); wa({}, {})
    assert rec.calls == ["a", "b", "a"]


def test_ordered_substring_subsequence():
    assert ordered_substring(["a", "b", "c", "d"], ["b", "c"]) is True


def test_ordered_substring_wrong_order():
    assert ordered_substring(["a", "c", "b", "d"], ["b", "c"]) is False


def test_ordered_substring_missing_element():
    assert ordered_substring(["a", "b", "c"], ["b", "z"]) is False


def test_ordered_substring_empty_needle():
    # vacuously true
    assert ordered_substring(["a", "b"], []) is True


def test_ordered_substring_non_contiguous_match():
    assert ordered_substring(["a", "x", "b", "y", "c"], ["a", "b", "c"]) is True
