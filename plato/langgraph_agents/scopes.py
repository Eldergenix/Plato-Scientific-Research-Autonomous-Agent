"""R11 file-scope declarations for the langgraph_agents nodes.

Each scope is tight: only the files the node actually writes are
listed. Reads default to ``["**/*"]`` (full read access within the
project folder) since nodes need to read data_description, idea,
methods, etc. freely.

These scopes are consumed by :func:`plato.io.scoped_node.scoped_node`
when registering nodes in ``agents_graph.py``::

    builder.add_node("idea_maker", scoped_node(idea_maker, IDEA_SCOPE))

The scopes intentionally cover **today's** filesystem layout — a
node's actual write paths under ``state['files']['Folder']``. When a
node grows a new artifact, the matching scope must be widened in
the same PR or the write will raise :class:`plato.io.ScopeError`.
"""
from __future__ import annotations

from plato.io import FileScope


# Idea generation: the canonical idea.md plus per-iteration history
# sidecars that the maker/hater debate writes between rounds.
IDEA_SCOPE = FileScope(
    write=[
        "input_files/idea.md",
        "idea_generation_output/idea.log",
        "idea_generation_output/LLM_calls.txt",
        "idea_generation_output/Error.txt",
        ".history/idea_*.md",
    ],
    read=["**/*"],
)

# Hater node never persists a file of its own — the criticism flows
# through state — but it does emit chunks into the shared streaming
# log file the maker also writes to.
IDEA_HATER_SCOPE = FileScope(
    write=[
        "idea_generation_output/idea.log",
        "idea_generation_output/LLM_calls.txt",
    ],
    read=["**/*"],
)

METHODS_FAST_SCOPE = FileScope(
    write=[
        "input_files/methods.md",
        "methods_generation_output/methods.log",
        "methods_generation_output/LLM_calls.txt",
        "methods_generation_output/Error.txt",
    ],
    read=["**/*"],
)

LITERATURE_SUMMARY_SCOPE = FileScope(
    write=[
        "input_files/literature.md",
        "literature_output/literature.log",
        "literature_output/LLM_calls.txt",
        "literature_output/Error.txt",
    ],
    read=["**/*"],
)

# Multi-source retrieval node: appends to the literature log + a
# papers-processed manifest. Doesn't write the final summary.
SEMANTIC_SCHOLAR_SCOPE = FileScope(
    write=[
        "literature_output/literature.log",
        "literature_output/papers_processed.log",
        "literature_output/LLM_calls.txt",
    ],
    read=["**/*"],
)

# Claim extraction emits Claim objects into state but does write
# its streaming LLM log.
CLAIM_EXTRACTOR_SCOPE = FileScope(
    write=[
        "claim_extraction.log",
    ],
    read=["**/*"],
)

REFEREE_SCOPE = FileScope(
    write=[
        "input_files/referee.md",
        "referee_output/referee.log",
        "referee_output/LLM_calls.txt",
        "referee_output/Error.txt",
        # PDF page images rendered for vision-model review.
        "referee_output/*.png",
        "referee_output/*.jpg",
    ],
    read=["**/*"],
)

CLARIFIER_SCOPE = FileScope(
    write=[
        "clarifications.json",
        "input_files/clarifications.md",
        "clarifier_output/clarifier.log",
        "clarifier_output/LLM_calls.txt",
    ],
    read=["**/*"],
)

NOVELTY_DECIDER_SCOPE = FileScope(
    write=[
        "literature_output/novelty.log",
        "literature_output/LLM_calls.txt",
    ],
    read=["**/*"],
)


__all__ = [
    "IDEA_SCOPE",
    "IDEA_HATER_SCOPE",
    "METHODS_FAST_SCOPE",
    "LITERATURE_SUMMARY_SCOPE",
    "SEMANTIC_SCHOLAR_SCOPE",
    "CLAIM_EXTRACTOR_SCOPE",
    "REFEREE_SCOPE",
    "CLARIFIER_SCOPE",
    "NOVELTY_DECIDER_SCOPE",
]
