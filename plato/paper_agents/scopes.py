"""Phase 4 — R11 adoption: per-node :class:`FileScope` declarations.

Each paper-graph node should write only to a small, documented set of
files. These scopes pin down what ``abstract_node``, ``methods_node`` and
``conclusions_node`` are allowed to touch when they go through a
:class:`plato.io.ScopedWriter`.

Backward-compatibility note: the legacy nodes also write LaTeX-wrapped
section files into the ``temp/`` directory (e.g. ``temp/Abstract.tex``)
that drive the existing compile/fix pipeline. We widen the scopes to
include those paths rather than refactoring the pipeline in this commit.
Lines marked ``# scope-widening`` are explicit allowances for legacy
write locations.
"""
from __future__ import annotations

from plato.io import FileScope


ABSTRACT_SCOPE = FileScope(
    write=[
        "paper/abstract.tex",
        "paper/abstract.json",
        "paper/abstract.md",
        "temp/Abstract.tex",  # scope-widening: legacy temp_file() output
        "temp/Title.tex",     # scope-widening: legacy temp_file() output
    ],
    read=["**/*"],
)

METHODS_SCOPE = FileScope(
    write=[
        "paper/methods.tex",
        "paper/methods.json",
        "paper/methods.md",
        "temp/Methods.tex",  # scope-widening: legacy temp_file() output
    ],
    read=["**/*"],
)

CONCLUSIONS_SCOPE = FileScope(
    write=[
        "paper/conclusions.tex",
        "paper/conclusions.json",
        "paper/conclusions.md",
        "temp/Conclusions.tex",  # scope-widening: legacy temp_file() output
    ],
    read=["**/*"],
)


__all__ = ["ABSTRACT_SCOPE", "METHODS_SCOPE", "CONCLUSIONS_SCOPE"]
