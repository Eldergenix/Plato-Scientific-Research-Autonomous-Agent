from langchain_core.runnables import RunnableConfig

from ..paper_agents.tools import extract_latex_block, LLM_call_stream, clean_section
from .prompts import methods_fast_prompt
from .parameters import GraphState


def methods_fast(state: GraphState, config: RunnableConfig):

    print('Generating methods...', end="", flush=True)

    PROMPT = methods_fast_prompt(state)
    state, result = LLM_call_stream(PROMPT, state)
    text = extract_latex_block(state, result, "METHODS")

    # remove LLM added lines
    text = clean_section(text, "METHODS")

    with open(state['files']['methods'], 'w') as f:
        f.write(text)

    print(f"done {state['tokens']['ti']} {state['tokens']['to']}")
