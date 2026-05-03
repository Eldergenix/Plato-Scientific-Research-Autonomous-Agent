import os
from typing import Any
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from .parameters import GraphState
from ..config import INPUT_FILES, IDEA_FILE, METHOD_FILE, LITERATURE_FILE, REFEREE_FILE, PAPER_FOLDER

def preprocess_node(state: GraphState, config: RunnableConfig):
    """
    This agent reads the input files, clean up files, and set the name of some files
    """

    # set the tokens usage
    state['tokens'] = {'ti': 0, 'to': 0, 'i': 0, 'o': 0}

    #########################################
    # set the LLM
    if 'gemini' in state['llm']['model']:
        state['llm']['llm'] = ChatGoogleGenerativeAI(model=state['llm']['model'],
                                                temperature=state['llm']['temperature'],
                                                google_api_key=state["keys"].GEMINI)

    elif any(key in state['llm']['model'] for key in ['gpt', 'o3']):
        state['llm']['llm'] = ChatOpenAI(model=state['llm']['model'],
                                         temperature=state['llm']['temperature'],
                                         openai_api_key=state["keys"].OPENAI)
                    
    elif 'claude' in state['llm']['model']  or 'anthropic' in state['llm']['model'] :
        state['llm']['llm'] = ChatAnthropic(model=state['llm']['model'],
                                            temperature=state['llm']['temperature'],
                                            anthropic_api_key=state["keys"].ANTHROPIC)
    #########################################

    #########################################
    # read data description
    try:
        with open(state['files']['data_description'], 'r', encoding='utf-8') as f:
            description = f.read()
    except FileNotFoundError:
        raise Exception("Data description file not found!")
    except Exception:
        raise Exception("Error reading the data description file!")
    #########################################

    #########################################
    # read idea description
    if state['task'] in ['methods_generation', 'literature']:
        try:
            with open(state['files']['idea'], 'r', encoding='utf-8') as f:
                idea = f.read()
        except FileNotFoundError:
            raise Exception("Data description file not found!")
        except Exception:
            raise Exception("Error reading the data description file!")
    #########################################

    #########################################
    # set the name of the common files
    if state['task']=='idea_generation':
        state['files']['module_folder'] = 'idea_generation_output'
        state['files']['f_stream'] = f"{state['files']['Folder']}/{state['files']['module_folder']}/idea.log"
    elif state['task']=='methods_generation':
        state['files']['module_folder'] = 'methods_generation_output'
        state['files']['f_stream'] = f"{state['files']['Folder']}/{state['files']['module_folder']}/methods.log"
    elif state['task']=='literature':
        state['files']['module_folder'] = 'literature_output'
        state['files']['f_stream'] = f"{state['files']['Folder']}/{state['files']['module_folder']}/literature.log"
    elif state['task']=='referee':
        state['files']['module_folder'] = 'referee_output'
        state['files']['f_stream'] = f"{state['files']['Folder']}/{state['files']['module_folder']}/referee.log"
        state['files']['paper_images'] = f"{state['files']['Folder']}/{state['files']['module_folder']}"
        
    state['files'] = {**state['files'],
                      "Temp":      f"{state['files']['Folder']}/{state['files']['module_folder']}",
                      "LLM_calls": f"{state['files']['Folder']}/{state['files']['module_folder']}/LLM_calls.txt",
                      "Error":     f"{state['files']['Folder']}/{state['files']['module_folder']}/Error.txt",
    }
    #########################################
    # set particulars for different tasks
    # ``idea_state`` holds the IDEA TypedDict payload we'll thread back
    # into the graph; the ``idea`` variable above is a plain string read
    # off disk (or unset for non-content tasks). Mixing them tripped
    # mypy with "dict[str, object]" vs "str".
    idea_state: dict = {}
    files_any: dict[str, Any] = state['files']  # type: ignore[assignment]
    if state['task']=='idea_generation':
        idea_state = {**state['idea'], 'iteration':0, 'previous_ideas': "",
                'idea': "", 'criticism': ""}
        state['files'] = {**state['files'],
                          "idea":      f"{state['files']['Folder']}/{INPUT_FILES}/{IDEA_FILE}",
                          "idea_log":  f"{state['files']['Folder']}/{state['files']['module_folder']}/idea.log",
        }
    elif state['task']=='methods_generation':
        state['files'] = {**state['files'],
                          "methods": f"{state['files']['Folder']}/{INPUT_FILES}/{METHOD_FILE}",
        }
        idea_state = {**state['idea'], 'idea': idea}
    elif state['task']=='literature':
        state['literature'] = {**state['literature'], 'iteration':0, "query":"", "decision":"",
                               "papers":"", "next_agent":"", "messages":"", "num_papers": 0}
        state['files'] = {**state['files'],
                          "literature": f"{state['files']['Folder']}/{INPUT_FILES}/{LITERATURE_FILE}",
                          "literature_log": f"{state['files']['Folder']}/{state['files']['module_folder']}/literature.log",
                          "papers": f"{state['files']['Folder']}/{state['files']['module_folder']}/papers_processed.log",
        }
        idea_state = {**state['idea'], 'idea': idea}

    elif state['task']=='referee':
        state['referee'] = {**state['referee'], 'paper_version':2, 'report':'', 'images':[]}
        # ``Paper_folder`` is intentionally extra here — the referee
        # task reuses paper_agents output, so the FILES TypedDict in
        # langgraph_agents/parameters.py doesn't declare it. mypy
        # flags "Extra key" until that schema is unified across
        # graphs (TODO: see ADR on cross-graph state).
        state['files'] = {**state['files'],  # type: ignore[typeddict-unknown-key]
                          "Paper_folder": f"{state['files']['Folder']}/{PAPER_FOLDER}",
                          "referee_report": f"{state['files']['Folder']}/{INPUT_FILES}/{REFEREE_FILE}",
                          "referee_log":  f"{state['files']['Folder']}/{state['files']['module_folder']}/referee.log",
        }

    # create project folder, input files, and temp files
    os.makedirs(state['files']['Folder'],                    exist_ok=True)
    os.makedirs(state['files']['Temp'],                      exist_ok=True)
    os.makedirs(f"{state['files']['Folder']}/{INPUT_FILES}", exist_ok=True)

    #########################################
    # clean existing files. ``files_any`` lets us index by a runtime
    # string without the TypedDict literal-key check screaming.
    for fkey in ["LLM_calls", "Error"]:
        file_path = files_any[fkey]
        if os.path.exists(file_path):
            os.remove(file_path)

    # remove idea.md and idea.log if they exist
    if state['task']=='idea_generation':
        for fkey in ["idea", "idea_log"]:
            file_path = files_any[fkey]
            if os.path.exists(file_path):
                os.remove(file_path)

    # remove methods.md if it exists
    if state['task']=='methods_generation':
        for fkey in ["methods"]:
            file_path = files_any[fkey]
            if os.path.exists(file_path):
                os.remove(file_path)

    # remove literature.md if it exists
    if state['task']=="literature":
        for fkey in ['literature', 'literature_log', 'papers']:
            file_path = files_any[fkey]
            if os.path.exists(file_path):
                os.remove(file_path)

    # remove referee.md if it exists
    if state['task']=='referee':
        for fkey in ['referee_report', 'referee_log']:
            file_path = files_any[fkey]
            if os.path.exists(file_path):
                os.remove(file_path)

        # Return only the keys that this node actually changed.
        # Returning ``{**state, ...}`` would re-emit every existing
        # key as part of the state update, causing reducer-equipped
        # fields (e.g. ``messages`` with ``add_messages``) to
        # double-apply — the message list grew unboundedly across
        # checkpoints.
        return {
            "files":            state['files'],
            "llm":              state['llm'],
            "tokens":           state['tokens'],
            "data_description": description,
            "referee":          state['referee'],
        }
    #########################################


    return {
        "files":            state['files'],
        "llm":              state['llm'],
        "tokens":           state['tokens'],
        "data_description": description,
        "idea":             idea_state,
    }

