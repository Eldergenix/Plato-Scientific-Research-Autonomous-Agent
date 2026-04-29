"""Structural tests for the idea/literature/methods/referee LangGraph."""
from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver

from plato.langgraph_agents.agents_graph import build_lg_graph


STABLE_NODES = {
    "preprocess_node",
    "maker",
    "hater",
    "methods",
    "novelty",
    "semantic_scholar",
    "literature_summary",
    "referee",
}


@pytest.fixture(scope="module")
def idea_graph():
    return build_lg_graph(checkpointer=MemorySaver())


def test_idea_graph_compiles(idea_graph):
    # The compile() call already happened in the fixture; here we just
    # confirm the resulting object exposes the expected interface.
    assert idea_graph is not None
    assert hasattr(idea_graph, "get_graph")
    assert hasattr(idea_graph, "builder")
    nodes = idea_graph.get_graph().nodes
    assert len(nodes) >= len(STABLE_NODES)


def test_idea_graph_static_node_set(idea_graph):
    nodes = set(idea_graph.get_graph().nodes.keys())
    missing = STABLE_NODES - nodes
    assert not missing, f"stable idea-graph nodes missing: {sorted(missing)}"


def test_idea_graph_idea_loop_edge(idea_graph):
    # The hater -> maker edge is a direct edge; conditional edges from
    # maker back to hater are routed via ``router`` and don't show up in
    # the edge set, which is fine — the loop-back edge is what we care
    # about for trajectory invariants.
    edges = idea_graph.builder.edges
    assert ("hater", "maker") in edges, (
        f"missing iterative-debate loop edge hater -> maker, got {sorted(edges)}"
    )


def test_idea_graph_terminal_edges(idea_graph):
    """Sanity: methods/literature_summary/referee all terminate the graph."""
    edges = idea_graph.builder.edges
    for terminal in ("methods", "literature_summary", "referee"):
        assert (terminal, "__end__") in edges, (
            f"expected {terminal} -> __end__, got {sorted(edges)}"
        )


def test_idea_graph_semantic_scholar_to_novelty(idea_graph):
    edges = idea_graph.builder.edges
    assert ("semantic_scholar", "novelty") in edges, (
        f"missing edge semantic_scholar -> novelty, got {sorted(edges)}"
    )
