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


__all__ = ["ABSTRACT_SCOPE", "METHODS_SCOPE", "CONCLUSIONS_SCOPE"]
