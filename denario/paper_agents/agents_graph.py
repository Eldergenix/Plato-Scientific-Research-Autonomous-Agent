from langgraph.graph import START, StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .parameters import GraphState
from .paper_node import abstract_node, citations_node, conclusions_node, introduction_node, keywords_node, methods_node, plots_node, refine_results, results_node
from .reader import preprocess_node
from .routers import citation_router


def build_graph(mermaid_diagram=False):
    """
    This function builds the graph
    """

    # Define the graph
    builder = StateGraph(GraphState)

    # Define nodes: these do the work
    builder.add_node("preprocess_node",   preprocess_node)
    builder.add_node("abstract_node",     abstract_node)
    builder.add_node("introduction_node", introduction_node)
    builder.add_node("methods_node",      methods_node)
    builder.add_node("results_node",      results_node)
    builder.add_node("conclusions_node",  conclusions_node)
    builder.add_node("plots_node",        plots_node)
    builder.add_node("refine_results",    refine_results)
    builder.add_node("keywords_node",     keywords_node)
    builder.add_node("citations_node",    citations_node)
    
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
    builder.add_conditional_edges("refine_results", citation_router)
    builder.add_edge("citations_node",              END)

    memory = MemorySaver()
    graph  = builder.compile(checkpointer=memory)

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
