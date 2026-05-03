"""Phase 4 — R11 adoption: per-node :class:`FileScope` declarations.

Each paper-graph node writes to a small, documented set of files. These
scopes encode what ``abstract_node``, ``methods_node`` and
``conclusions_node`` may actually touch when going through a
:class:`plato.io.ScopedWriter`.

The scopes describe **the actual filesystem layout** that the existing
compile/fix pipeline (``compile_tex_document`` → ``fix_latex``) reads
from. ``temp/<Section>.tex`` is the canonical artifact for each section.
The corresponding ``paper/<section>.{tex,json,md}`` slots are reserved
for the upcoming structured-section refactor (Phase 5+) and stay in
scope so that incremental migration does not require widening the list.
Until that refactor lands, only the ``temp/`` paths see writes; the
``paper/`` paths are inert.
"""
from __future__ import annotations

from plato.io import FileScope


ABSTRACT_SCOPE = FileScope(
    write=[
        # Active paths (legacy compile/fix pipeline reads these).
        "temp/Abstract.tex",
        "temp/Title.tex",
        # Reserved for the Phase-5 structured-section refactor.
        "paper/abstract.tex",
        "paper/abstract.json",
        "paper/abstract.md",
    ],
    read=["**/*"],
)

METHODS_SCOPE = FileScope(
    write=[
        "temp/Methods.tex",
        "paper/methods.tex",
        "paper/methods.json",
        "paper/methods.md",
    ],
    read=["**/*"],
)

CONCLUSIONS_SCOPE = FileScope(
    write=[
        "temp/Conclusions.tex",
        "paper/conclusions.tex",
        "paper/conclusions.json",
        "paper/conclusions.md",
    ],
    read=["**/*"],
)

INTRODUCTION_SCOPE = FileScope(
    write=[
        "temp/Introduction.tex",
        "paper/introduction.tex",
        "paper/introduction.json",
    ],
    read=["**/*"],
)

RESULTS_SCOPE = FileScope(
    write=[
        "temp/Results.tex",
        "paper/results.tex",
        "paper/results.json",
    ],
    read=["**/*"],
)

KEYWORDS_SCOPE = FileScope(
    write=[
        # Active: Keywords.tex compiled by compile_tex_document.
        "temp/Keywords.tex",
        # Reserved structured outputs.
        "paper/keywords.tex",
        "paper/AAS_keywords.txt",
    ],
    read=["**/*"],
)

PLOTS_SCOPE = FileScope(
    write=[
        # JSON caption caches written per batch (e.g. plots_1_7.json).
        "temp/plots_*.json",
        # Compiled results-with-figures section files.
        "temp/Results_*.tex",
        # Reserved structured plot output.
        "paper/Plots/**/*",
    ],
    read=["**/*"],
)

REFINE_SCOPE = FileScope(
    write=[
        "temp/Results_refined.tex",
        # Paper version artifacts produced by save_paper.
        "paper_v*.tex",
        "paper_v*.pdf",
        "paper_v*.aux",
        "paper_v*.log",
        "paper_v*.out",
        "paper_v*.bbl",
        "paper_v*.blg",
        # Sidecar companion files.
        "paper_folder/**/*",
    ],
    read=["**/*"],
)

# Async citations node: writes per-section ``*_w_citations*.tex`` + ``.bib``
# partials under ``temp/`` and the paper_v3/paper_v4 artifacts plus the
# bibliography sidecars produced by ``save_bib`` / ``process_bib_file``.
CITATIONS_SCOPE = FileScope(
    write=[
        "temp/*_w_citations.tex",
        "temp/*_w_citations2.tex",
        "temp/*.bib",
        "paper_v*.tex",
        "paper_v*.pdf",
        "paper_v*.aux",
        "paper_v*.log",
        "paper_v*.out",
        "paper_v*.bbl",
        "paper_v*.blg",
        "bibliography.bib",
        "bibliography_temp.bib",
    ],
    read=["**/*"],
)

# R3 citation validator: writes a per-run sidecar JSON next to the rest of
# the run artifacts under ``runs/<run_id>/`` (relative to ``Folder``).
CITATION_VALIDATOR_SCOPE = FileScope(
    write=[
        "runs/*/validation_report.json",
    ],
    read=["**/*"],
)

# R5 evidence matrix: writes the per-run JSONL matrix alongside the
# validator's report.
EVIDENCE_MATRIX_SCOPE = FileScope(
    write=[
        "runs/*/evidence_matrix.jsonl",
    ],
    read=["**/*"],
)


__all__ = [
    "ABSTRACT_SCOPE",
    "METHODS_SCOPE",
    "CONCLUSIONS_SCOPE",
    "INTRODUCTION_SCOPE",
    "RESULTS_SCOPE",
    "KEYWORDS_SCOPE",
    "PLOTS_SCOPE",
    "REFINE_SCOPE",
    "CITATIONS_SCOPE",
    "CITATION_VALIDATOR_SCOPE",
    "EVIDENCE_MATRIX_SCOPE",
]
