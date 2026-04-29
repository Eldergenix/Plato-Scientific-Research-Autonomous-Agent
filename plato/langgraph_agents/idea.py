from langchain_core.runnables import RunnableConfig

from ..paper_agents.tools import extract_latex_block, LLM_call_stream, clean_section
from .prompts import idea_maker_prompt, idea_hater_prompt
from .parameters import GraphState


def idea_maker(state: GraphState, config: RunnableConfig):

    print(f"Maker (iteration {state['idea']['iteration']+1})")
    
    PROMPT = idea_maker_prompt(state)
    state, result = LLM_call_stream(PROMPT, state)
    text = extract_latex_block(state, result, "IDEA")

    # remove LLM added lines
    text = clean_section(text, "IDEA")

    #with open(state['files']['idea_log'], 'a') as f:
    #    f.write(f"""Iteration {state['idea']['iteration']}:
#{text}
#---------------------------------------------
#""")

    state['idea']['idea'] = text
    state['idea']['previous_ideas'] = f"""
{state['idea']['previous_ideas']}

Iteration {state['idea']['iteration']}:
Idea: {text}
"""
    state['idea']['iteration'] += 1

    if state['idea']['iteration']==state['idea']['total_iterations']:
        with open(state['files']['idea'], 'w') as f:
            f.write(text)

        print(f"done {state['tokens']['ti']} {state['tokens']['to']}")
    
    return {"idea": state['idea']}


def idea_hater(state: GraphState, config: RunnableConfig):

    #print('Hater...', end="", flush=True)
    print(f"Hater (iteration {state['idea']['iteration']})")
    
    PROMPT = idea_hater_prompt(state)
    state, result = LLM_call_stream(PROMPT, state)
    text = extract_latex_block(state, result, "CRITIC")

    # remove LLM added lines
    text = clean_section(text, "CRITIC")
    
    state['idea']['criticism'] = text

    #with open(state['files']['idea_log'], 'a') as f:
    #    f.write(f"""Criticism:
#{text}
#---------------------------------------------
#""")

    return {"idea": state['idea']}


