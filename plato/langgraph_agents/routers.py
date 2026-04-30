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
        return "__end__"

def literature_router(state: GraphState) -> str:
    """
    This simple function determines which agent should go after calling the novelty_decider one
    """

    return state['literature']['next_agent']
