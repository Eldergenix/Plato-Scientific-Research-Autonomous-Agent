"""Phase 2 — graph-level smoke test for the R3+R5 wiring.

The full paper graph should compile cleanly with the new
``citation_validator_node``, ``claim_evidence_fanout``, ``claim_extractor``,
and ``evidence_matrix_node`` registered, and the citation router should
keep both branches (citations on/off) routable.
"""
from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver

from plato.paper_agents.agents_graph import build_graph


def test_graph_compiles_with_validation_and_evidence_nodes():
    graph = build_graph(checkpointer=MemorySaver())
    nodes = set(graph.get_graph().nodes)
    expected_new = {
        "citation_validator_node",
        "claim_evidence_fanout",
        "claim_extractor",
        "evidence_matrix_node",
    }
    assert expected_new.issubset(nodes), f"missing nodes: {expected_new - nodes}"


def test_graph_node_count_at_least_18():
    graph = build_graph(checkpointer=MemorySaver())
    # Spec floor: 17 work nodes + START + END before this change.
    # After wiring: +4 work nodes -> 23 nodes (including START/END markers).
    assert len(graph.get_graph().nodes) >= 18


def test_existing_review_pipeline_still_present():
    """Reviewer panel + critique aggregator must remain wired in place."""
    graph = build_graph(checkpointer=MemorySaver())
    nodes = set(graph.get_graph().nodes)
    review_nodes = {
        "reviewer_panel_fanout",
        "methodology_reviewer",
        "statistics_reviewer",
        "novelty_reviewer",
        "writing_reviewer",
        "critique_aggregator",
        "redraft_node",
    }
    assert review_nodes.issubset(nodes)


def test_citation_router_skip_branch_routes_to_claim_evidence_fanout():
    """When add_citations is False the router should still feed the matrix."""
    from plato.paper_agents.routers import citation_router

    state = {"paper": {"add_citations": False}}
    assert citation_router(state) == "claim_evidence_fanout"


def test_citation_router_on_branch_routes_to_citations_node():
    from plato.paper_agents.routers import citation_router

    state = {"paper": {"add_citations": True}}
    assert citation_router(state) == "citations_node"


def test_citations_node_predecessor_to_validator():
    """Confirm citations_node -> citation_validator_node edge exists."""
    graph = build_graph(checkpointer=MemorySaver())
    edges = graph.get_graph().edges
    edge_pairs = {(e.source, e.target) for e in edges}
    assert ("citations_node", "citation_validator_node") in edge_pairs
    assert ("citation_validator_node", "claim_evidence_fanout") in edge_pairs
    assert ("claim_evidence_fanout", "claim_extractor") in edge_pairs
    assert ("claim_extractor", "evidence_matrix_node") in edge_pairs
    assert ("evidence_matrix_node", "reviewer_panel_fanout") in edge_pairs
