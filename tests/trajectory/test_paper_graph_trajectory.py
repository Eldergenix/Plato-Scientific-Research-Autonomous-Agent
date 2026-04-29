"""Structural / trajectory tests for the paper-writing LangGraph.

These tests intentionally only assert on the *stable* node set that exists
on main today. Streams adding new nodes (e.g. citation_validator_node,
evidence_matrix_node) are expected to keep the existing nodes intact, so
``set(stable) <= set(g.get_graph().nodes)`` should remain a safe invariant.
"""
from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver

from plato.paper_agents.agents_graph import build_graph


STABLE_NODES = {
    "preprocess_node",
    "keywords_node",
    "abstract_node",
    "introduction_node",
    "methods_node",
    "results_node",
    "conclusions_node",
    "plots_node",
    "refine_results",
    "citations_node",
    "reviewer_panel_fanout",
    "methodology_reviewer",
    "statistics_reviewer",
    "novelty_reviewer",
    "writing_reviewer",
    "critique_aggregator",
    "redraft_node",
}

REVIEWER_NODES = {
    "methodology_reviewer",
    "statistics_reviewer",
    "novelty_reviewer",
    "writing_reviewer",
}


@pytest.fixture(scope="module")
def paper_graph():
    return build_graph(checkpointer=MemorySaver())


def test_paper_graph_compiles(paper_graph):
    nodes = paper_graph.get_graph().nodes
    # 17 stable + __start__ + __end__ at minimum
    assert len(nodes) >= 17, f"expected >=17 nodes, got {len(nodes)}: {sorted(nodes)}"


def test_paper_graph_static_node_set(paper_graph):
    nodes = set(paper_graph.get_graph().nodes.keys())
    missing = STABLE_NODES - nodes
    assert not missing, f"stable nodes missing from compiled graph: {sorted(missing)}"


def test_paper_graph_keywords_before_abstract(paper_graph):
    # The compiled graph view drops unreachable subgraphs; the builder's
    # raw edge set is the source of truth for declared structure.
    edges = paper_graph.builder.edges
    assert ("keywords_node", "abstract_node") in edges, (
        f"expected direct edge keywords_node -> abstract_node, got {sorted(edges)}"
    )


def test_paper_graph_reviewer_panel_present(paper_graph):
    nodes = set(paper_graph.get_graph().nodes.keys())
    missing = REVIEWER_NODES - nodes
    assert not missing, f"reviewer nodes missing: {sorted(missing)}"

    edges = paper_graph.builder.edges
    for reviewer in REVIEWER_NODES:
        assert (reviewer, "critique_aggregator") in edges, (
            f"reviewer {reviewer!r} does not feed critique_aggregator"
        )
        assert ("reviewer_panel_fanout", reviewer) in edges, (
            f"reviewer_panel_fanout does not fan out to {reviewer!r}"
        )


def test_paper_graph_revision_loop_edge(paper_graph):
    edges = paper_graph.builder.edges
    assert ("redraft_node", "reviewer_panel_fanout") in edges, (
        f"missing revision loop-back edge redraft_node -> reviewer_panel_fanout, "
        f"got {sorted(edges)}"
    )


def test_paper_graph_pipeline_chain(paper_graph):
    """Sanity: drafting nodes form the expected linear chain."""
    edges = paper_graph.builder.edges
    chain = [
        ("preprocess_node", "keywords_node"),
        ("keywords_node", "abstract_node"),
        ("abstract_node", "introduction_node"),
        ("introduction_node", "methods_node"),
        ("methods_node", "results_node"),
        ("results_node", "conclusions_node"),
        ("conclusions_node", "plots_node"),
        ("plots_node", "refine_results"),
    ]
    for src, dst in chain:
        assert (src, dst) in edges, f"missing pipeline edge {src} -> {dst}"
