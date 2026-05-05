"""Slide outline node.

Runs once after the revision loop terminates. Reads the final composed
paper sections from ``state['paper']`` and asks the LLM to convert them
into a presentation-grade Markdown slide outline. The result is written
to ``state['paper']['slide_outline']`` and persisted to
``<Paper_folder>/slide_outline.md`` via the scoped writer so the
file-scope contract from R11 stays intact.
"""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from .parameters import GraphState
from .prompts import slide_outline_prompt
from .scopes import SLIDE_OUTLINE_SCOPE
from .tools import LLM_call
from ..io import ScopedWriter


def slide_outline_node(state: GraphState, config: RunnableConfig):
    """Produce a Markdown slide outline from the finished paper.

    Mirrors the partial-state-update contract used by every other paper
    node (see :func:`plato.paper_agents.paper_node.section_node`):
    return only the keys that changed. ``paper`` is merged in shallow so
    every previously written section is preserved.
    """
    print("Building slide outline".ljust(33, "."), end="", flush=True)

    prompt = slide_outline_prompt(state)
    state, result = LLM_call(prompt, state, node_name="slide_outline")

    # No fenced LaTeX block to extract — the prompt asks for raw
    # Markdown, so we just trim and use the result as-is.
    outline = (result or "").strip()

    # Persist to disk through ScopedWriter so the per-node FileScope
    # contract is enforced (R11 adoption).
    paper_folder = (state.get("files") or {}).get("Paper_folder")
    if paper_folder and outline:
        writer = ScopedWriter(paper_folder, SLIDE_OUTLINE_SCOPE)
        writer.write("slide_outline.md", outline)

    print(f" |  done {state['tokens']['ti']} {state['tokens']['to']}")

    return {
        "paper": {**state["paper"], "slide_outline": outline},
        "tokens": state["tokens"],
    }


__all__ = ["slide_outline_node"]
