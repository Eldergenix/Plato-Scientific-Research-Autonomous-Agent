from .parameters import GraphState


# idea - methods router
def task_router (state: GraphState) -> str:

    if state['task']=='idea_generation':
        return 'maker'
    elif state['task']=='methods_generation':
        return 'methods'
    elif state['task']=='literature':
        return 'novelty'
    elif state['task']=='referee':
        return 'referee'
    else:
        raise Exception('Wrong task choosen!')
    
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
