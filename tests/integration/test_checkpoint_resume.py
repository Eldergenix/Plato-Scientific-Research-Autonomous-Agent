"""Phase 1 — R2 verification: checkpoint resume across graph restarts.

Validates the acceptance criterion: kill mid-graph, restart with the same
``thread_id``, and assert state continues from the last checkpoint.

We deliberately use a tiny inline ``StateGraph`` instead of Plato's full graph
so the test is fast, deterministic, and free of LLM/network dependencies. The
behavior under test is purely the LangGraph checkpoint contract that
``make_checkpointer`` plugs into.
"""
from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph

from plato.state import make_checkpointer


class _CounterState(TypedDict, total=False):
    counter: int


def _step1(state: _CounterState) -> _CounterState:
    return {"counter": state.get("counter", 0) + 1}


def _step2(state: _CounterState) -> _CounterState:
    return {"counter": state.get("counter", 0) + 10}


def _build(checkpointer, *, halt_after: int = 1):
    """Compile a 2-node counter graph that halts after step1 if ``halt_after==1``."""
    g = StateGraph(_CounterState)
    g.add_node("step1", _step1)
    g.add_node("step2", _step2)
    g.add_edge(START, "step1")

    def router(_state: _CounterState):
        return END if halt_after == 1 else "step2"

    g.add_conditional_edges("step1", router)
    g.add_edge("step2", END)
    return g.compile(checkpointer=checkpointer)


def test_sqlite_checkpoint_persists_across_invocations(tmp_path: Path):
    """A SQLite checkpointer survives discarding the in-memory graph object.

    Simulates the crash-resume case: invoke once under thread "T1", drop the
    graph and the checkpointer, rebuild both pointing at the same DB file, and
    assert that the state for "T1" is still there.
    """
    pytest.importorskip("langgraph.checkpoint.sqlite")

    db_path = tmp_path / "state.db"
    config = {"configurable": {"thread_id": "T1"}}

    cp_first = make_checkpointer("sqlite", path=str(db_path))
    graph_first = _build(cp_first, halt_after=1)
    out = graph_first.invoke({"counter": 0}, config=config)
    assert out == {"counter": 1}

    # Discard everything we held in memory, including any sqlite connection.
    del graph_first
    del cp_first

    cp_resumed = make_checkpointer("sqlite", path=str(db_path))
    graph_resumed = _build(cp_resumed, halt_after=1)

    snapshot = graph_resumed.get_state(config=config)
    assert snapshot.values == {"counter": 1}, (
        "Expected the step1 increment from invocation #1 to be preserved on disk; "
        f"got {snapshot.values!r}."
    )
    # The first run terminated at END, so there are no pending nodes to continue.
    assert snapshot.next == ()


def test_memory_checkpointer_does_not_persist_across_instances():
    """Control: ``MemorySaver`` is per-instance. A fresh instance starts empty."""
    config = {"configurable": {"thread_id": "T1"}}

    cp_first = make_checkpointer("memory")
    graph_first = _build(cp_first, halt_after=1)
    out = graph_first.invoke({"counter": 0}, config=config)
    assert out == {"counter": 1}

    cp_second = make_checkpointer("memory")
    graph_second = _build(cp_second, halt_after=1)
    snapshot = graph_second.get_state(config=config)

    assert snapshot.values == {}, (
        "MemorySaver must not leak state across instances; "
        f"got {snapshot.values!r}."
    )
    assert snapshot.created_at is None


def test_two_threads_isolated(tmp_path: Path):
    """Different ``thread_id`` values must not bleed into each other on SQLite."""
    pytest.importorskip("langgraph.checkpoint.sqlite")

    db_path = tmp_path / "state.db"

    cp = make_checkpointer("sqlite", path=str(db_path))
    graph = _build(cp, halt_after=1)

    out_a = graph.invoke({"counter": 0}, config={"configurable": {"thread_id": "A"}})
    out_b = graph.invoke({"counter": 0}, config={"configurable": {"thread_id": "B"}})
    assert out_a == {"counter": 1}
    assert out_b == {"counter": 1}

    # Rebuild with a fresh checkpointer pointing at the same DB and check both
    # threads independently.
    cp_resumed = make_checkpointer("sqlite", path=str(db_path))
    graph_resumed = _build(cp_resumed, halt_after=1)

    snap_a = graph_resumed.get_state(config={"configurable": {"thread_id": "A"}})
    snap_b = graph_resumed.get_state(config={"configurable": {"thread_id": "B"}})

    assert snap_a.values == {"counter": 1}
    assert snap_b.values == {"counter": 1}

    # Advance only thread A and confirm thread B is untouched.
    out_a2 = graph_resumed.invoke(
        {"counter": 5}, config={"configurable": {"thread_id": "A"}}
    )
    assert out_a2 == {"counter": 6}

    snap_b_after = graph_resumed.get_state(
        config={"configurable": {"thread_id": "B"}}
    )
    assert snap_b_after.values == {"counter": 1}, (
        "Mutating thread A must not affect thread B; "
        f"got B={snap_b_after.values!r}."
    )
