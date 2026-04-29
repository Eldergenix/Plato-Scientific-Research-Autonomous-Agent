from langgraph.graph import START, StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .parameters import GraphState
from .reader import preprocess_node
from .idea import idea_maker, idea_hater
from .methods import methods_fast
from .literature import novelty_decider, semantic_scholar, literature_summary
from .referee import referee
from .routers import router, task_router, literature_router


def build_lg_graph(mermaid_diagram=False):
    """
    This function builds the graph

    Args:
       mermaid_diagram: whether to create a diagram with the graph
    """

    # Define the graph
    builder = StateGraph(GraphState)

    # Define nodes: these do the work
    builder.add_node("preprocess_node",    preprocess_node)
    builder.add_node("maker",              idea_maker)
    builder.add_node("hater",              idea_hater)
    builder.add_node("methods",            methods_fast)
    builder.add_node("novelty",            novelty_decider)
    builder.add_node("semantic_scholar",   semantic_scholar)
    builder.add_node("literature_summary", literature_summary)
    builder.add_node("referee",            referee)
    
    # Define edges: these determine how the control flow moves
    builder.add_edge(START,                          "preprocess_node")
    builder.add_conditional_edges("preprocess_node", task_router)
    builder.add_conditional_edges("maker",           router)
    builder.add_edge("hater",                        "maker")
    builder.add_edge("methods",                      END)
    builder.add_conditional_edges("novelty",         literature_router)
    builder.add_edge("semantic_scholar",             "novelty")
    builder.add_edge("literature_summary",           END)
    builder.add_edge("referee",                      END)
    

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
