import os
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from .parameters import GraphState
from ..config import (
    INPUT_FILES,
    IDEA_FILE,
    METHOD_FILE,
    LITERATURE_FILE,
    REFEREE_FILE,
    PAPER_FOLDER,
)


def preprocess_node(state: GraphState, config: RunnableConfig):
    """
    This agent reads the input files, clean up files, and set the name of some files
    """
    files = cast(dict[str, Any], state["files"])

    # set the tokens usage
    state["tokens"] = {"ti": 0, "to": 0, "i": 0, "o": 0}

    #########################################
    # set the LLM
    if "gemini" in state["llm"]["model"]:
        state["llm"]["llm"] = ChatGoogleGenerativeAI(
            model=state["llm"]["model"],
            temperature=state["llm"]["temperature"],
            google_api_key=state["keys"].GEMINI,
        )

    elif any(key in state["llm"]["model"] for key in ["gpt", "o3"]):
        state["llm"]["llm"] = cast(Any, ChatOpenAI)(
            model=state["llm"]["model"],
            temperature=state["llm"]["temperature"],
            openai_api_key=state["keys"].OPENAI,
        )

    elif any(
        key in state["llm"]["model"]
        for key in ["deepseek-ai/", "Qwen/", "meta-llama/", "moonshotai/", "nvidia/"]
    ):
        state["llm"]["llm"] = cast(Any, ChatOpenAI)(
            model=state["llm"]["model"],
            temperature=state["llm"]["temperature"],
            openai_api_key=state["keys"].HUGGINGFACE,
            openai_api_base="https://router.huggingface.co/v1",
        )

    elif "claude" in state["llm"]["model"] or "anthropic" in state["llm"]["model"]:
        state["llm"]["llm"] = cast(Any, ChatAnthropic)(
            model=state["llm"]["model"],
            temperature=state["llm"]["temperature"],
            anthropic_api_key=state["keys"].ANTHROPIC,
        )
    #########################################

    #########################################
    # read data description
    try:
        with open(state["files"]["data_description"], "r", encoding="utf-8") as f:
            description = f.read()
    except FileNotFoundError:
        raise Exception("Data description file not found!")
    except Exception:
        raise Exception("Error reading the data description file!")
    #########################################

    #########################################
    # read idea description
    if state["task"] in ["methods_generation", "literature"]:
        try:
            with open(state["files"]["idea"], "r", encoding="utf-8") as fh:
                idea_text = fh.read()
        except FileNotFoundError:
            raise Exception("Idea file not found!")
        except Exception:
            raise Exception("Error reading the idea file!")
    else:
        idea_text = ""
    #########################################

    #########################################
    # set the name of the common files
    if state["task"] == "idea_generation":
        files["module_folder"] = "idea_generation_output"
        files["f_stream"] = f"{files['Folder']}/{files['module_folder']}/idea.log"
    elif state["task"] == "methods_generation":
        files["module_folder"] = "methods_generation_output"
        files["f_stream"] = f"{files['Folder']}/{files['module_folder']}/methods.log"
    elif state["task"] == "literature":
        files["module_folder"] = "literature_output"
        files["f_stream"] = f"{files['Folder']}/{files['module_folder']}/literature.log"
    elif state["task"] == "referee":
        files["module_folder"] = "referee_output"
        files["f_stream"] = f"{files['Folder']}/{files['module_folder']}/referee.log"
        files["paper_images"] = f"{files['Folder']}/{files['module_folder']}"

    files.update(
        {
            "Temp": f"{files['Folder']}/{files['module_folder']}",
            "LLM_calls": f"{files['Folder']}/{files['module_folder']}/LLM_calls.txt",
            "Error": f"{files['Folder']}/{files['module_folder']}/Error.txt",
        }
    )
    #########################################
    # set particulars for different tasks
    idea_state: Any
    if state["task"] == "idea_generation":
        idea_state = {
            **state["idea"],
            "iteration": 0,
            "previous_ideas": "",
            "idea": "",
            "criticism": "",
        }
        files.update(
            {
                "idea": f"{files['Folder']}/{INPUT_FILES}/{IDEA_FILE}",
                "idea_log": f"{files['Folder']}/{files['module_folder']}/idea.log",
            }
        )
    elif state["task"] == "methods_generation":
        files["methods"] = f"{files['Folder']}/{INPUT_FILES}/{METHOD_FILE}"
        idea_state = {**state["idea"], "idea": idea_text}
    elif state["task"] == "literature":
        state["literature"] = {
            **state["literature"],
            "iteration": 0,
            "query": "",
            "decision": "",
            "papers": "",
            "next_agent": "",
            "messages": "",
            "num_papers": 0,
        }
        files.update(
            {
                "literature": f"{files['Folder']}/{INPUT_FILES}/{LITERATURE_FILE}",
                "literature_log": f"{files['Folder']}/{files['module_folder']}/literature.log",
                "papers": f"{files['Folder']}/{files['module_folder']}/papers_processed.log",
            }
        )
        idea_state = {**state["idea"], "idea": idea_text}

    elif state["task"] == "referee":
        state["referee"] = {
            **state["referee"],
            "paper_version": 2,
            "report": "",
            "images": [],
        }
        files.update(
            {
                "Paper_folder": f"{files['Folder']}/{PAPER_FOLDER}",
                "referee_report": f"{files['Folder']}/{INPUT_FILES}/{REFEREE_FILE}",
                "referee_log": f"{files['Folder']}/{files['module_folder']}/referee.log",
            }
        )
        idea_state = state["idea"]
    else:
        idea_state = state["idea"]

    # create project folder, input files, and temp files
    os.makedirs(files["Folder"], exist_ok=True)
    os.makedirs(files["Temp"], exist_ok=True)
    os.makedirs(f"{files['Folder']}/{INPUT_FILES}", exist_ok=True)

    #########################################
    # clean existing files
    for file_key in ["LLM_calls", "Error"]:
        file_path = files[file_key]
        if os.path.exists(file_path):
            os.remove(file_path)

    # remove idea.md and idea.log if they exist
    if state["task"] == "idea_generation":
        for file_key in ["idea", "idea_log"]:
            file_path = files[file_key]
            if os.path.exists(file_path):
                os.remove(file_path)

    # remove methods.md if it exists
    if state["task"] == "methods_generation":
        for file_key in ["methods"]:
            file_path = files[file_key]
            if os.path.exists(file_path):
                os.remove(file_path)

    # remove literature.md if it exists
    if state["task"] == "literature":
        for file_key in ["literature", "literature_log", "papers"]:
            file_path = files[file_key]
            if os.path.exists(file_path):
                os.remove(file_path)

    # remove referee.md if it exists
    if state["task"] == "referee":
        for file_key in ["referee_report", "referee_log"]:
            file_path = files[file_key]
            if os.path.exists(file_path):
                os.remove(file_path)

        # Return only the keys that this node actually changed.
        # Returning ``{**state, ...}`` would re-emit every existing
        # key as part of the state update, causing reducer-equipped
        # fields (e.g. ``messages`` with ``add_messages``) to
        # double-apply — the message list grew unboundedly across
        # checkpoints.
        return {
            "files": state["files"],
            "llm": state["llm"],
            "tokens": state["tokens"],
            "data_description": description,
            "referee": state["referee"],
        }
    #########################################

    update = {
        "files": state["files"],
        "llm": state["llm"],
        "tokens": state["tokens"],
        "data_description": description,
        "idea": idea_state,
    }
    if state["task"] == "literature":
        update["literature"] = state["literature"]
    return update
