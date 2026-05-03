from langchain_core.runnables import RunnableConfig

from ..paper_agents.tools import extract_latex_block, LLM_call_stream, clean_section
from .prompts import idea_maker_prompt, idea_hater_prompt
from .parameters import GraphState


def idea_maker(state: GraphState, config: RunnableConfig):

    print(f"Maker (iteration {state['idea']['iteration']+1})")

    PROMPT = idea_maker_prompt(state)
    state, result = LLM_call_stream(PROMPT, state, node_name="idea_maker")
    text = extract_latex_block(state, result, "IDEA")

    # remove LLM added lines
    text = clean_section(text, "IDEA")

    # Build the new ``idea`` dict immutably. Mutating ``state['idea']``
    # in-place AND returning it as the partial update breaks the
    # checkpointer's snapshot semantics — LangGraph stores the previous
    # snapshot by reference, so an in-place mutation rewrites history
    # under SqliteSaver/PostgresSaver. The fix is to return a fresh dict.
    new_iter = state['idea']['iteration'] + 1
    new_idea = {
        **state['idea'],
        'idea': text,
        'previous_ideas': (
            f"{state['idea']['previous_ideas']}\n\n"
            f"Iteration {state['idea']['iteration']}:\n"
            f"Idea: {text}\n"
        ),
        'iteration': new_iter,
    }

    if new_iter == state['idea']['total_iterations']:
        with open(state['files']['idea'], 'w') as f:
            f.write(text)

        print(f"done {state['tokens']['ti']} {state['tokens']['to']}")

    return {"idea": new_idea}


def idea_hater(state: GraphState, config: RunnableConfig):

    print(f"Hater (iteration {state['idea']['iteration']})")

    PROMPT = idea_hater_prompt(state)
    state, result = LLM_call_stream(PROMPT, state, node_name="idea_hater")
    text = extract_latex_block(state, result, "CRITIC")

    # remove LLM added lines
    text = clean_section(text, "CRITIC")

    # Same immutable-update pattern as idea_maker — never mutate state
    # in-place when returning the value as the LangGraph state update.
    new_idea = {**state['idea'], 'criticism': text}

    return {"idea": new_idea}


