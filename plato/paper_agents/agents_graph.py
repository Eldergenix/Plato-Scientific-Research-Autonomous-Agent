from langgraph.graph import START, StateGraph, END

from .parameters import GraphState
from .paper_node import abstract_node, citations_node, conclusions_node, introduction_node, keywords_node, methods_node, plots_node, refine_results, results_node
from .reader import preprocess_node
from .routers import citation_router, revision_router
from .reviewer_panel import (
    methodology_reviewer,
    novelty_reviewer,
    statistics_reviewer,
    writing_reviewer,
)
from .critique_aggregator import critique_aggregator
from .redraft_node import redraft_node
from ..state import make_checkpointer


def _reviewer_panel_fanout(state: GraphState):
    """No-op fan-out hub: parallel edges to each reviewer originate here.

    Initialises ``revision_state`` on first entry so downstream routing has
    sensible defaults even if the caller did not preset it.
    """
    revision_state = dict(state.get("revision_state") or {})
    revision_state.setdefault("iteration", 0)
    revision_state.setdefault("max_iterations", 2)
    return {
        "revision_state": revision_state,
        # Always start a fresh critique slate per pass.
        "critiques": {},
    }


def build_graph(mermaid_diagram=False, checkpointer=None):
    """
    Build the paper-writing graph.

    Args:
        mermaid_diagram: whether to render the graph as a mermaid PNG.
        checkpointer:    LangGraph checkpointer. If None, a SQLite-backed
                         checkpointer is created via
                         ``plato.state.make_checkpointer``. Pass an explicit
                         ``MemorySaver()`` for tests.
    """

    # Define the graph
    builder = StateGraph(GraphState)

    # Define nodes: these do the work
    builder.add_node("preprocess_node",       preprocess_node)
    builder.add_node("abstract_node",         abstract_node)
    builder.add_node("introduction_node",     introduction_node)
    builder.add_node("methods_node",          methods_node)
    builder.add_node("results_node",          results_node)
    builder.add_node("conclusions_node",      conclusions_node)
    builder.add_node("plots_node",            plots_node)
    builder.add_node("refine_results",        refine_results)
    builder.add_node("keywords_node",         keywords_node)
    builder.add_node("citations_node",        citations_node)

    # Phase 3 — R6: multi-reviewer panel + revision loop
    builder.add_node("reviewer_panel_fanout", _reviewer_panel_fanout)
    builder.add_node("methodology_reviewer",  methodology_reviewer)
    builder.add_node("statistics_reviewer",   statistics_reviewer)
    builder.add_node("novelty_reviewer",      novelty_reviewer)
    builder.add_node("writing_reviewer",      writing_reviewer)
    builder.add_node("critique_aggregator",   critique_aggregator)
    builder.add_node("redraft_node",          redraft_node)

    # Define edges: these determine how the control flow moves
    builder.add_edge(START,                         "preprocess_node")
    builder.add_edge("preprocess_node",             "keywords_node")
    builder.add_edge("keywords_node",               "abstract_node")
    builder.add_edge("abstract_node",               "introduction_node")
    builder.add_edge("introduction_node",           "methods_node")
    builder.add_edge("methods_node",                "results_node")
    builder.add_edge("results_node",                "conclusions_node")
    builder.add_edge("conclusions_node",            "plots_node")
    builder.add_edge("plots_node",                  "refine_results")
    # Citations stage: either run citations_node, or skip straight to review.
    builder.add_conditional_edges(
        "refine_results",
        citation_router,
        {
            "citations_node": "citations_node",
            "reviewer_panel_fanout": "reviewer_panel_fanout",
        },
    )
    # After citations, hand off to the reviewer panel fan-out.
    builder.add_edge("citations_node",              "reviewer_panel_fanout")

    # Parallel fan-out: four reviewers run in parallel from the fan-out hub.
    builder.add_edge("reviewer_panel_fanout",       "methodology_reviewer")
    builder.add_edge("reviewer_panel_fanout",       "statistics_reviewer")
    builder.add_edge("reviewer_panel_fanout",       "novelty_reviewer")
    builder.add_edge("reviewer_panel_fanout",       "writing_reviewer")

    # Fan-in: every reviewer feeds the aggregator. LangGraph waits for all
    # in-edges to complete before running the aggregator node.
    builder.add_edge("methodology_reviewer",        "critique_aggregator")
    builder.add_edge("statistics_reviewer",         "critique_aggregator")
    builder.add_edge("novelty_reviewer",            "critique_aggregator")
    builder.add_edge("writing_reviewer",            "critique_aggregator")

    # Conditional redraft loop based on severity + iteration cap.
    builder.add_conditional_edges(
        "critique_aggregator",
        revision_router,
        {
            "redraft_node": "redraft_node",
            END: END,
        },
    )
    # After a redraft, re-enter the reviewer panel for another pass.
    builder.add_edge("redraft_node",                "reviewer_panel_fanout")

    if checkpointer is None:
        checkpointer = make_checkpointer()
    graph = builder.compile(checkpointer=checkpointer)

    # # generate an scheme with the graph
    if mermaid_diagram:
        try:
            import requests
            original_post = requests.post

            def patched_post(*args, **kwargs):
                kwargs.setdefault("timeout", 30)  # Increase timeout to 30 seconds
                return original_post(*args, **kwargs)

            requests.post = patched_post
            graph_image = graph.get_graph(xray=True).draw_mermaid_png()
            with open("graph_diagram.png", "wb") as f:
                f.write(graph_image)
            print("✅ Graph diagram saved to graph_diagram.png")
        except Exception as e:
            print(f"⚠️ Failed to generate or save graph diagram: {e}")


    return graph
