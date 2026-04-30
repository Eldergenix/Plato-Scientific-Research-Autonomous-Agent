"""Adversarial paths against :class:`plato.io.scoped_writer.ScopedWriter`.

The writer is the file-system trust boundary for paper-graph nodes.
Every adversarial path here has a real-world analog: an LLM that
fabricates an absolute path, a corrupted ``state.json`` carrying
``..``-traversal, a symlink planted by a parallel run, or a NUL-byte
smuggle attempting to truncate the path on the C side.

If any of these slip through, a node could write outside its scope.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

from plato.io.scoped_writer import FileScope, ScopedWriter, ScopeError


@pytest.fixture
def writer(tmp_path: Path) -> ScopedWriter:
    """A writer rooted at a fresh tmp dir with a permissive scope.

    The scope intentionally allows ``**/*`` so the *only* reason a
    rejection occurs in these tests is the path-shape check, not the
    glob check. That keeps the failure modes independent.
    """
    scope = FileScope(write=["**/*"], read=["**/*"])
    return ScopedWriter(project_dir=tmp_path, scope=scope)


# ---------------------------------------------------------------------------
# Parent-traversal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_path",
    [
        "../etc/passwd",
        "foo/../../bar",
        "foo/../bar/../../baz",
        "./../escape.txt",
        "a/b/c/../../../../../../etc/passwd",
        "..",
        "../",
        "foo/..",
        # Even when ``..`` would normalize back inside project_dir, refuse.
        "subdir/../subdir/legit.txt",
    ],
)
def test_parent_traversal_is_rejected(writer: ScopedWriter, bad_path: str):
    with pytest.raises(ScopeError, match=r"parent-traversal|absolute"):
        writer.write(bad_path, "x")


# ---------------------------------------------------------------------------
# Absolute paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_path",
    [
        "/etc/passwd",
        "/tmp/evil.txt",
        "//double-slash",
        "/",
        # POSIX rejects backslash-prefixed paths as "starts with separator".
        "\\windows\\system32\\evil.exe",
    ],
)
def test_absolute_paths_are_rejected(writer: ScopedWriter, bad_path: str):
    with pytest.raises(ScopeError, match=r"absolute"):
        writer.write(bad_path, "x")


def test_absolute_path_inside_project_dir_is_still_rejected(tmp_path: Path):
    """An absolute path to a *legal* in-scope target is still rejected.

    The scope contract is "callers pass relative paths". An absolute
    path that happens to land inside ``project_dir`` would erode that
    contract, so refuse it even when the resolved target would be safe.
    """
    scope = FileScope(write=["**/*"], read=["**/*"])
    writer = ScopedWriter(project_dir=tmp_path, scope=scope)

    legit_abs = str((tmp_path / "out.txt").resolve())
    with pytest.raises(ScopeError, match=r"absolute"):
        writer.write(legit_abs, "x")


# ---------------------------------------------------------------------------
# Symlink escape
# ---------------------------------------------------------------------------


def test_symlink_pointing_outside_project_dir_is_rejected(tmp_path: Path):
    """A symlink inside project_dir that points outside must not be followed."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    # ``proj/escape`` -> ``../outside``
    link = project_dir / "escape"
    link.symlink_to(outside)

    scope = FileScope(write=["**/*"], read=["**/*"])
    writer = ScopedWriter(project_dir=project_dir, scope=scope)

    # Writing through the symlink dir must be refused.
    with pytest.raises(ScopeError, match=r"symlink|escapes project_dir"):
        writer.write("escape/pwned.txt", "x")


def test_symlink_to_in_scope_dir_resolves_safely(tmp_path: Path):
    """A symlink whose target is *inside* project_dir resolves to a safe path.

    ``Path.resolve()`` follows the link before the writer's parent walk,
    so the recorded target is the real directory and the write lands
    inside project_dir. This documents the actual contract: the writer
    catches *escape* via symlink (covered by other tests in this file),
    but a symlink that legitimately points back into project_dir is
    accepted because resolution flattens it.

    If you need to refuse all symlinks regardless of target, harden
    ``ScopedWriter._resolve`` to inspect the unresolved path before
    calling ``.resolve()``.
    """
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    real = project_dir / "real"
    real.mkdir()

    link = project_dir / "alias"
    link.symlink_to(real)

    scope = FileScope(write=["**/*"], read=["**/*"])
    writer = ScopedWriter(project_dir=project_dir, scope=scope)

    target = writer.write("alias/x.txt", "data")
    # The resolved target is inside project_dir (not outside), and the
    # parent dir on disk is the real directory, not the alias.
    assert target.resolve().is_relative_to(project_dir.resolve())
    assert (real / "x.txt").read_text() == "data"


def test_intermediate_symlink_directory_is_rejected(tmp_path: Path):
    """Symlink anywhere on the path — not just the leaf — must be caught."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    real_intermediate = tmp_path / "real_dir"
    real_intermediate.mkdir()

    # ``proj/sub`` is a symlink to a directory outside project_dir.
    link_dir = project_dir / "sub"
    link_dir.symlink_to(real_intermediate)

    scope = FileScope(write=["**/*"], read=["**/*"])
    writer = ScopedWriter(project_dir=project_dir, scope=scope)

    with pytest.raises(ScopeError, match=r"symlink|escapes project_dir"):
        writer.write("sub/leaf.txt", "x")


# ---------------------------------------------------------------------------
# Long paths
# ---------------------------------------------------------------------------


def test_path_longer_than_4096_chars_is_rejected_or_handled(writer: ScopedWriter):
    """Very long paths must either raise ScopeError or OSError — never write."""
    long_segment = "a" * 4097
    long_path = f"{long_segment}/file.txt"

    # The OS may bail with OSError before the writer ever materializes the
    # parent dir. Either rejection mode is acceptable; what matters is that
    # the file is NOT created and no surprise side-effect occurs.
    with pytest.raises((ScopeError, OSError)):
        writer.write(long_path, "x")


def test_deeply_nested_path_is_rejected_or_handled(writer: ScopedWriter):
    """A long ``a/a/a/...`` chain blows past PATH_MAX on most filesystems."""
    deep = "/".join(["a"] * 1024) + "/leaf.txt"

    with pytest.raises((ScopeError, OSError)):
        writer.write(deep, "x")


# ---------------------------------------------------------------------------
# NUL bytes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_path",
    [
        "foo\x00bar",
        "legit.txt\x00../../etc/passwd",
        "\x00",
        "dir/\x00/file.txt",
    ],
)
def test_nul_byte_in_path_is_rejected(writer: ScopedWriter, bad_path: str):
    """NUL bytes in paths must never reach the OS layer.

    Python's ``open()`` raises ``ValueError`` for embedded NULs, but a
    naive caller could swallow that. We assert the writer surfaces a
    rejection (ScopeError, ValueError, or OSError — any clear failure)
    rather than silently truncating at the NUL on the C side.
    """
    with pytest.raises((ScopeError, ValueError, OSError)):
        writer.write(bad_path, "x")


# ---------------------------------------------------------------------------
# Empty / pathological inputs
# ---------------------------------------------------------------------------


def test_empty_path_is_rejected(writer: ScopedWriter):
    with pytest.raises(ScopeError, match=r"empty"):
        writer.write("", "x")


def test_dotdot_only_at_root_is_rejected(writer: ScopedWriter):
    with pytest.raises(ScopeError):
        writer.write("..", "x")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-style absolute paths")
def test_windows_drive_letter_is_rejected(writer: ScopedWriter):
    with pytest.raises(ScopeError):
        writer.write("C:\\Windows\\System32\\evil.exe", "x")


# ---------------------------------------------------------------------------
# Positive control — ensure the writer still works for valid paths
# ---------------------------------------------------------------------------


def test_valid_relative_path_writes_successfully(tmp_path: Path):
    """Sanity: the adversarial parametrize lists above don't accidentally
    block legitimate writes."""
    scope = FileScope(write=["**/*"], read=["**/*"])
    writer = ScopedWriter(project_dir=tmp_path, scope=scope)

    target = writer.write("nested/dir/out.txt", "hello")
    assert target.read_text() == "hello"
    # Resolved path is under project_dir.
    assert tmp_path.resolve() in target.resolve().parents or target.resolve().parent.is_relative_to(
        tmp_path.resolve()
    )


def test_read_rejects_traversal(tmp_path: Path):
    """The same adversarial rules apply to reads."""
    scope = FileScope(write=["**/*"], read=["**/*"])
    writer = ScopedWriter(project_dir=tmp_path, scope=scope)

    # Plant a file outside project_dir and try to read it through ``..``.
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret")
    try:
        with pytest.raises(ScopeError):
            writer.read("../outside.txt")
    finally:
        if outside.exists():
            os.unlink(outside)
