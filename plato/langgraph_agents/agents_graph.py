from langgraph.graph import START, StateGraph, END

from .parameters import GraphState
from .reader import preprocess_node
from .idea import idea_maker, idea_hater
from .methods import methods_fast
from .literature import novelty_decider, semantic_scholar, literature_summary
from .referee import referee
from .clarifier import research_question_clarifier
from .counter_evidence import counter_evidence_search
from .gap_detector import gap_detector
from .routers import router, task_router, literature_router, clarifier_router
from .scopes import (
    CLARIFIER_SCOPE,
    IDEA_HATER_SCOPE,
    IDEA_SCOPE,
    LITERATURE_SUMMARY_SCOPE,
    METHODS_FAST_SCOPE,
    NOVELTY_DECIDER_SCOPE,
    REFEREE_SCOPE,
    SEMANTIC_SCHOLAR_SCOPE,
)
from ..io import scoped_node
from ..state import make_checkpointer


def build_lg_graph(mermaid_diagram=False, checkpointer=None):
    """
    This function builds the graph

    Args:
       mermaid_diagram: whether to create a diagram with the graph
       checkpointer:    LangGraph checkpointer. If None, a SQLite-backed
                        checkpointer (durable across restarts) is created via
                        ``plato.state.make_checkpointer``. Pass an explicit
                        ``MemorySaver()`` for tests that should not persist.
    """

    # Define the graph
    builder = StateGraph(GraphState)

    # Define nodes: these do the work.
    #
    # R11 file-scope adoption: every node that writes a file is wrapped
    # in ``scoped_node(fn, scope)`` so its writes go through a
    # ScopedWriter rooted at state["files"]["Folder"]. Out-of-scope
    # writes raise ``ScopeError`` at runtime — defence in depth against
    # an LLM-generated path traversing into another tenant's project.
    # ``preprocess_node`` only edits state (no file writes), so we leave
    # it un-scoped to avoid wrapping cost. ``counter_evidence_search``
    # and ``gap_detector`` are pure state transformations today; if
    # they grow file outputs, wrap them then.
    builder.add_node("preprocess_node",              preprocess_node)
    builder.add_node(
        "research_question_clarifier",
        scoped_node(research_question_clarifier, CLARIFIER_SCOPE),
    )
    builder.add_node("maker",                        scoped_node(idea_maker, IDEA_SCOPE))
    builder.add_node("hater",                        scoped_node(idea_hater, IDEA_HATER_SCOPE))
    builder.add_node("methods",                      scoped_node(methods_fast, METHODS_FAST_SCOPE))
    builder.add_node("novelty",                      scoped_node(novelty_decider, NOVELTY_DECIDER_SCOPE))
    builder.add_node("semantic_scholar",             scoped_node(semantic_scholar, SEMANTIC_SCHOLAR_SCOPE))
    builder.add_node(
        "literature_summary",
        scoped_node(literature_summary, LITERATURE_SUMMARY_SCOPE),
    )
    builder.add_node("counter_evidence_search",      counter_evidence_search)
    builder.add_node("gap_detector",                 gap_detector)
    builder.add_node("referee",                      scoped_node(referee, REFEREE_SCOPE))

    # Define edges: these determine how the control flow moves
    builder.add_edge(START,                          "preprocess_node")
    builder.add_conditional_edges("preprocess_node", task_router)
    # Workflow #1: gate the maker/hater debate behind the clarifier.
    builder.add_conditional_edges(
        "research_question_clarifier",
        clarifier_router,
        {"maker": "maker", END: END},
    )
    builder.add_conditional_edges("maker",           router)
    builder.add_edge("hater",                        "maker")
    builder.add_edge("methods",                      END)
    builder.add_conditional_edges("novelty",         literature_router)
    builder.add_edge("semantic_scholar",             "novelty")
    # Workflow #11 + #12: after the literature summary, hunt for
    # counter-evidence and then run gap analysis before terminating.
    builder.add_edge("literature_summary",           "counter_evidence_search")
    builder.add_edge("counter_evidence_search",      "gap_detector")
    builder.add_edge("gap_detector",                 END)
    builder.add_edge("referee",                      END)
    

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
