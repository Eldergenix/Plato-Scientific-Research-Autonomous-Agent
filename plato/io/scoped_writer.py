"""
Phase 3 — R11: scoped file writer.

``ScopedWriter`` is a thin wrapper around :class:`pathlib.Path` that
enforces a node-scoped allowlist of glob patterns. It refuses absolute
paths, ``..``-traversal, and symlinks that escape the project directory.

This is opt-in: existing tools in :mod:`plato.paper_agents.tools` still
write files directly. New nodes that want a smaller blast radius can
declare a :class:`FileScope` and route writes through the writer.
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path, PurePath, PurePosixPath
from typing import Union

from pydantic import BaseModel, Field


class ScopeError(Exception):
    """Raised when a path is rejected by a :class:`ScopedWriter`."""


class FileScope(BaseModel):
    """A per-node allowlist of write/read glob patterns.

    Patterns are matched against the *relative* path from the writer's
    project directory (always interpreted with POSIX separators). A
    pattern like ``"papers/**/*.tex"`` allows nested writes; ``"out.json"``
    allows exactly that file.
    """

    write: list[str] = Field(
        default_factory=list,
        description="Glob patterns (relative to project_dir) the node may write.",
    )
    read: list[str] = Field(
        default_factory=lambda: ["**/*"],
        description="Glob patterns the node may read. Defaults to all files.",
    )


PathLike = Union[str, Path]


class ScopedWriter:
    """Path-scoped read/write helper.

    Construct one per node with the ``project_dir`` it is allowed to
    operate inside. Every read/write goes through :meth:`read` or
    :meth:`write`, which reject:

    * absolute paths (``/etc/passwd``)
    * ``..``-traversal (``../../etc/passwd``)
    * symlinks that resolve outside ``project_dir``
    * paths that don't match any pattern in the relevant scope list
    """

    def __init__(self, project_dir: PathLike, scope: FileScope) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.scope = scope

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def write(self, relpath: PathLike, content: Union[str, bytes]) -> Path:
        """Write ``content`` to ``relpath``; return the absolute path written.

        Raises :class:`ScopeError` if ``relpath`` is outside the scope or
        otherwise invalid.
        """
        target = self._resolve(relpath, self.scope.write, op="write")
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content)
        return target

    def read(self, relpath: PathLike) -> bytes:
        """Read raw bytes from ``relpath``.

        Raises :class:`ScopeError` if ``relpath`` is outside the scope or
        otherwise invalid.
        """
        target = self._resolve(relpath, self.scope.read, op="read")
        return target.read_bytes()

    @staticmethod
    def matches(relpath: str, patterns: list[str]) -> bool:
        """Return True if ``relpath`` matches at least one of ``patterns``.

        Both :class:`pathlib.PurePath.match` (which understands ``**``)
        and :func:`fnmatch.fnmatch` (which is more forgiving for simple
        filename globs) are tried, so a pattern like ``"out.json"``
        matches ``"out.json"`` and ``"papers/**/*.tex"`` matches
        ``"papers/sec/intro.tex"``.

        ``**/`` at the start of a pattern means "zero or more directory
        segments" — so ``"**/*"`` matches both ``"file.txt"`` and
        ``"a/b/file.txt"``. (Stock :func:`fnmatch.fnmatch` and
        :meth:`PurePath.match` both require at least one separator,
        which is surprising for a default-allow scope.)
        """
        rel = PurePosixPath(relpath.replace(os.sep, "/"))
        rel_str = str(rel)
        for pat in patterns:
            posix_pat = pat.replace(os.sep, "/")
            if ScopedWriter._match_pattern(rel_str, posix_pat):
                return True
        return False

    @staticmethod
    def _match_pattern(rel_str: str, pattern: str) -> bool:
        """Single-pattern match with the ``**/`` zero-or-more extension."""
        candidates = [pattern]
        # ``**/X`` — also try ``X`` so it matches ``X`` at the project root.
        if pattern.startswith("**/"):
            candidates.append(pattern[len("**/") :])
        for cand in candidates:
            if not cand:
                continue
            try:
                if PurePath(rel_str).match(cand):
                    return True
            except ValueError:
                # PurePath.match raises on empty pattern — treat as no-match.
                pass
            if fnmatch.fnmatch(rel_str, cand):
                return True
        return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _resolve(
        self,
        relpath: PathLike,
        patterns: list[str],
        *,
        op: str,
    ) -> Path:
        rel_str = os.fspath(relpath)
        if not rel_str:
            raise ScopeError(f"{op}: empty path")

        # Reject absolute paths up front (POSIX or Windows-style).
        candidate = PurePath(rel_str)
        if candidate.is_absolute() or rel_str.startswith(("/", "\\")):
            raise ScopeError(f"{op}: absolute paths are not allowed: {rel_str!r}")

        # Reject any ``..`` segment — even if it would normalize back inside
        # project_dir, we don't want surprising parent traversal.
        parts = candidate.parts
        if any(p == ".." for p in parts):
            raise ScopeError(f"{op}: parent-traversal '..' is not allowed: {rel_str!r}")

        # Pattern check is done on the as-given relative path so callers
        # can write meaningful globs.
        normalized = str(PurePosixPath(*parts)) if parts else ""
        if not self.matches(normalized, patterns):
            raise ScopeError(
                f"{op}: {rel_str!r} does not match any allowed pattern in {patterns!r}"
            )

        target = (self.project_dir / candidate).resolve()

        # Symlink / containment check: the resolved target must still be
        # under the resolved project_dir. ``Path.resolve`` follows symlinks
        # so any escape via symlink shows up here.
        try:
            target.relative_to(self.project_dir)
        except ValueError as exc:
            raise ScopeError(
                f"{op}: resolved path escapes project_dir: {target} not under {self.project_dir}"
            ) from exc

        # Extra defense: if the path itself (or any parent below
        # project_dir) is a symlink, refuse — even if it currently points
        # inside the project, the target could be swapped later.
        self._reject_symlinks(target)

        return target

    def _reject_symlinks(self, target: Path) -> None:
        """Walk from ``target`` up to ``project_dir`` and refuse symlinks."""
        cur = target
        # Use lexical equality on resolved paths — both are already resolved.
        while cur != self.project_dir:
            if cur.is_symlink():
                raise ScopeError(
                    f"refusing to follow symlink: {cur}"
                )
            parent = cur.parent
            if parent == cur:
                # Reached filesystem root without hitting project_dir; the
                # containment check above should have caught this already.
                raise ScopeError(f"path escapes project_dir: {target}")
            cur = parent


def writer_for_node(
    project_dir: PathLike,
    node_name: str,
    scope: FileScope | None = None,
) -> ScopedWriter:
    """Build a :class:`ScopedWriter` for ``node_name`` rooted at ``project_dir``.

    Thin convenience used by paper-graph nodes that already declare a
    :class:`FileScope` in :mod:`plato.paper_agents.scopes`. ``scope`` is
    required — a node without an explicit scope has nothing to enforce, so
    we refuse to fabricate a default that would silently allow everything.
    """
    if scope is None:
        raise ValueError(
            f"writer_for_node({node_name!r}): a FileScope is required; "
            "pass an explicit scope from plato.paper_agents.scopes."
        )
    return ScopedWriter(project_dir=project_dir, scope=scope)


__all__ = ["FileScope", "ScopedWriter", "ScopeError", "writer_for_node"]
