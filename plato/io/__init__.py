"""
Plato I/O package.

Phase 3 (R11): scoped file writes for agent-driven file edits.

The :class:`ScopedWriter` enforces a per-node allowlist of glob patterns
relative to a project directory. This is opt-in for new nodes — existing
``paper_agents/tools.py`` continues to write files freely. New nodes that
adopt :class:`ScopedWriter` get a small, auditable safety net against
path-traversal, symlink escape, and accidental writes outside the
intended sandbox.
"""
from __future__ import annotations

from .scoped_node import scoped_node
from .scoped_writer import FileScope, ScopedWriter, ScopeError, writer_for_node

__all__ = [
    "FileScope",
    "ScopedWriter",
    "ScopeError",
    "scoped_node",
    "writer_for_node",
]
