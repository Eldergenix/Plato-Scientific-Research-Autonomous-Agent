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

# Iter-18 (R11 completion): the citations flow writes per-section
# .bib files plus first- and second-pass cleaned tex. These don't
# slot into any single section's scope (they're cross-cutting
# helpers called from ``add_citations_async`` and ``citations_node``)
# so they get their own scope rather than widening every section
# scope. ``*_w_citations*.tex`` covers both ``_w_citations.tex`` and
# ``_w_citations2.tex`` — the cleanup pass that follows the LLM
# rewrite.
CITATIONS_SCOPE = FileScope(
    write=[
        "temp/*.bib",
        "temp/*_w_citations.tex",
        "temp/*_w_citations2.tex",
    ],
    read=["**/*"],
)

# Iter-18: the LaTeX fixer (``latex.fix_latex``) writes versioned
# recovery files when a section fails to compile. It's called from
# inside many different node contexts (abstract / introduction /
# methods / refine / citations / ...), so the per-node scopes can't
# express what it actually writes — every section can produce up to
# three ``<section>_v[1-3].tex`` recovery candidates. A single broad
# scope captures the contract without forcing every per-section scope
# to widen its write set just to permit recovery files.
LATEX_FIX_SCOPE = FileScope(
    write=[
        "temp/*_v[1-9].tex",
        "temp/*_v[1-9][0-9].tex",
        "temp/*_v[1-9].bib",
        "temp/*_v[1-9][0-9].bib",
        # The fixer also renames the original aside as ``<section>_orig``;
        # leave that to the caller's mv pipeline (no scoped write).
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
    "LATEX_FIX_SCOPE",
]
