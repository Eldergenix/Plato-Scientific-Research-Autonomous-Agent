from langchain_core.runnables import RunnableConfig

from ..paper_agents.tools import extract_latex_block, LLM_call_stream, clean_section
from .prompts import methods_fast_prompt
from .parameters import GraphState


def methods_fast(state: GraphState, config: RunnableConfig):
    """Generate the methods section in fast (single-shot) mode.

    Returns the token / message deltas so LangGraph's reducer captures
    them in the next checkpoint. Previously this returned ``None``, which
    meant resume-from-checkpoint had no record of the LLM call — the
    methods file was on disk but the in-graph state had no token usage,
    no message history, and would re-run the LLM on resume.
    """

    print('Generating methods...', end="", flush=True)

    PROMPT = methods_fast_prompt(state)
    state, result = LLM_call_stream(PROMPT, state, node_name="methods_fast")
    text = extract_latex_block(state, result, "METHODS")

    # remove LLM added lines
    text = clean_section(text, "METHODS")

    with open(state['files']['methods'], 'w') as f:
        f.write(text)

    print(f"done {state['tokens']['ti']} {state['tokens']['to']}")
    return {
        "messages": state.get("messages", []),
        "tokens": state["tokens"],
    }
