from langgraph.graph import END

from .parameters import GraphState


# idea - methods router
def task_router (state: GraphState) -> str:

    if state['task']=='idea_generation':
        return 'research_question_clarifier'
    elif state['task']=='methods_generation':
        return 'methods'
    elif state['task']=='literature':
        return 'novelty'
    elif state['task']=='referee':
        return 'referee'
    else:
        raise Exception('Wrong task choosen!')


# Workflow gap #1: clarifier router. If the clarifier produced questions
# the user must answer, suspend the run by routing to END so the caller
# can collect answers; otherwise proceed to the maker/hater debate.
def clarifier_router(state: GraphState) -> str:
    if state.get('needs_clarification'):
        return END
    return 'maker'
    
# Idea maker - hater router
def router(state: GraphState) -> str:

    if state['idea']['iteration']<state['idea']['total_iterations']:
        return "hater"
    else:
        # Use the canonical END sentinel rather than the literal
        # ``"__end__"`` string. Today they are equal, but a future
        # LangGraph release might introduce strict node-set validation
        # on conditional edges, in which case the bare string would
        # raise GraphValueError.
        return END


# Whitelist of valid literature_router targets. Keeping this in sync
# with novelty_decider's writes guards against an LLM-malformed
# Decision routing the graph into a non-existent node (which would
# raise GraphValueError at runtime).
_VALID_LITERATURE_TARGETS = {"literature_summary", "semantic_scholar"}


def literature_router(state: GraphState) -> str:
    """Pick the next literature node based on novelty_decider's write."""

    target = state['literature']['next_agent']
    if target not in _VALID_LITERATURE_TARGETS:
        raise ValueError(
            f"literature_router: unknown next_agent {target!r} "
            f"(valid: {sorted(_VALID_LITERATURE_TARGETS)})"
        )
    return target
