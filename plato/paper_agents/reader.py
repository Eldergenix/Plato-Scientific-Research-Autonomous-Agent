import os
import time
import hashlib
import shutil
from pathlib import Path
from typing import Any, cast
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from .parameters import GraphState
from .latex_presets import journal_dict
from ..config import (
    INPUT_FILES,
    IDEA_FILE,
    METHOD_FILE,
    RESULTS_FILE,
    PAPER_FOLDER,
    PLOTS_FOLDER,
    LaTeX_DIR,
)


def preprocess_node(state: GraphState, config: RunnableConfig):
    """
    This agent reads the input files, clean up files, and set the name of some files
    """
    files = cast(dict[str, Any], state["files"])

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

    # set the tokens usage
    state["tokens"] = {"ti": 0, "to": 0, "i": 0, "o": 0}

    # set time
    state["time"] = {"start": time.time()}

    # set value of the parameters
    state["params"] = {"num_keywords": 5}

    # get Paper folder
    files["Paper_folder"] = f"{files['Folder']}/{PAPER_FOLDER}"
    os.makedirs(files["Paper_folder"], exist_ok=True)

    # set the name of the other files
    files.update(
        {
            "Idea": f"{IDEA_FILE}",  # name of file containing idea description
            "Methods": f"{METHOD_FILE}",  # name of file with methods description
            "Results": f"{RESULTS_FILE}",  # name of file with results description
            "Plots": f"{PLOTS_FOLDER}",  # name of folder containing plots
            "Paper_v1": "paper_v1_preliminary.tex",
            "Paper_v2": "paper_v2_no_citations.tex",
            "Paper_v3": "paper_v3_citations.tex",
            "Paper_v4": "paper_v4_final.tex",
            "Error": f"{files['Paper_folder']}/Error.txt",
            "LaTeX_log": f"{files['Paper_folder']}/LaTeX_compilation.log",
            "LaTeX_err": f"{files['Paper_folder']}/LaTeX_err.log",
            "Temp": f"{files['Paper_folder']}/temp",
            "LLM_calls": f"{files['Paper_folder']}/LLM_calls.txt",
            "AAS_keywords": str(LaTeX_DIR / "AAS_keywords.txt"),
        }
    )

    # set the Latex class
    state["latex"] = {"section_to_fix": ""}

    # read input files
    idea: dict[str, str | None] = {}
    for key in ["Idea", "Methods", "Results"]:
        path = Path(f"{files['Folder']}/{INPUT_FILES}/{files[key]}")
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                idea[key] = fh.read()
        else:
            idea[key] = None

    # remove these files if they already exist
    for file_key in ["Paper_v1", "Paper_v2", "Paper_v3", "Paper_v4"]:
        f_in = f"{files['Paper_folder']}/{files[file_key]}"
        if os.path.exists(f_in):
            os.remove(f"{f_in}")

        # get the root of the paper file (if paper.tex, root=paper)
        root = Path(files[file_key]).stem

        for f_in in [
            f"{root}.pdf",
            f"{root}.aux",
            f"{root}.log",
            f"{root}.out",
            f"{root}.bbl",
            f"{root}.blg",
            f"{root}.synctex.gz",
            f"{root}.synctex(busy)",
            "bibliography.bib",
            "bibliography_temp.bib",
        ]:
            fin = f"{files['Paper_folder']}/{f_in}"
            if os.path.exists(fin):
                os.remove(f"{fin}")

    # remove these files if they already exist
    for f_in in [
        files["Error"],
        files["LLM_calls"],
        files["LaTeX_log"],
        files["LaTeX_err"],
    ]:
        if os.path.exists(f_in):
            os.remove(f"{f_in}")

    # create a folder to save LaTeX progress
    os.makedirs(files["Temp"], exist_ok=True)

    # create symbolic link to input_files in Temp to compile files in Temp
    link_src = Path(f"{files['Folder']}/{INPUT_FILES}").resolve()
    link_dst = Path(f"{files['Paper_folder']}/{INPUT_FILES}").resolve()
    # Only create symlink if it doesn't already exist
    if not link_dst.exists() and not link_dst.is_symlink():
        link_dst.symlink_to(link_src, target_is_directory=True)

    # copy LaTeX files to project folder
    journal_files = journal_dict[state["paper"]["journal"]].files

    # copy LaTeX journal files to project folder
    for journal_file in journal_files:
        f_in = f"{files['Paper_folder']}/{journal_file}"
        if not (os.path.exists(f_in)):
            shutil.copy(LaTeX_DIR / journal_file, files["Paper_folder"])
        f_in = f"{files['Temp']}/{journal_file}"
        if not (os.path.exists(f_in)):
            shutil.copy(LaTeX_DIR / journal_file, files["Temp"])

    # deal with repeated plots
    plots_dir = Path(f"{files['Folder']}/{INPUT_FILES}/{files['Plots']}")
    repeated_dir = Path(f"{plots_dir}_repeated")

    # Walk through all plot files
    hash_dict: dict[str, Path] = {}  # create hash dictionary
    for file in plots_dir.iterdir():
        if file.is_file():
            # Compute hash
            with open(file, "rb") as fh:
                file_hash = hashlib.sha256(fh.read()).hexdigest()

            if file_hash in hash_dict:
                repeated_dir.mkdir(exist_ok=True)
                # This is a repeated file: copy it to repeated_plots
                print(f"Repeated: {file.name} (same as {hash_dict[file_hash].name})")
                shutil.move(file, repeated_dir / file.name)
            else:
                hash_dict[file_hash] = file

    # get the number of plots in the project
    folder_path = Path(f"{files['Folder']}/{INPUT_FILES}/{files['Plots']}")
    plot_files = [
        file
        for file in folder_path.iterdir()
        if file.is_file() and file.name != ".DS_Store"
    ]
    state["files"]["num_plots"] = len(plot_files)

    return {
        **state,
        "llm": state["llm"],
        "tokens": state["tokens"],
        "params": state["params"],
        "files": state["files"],
        "latex": state["latex"],
        "idea": idea,
        "paper": {**state["paper"], "summary": ""},
        "time": state["time"],
    }
