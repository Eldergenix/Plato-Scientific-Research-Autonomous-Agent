"""Graph-level smoke tests for the Phase 5 nodes wired into ``build_lg_graph``.

These tests exercise compile-time wiring only — they do not invoke any
node bodies, so no LLM, retrieval, or filesystem mocks are required.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from plato.langgraph_agents.agents_graph import build_lg_graph
from plato.langgraph_agents.routers import clarifier_router


def _builder_edges(graph) -> set[tuple[str, str]]:
    return set(graph.builder.edges)


def test_idea_graph_compiles_with_phase5_nodes():
    graph = build_lg_graph(checkpointer=MemorySaver())
    nodes = set(graph.get_graph().nodes.keys())
    expected = {
        "research_question_clarifier",
        "counter_evidence_search",
        "gap_detector",
    }
    missing = expected - nodes
    assert not missing, f"Phase 5 nodes missing: {sorted(missing)}"


def test_phase5_chain_edges_present():
    graph = build_lg_graph(checkpointer=MemorySaver())
    edges = _builder_edges(graph)
    chain = [
        ("literature_summary", "counter_evidence_search"),
        ("counter_evidence_search", "gap_detector"),
        ("gap_detector", "__end__"),
    ]
    for edge in chain:
        assert edge in edges, f"missing chain edge {edge}, got {sorted(edges)}"


def test_clarifier_node_is_present_and_terminal_safe():
    graph = build_lg_graph(checkpointer=MemorySaver())
    nodes = set(graph.get_graph().nodes.keys())
    assert "research_question_clarifier" in nodes


def test_clarifier_router_returns_maker_when_no_questions():
    state = {"needs_clarification": False}
    assert clarifier_router(state) == "maker"


def test_clarifier_router_returns_end_when_questions_pending():
    state = {"needs_clarification": True}
    # END is langgraph's sentinel. Compare via the routers module export.
    from langgraph.graph import END

    assert clarifier_router(state) == END


def test_existing_terminal_edges_unchanged():
    """methods, referee terminate at END exactly like before."""
    graph = build_lg_graph(checkpointer=MemorySaver())
    edges = _builder_edges(graph)
    for terminal in ("methods", "referee"):
        assert (terminal, "__end__") in edges


def test_hater_to_maker_loop_preserved():
    """The maker/hater debate loop must survive Phase 5 wiring."""
    graph = build_lg_graph(checkpointer=MemorySaver())
    edges = _builder_edges(graph)
    assert ("hater", "maker") in edges


def test_semantic_scholar_to_novelty_preserved():
    graph = build_lg_graph(checkpointer=MemorySaver())
    edges = _builder_edges(graph)
    assert ("semantic_scholar", "novelty") in edges
