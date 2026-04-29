from langchain_core.runnables import RunnableConfig

from ..paper_agents.tools import extract_latex_block, LLM_call_stream, clean_section
from .prompts import reviewer_fast_prompt
from .parameters import GraphState
from .pdf_reader import pdf_to_images


def referee(state: GraphState, config: RunnableConfig):

    print('Reviewing the paper...', end="", flush=True)

    if state['referee']['paper_version']==2:
        paper_name = "paper_v2_no_citations.pdf"
    elif state['referee']['paper_version']==4:
        paper_name = "paper_v4_final.pdf"
    pdf_path = f"{state['files']['Paper_folder']}/{paper_name}"
    out_dir = f"{state['files']['paper_images']}"

    # get the base64 representation of the images
    state['referee']['images'] = pdf_to_images(pdf_path, out_dir)

    # call the LLM
    PROMPT = reviewer_fast_prompt(state)
    state, result = LLM_call_stream(PROMPT, state)
    text = extract_latex_block(state, result, "REVIEW")

    # remove LLM added lines
    text = clean_section(text, "REVIEW")

    with open(state['files']['referee_report'], 'w') as f:
        f.write(text)

    print(f"done {state['tokens']['ti']} {state['tokens']['to']}")
