"""Tests for the Quarkdown render module.

Covers ``plato_dashboard.render.transformer`` (markdown -> .qd shaping)
and ``plato_dashboard.render.quarkdown`` / ``...render.pipeline`` (the
subprocess driver and the four-doctype orchestrator). The Quarkdown
binary is never actually invoked — the asyncio subprocess factory is
stubbed out so these tests stay sub-second and don't depend on the
external CLI being on $PATH.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from plato_dashboard.render import quarkdown as quarkdown_mod
from plato_dashboard.render import pipeline as pipeline_mod
from plato_dashboard.render.quarkdown import RenderResult, render_qd
from plato_dashboard.render.pipeline import render_all_artifacts
from plato_dashboard.render.transformer import (
    DocMeta,
    to_qd_docs,
    to_qd_paper,
    to_qd_plain,
    to_qd_slides,
    write_qd,
)


# --------------------------------------------------------------------- #
# transformer.to_qd_*
# --------------------------------------------------------------------- #
def test_to_qd_paper_emits_paged_doctype() -> None:
    out = to_qd_paper("# Hi", DocMeta(name="X"))
    assert out.startswith(".docname {X}")
    assert ".doctype {paged}" in out
    assert "# Hi" in out


def test_to_qd_slides_emits_slides_doctype() -> None:
    out = to_qd_slides("## Slide 1: Hi", DocMeta(name="X"))
    assert out.startswith(".docname {X}")
    assert ".doctype {slides}" in out


def test_to_qd_docs_emits_docs_doctype() -> None:
    out = to_qd_docs("# Hi", DocMeta(name="X"))
    assert out.startswith(".docname {X}")
    assert ".doctype {docs}" in out


def test_to_qd_plain_emits_plain_doctype() -> None:
    out = to_qd_plain("# Hi", DocMeta(name="X"))
    assert out.startswith(".docname {X}")
    assert ".doctype {plain}" in out


# --------------------------------------------------------------------- #
# transformer.write_qd
# --------------------------------------------------------------------- #
def test_write_qd_creates_parent_dirs(tmp_path: Path) -> None:
    dest = tmp_path / "a" / "b" / "c.qd"
    body = ".docname {X}\n.doctype {paged}\n\n# Hi"

    written = write_qd(body, dest)

    assert written == dest
    assert dest.is_file()
    assert dest.read_text(encoding="utf-8") == body


# --------------------------------------------------------------------- #
# quarkdown.render_qd — argv shaping
# --------------------------------------------------------------------- #
class _FakeProc:
    """Stand-in for the Process object returned by the asyncio subprocess
    factory. Records the argv it was invoked with so tests can assert on
    it; communicate returns canned output."""

    def __init__(
        self,
        stdout: bytes = b"out",
        stderr: bytes = b"",
        returncode: int = 0,
        timeout: bool = False,
    ) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self._timeout = timeout
        self._killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._timeout:
            # asyncio.wait_for wraps this call; sleeping forever surfaces
            # the same path as a real timeout (proc never returns).
            await asyncio.sleep(10)
        return self._stdout, self._stderr

    def kill(self) -> None:
        self._killed = True

    async def wait(self) -> int:
        return self.returncode


def _patch_subprocess(
    monkeypatch: pytest.MonkeyPatch, proc: _FakeProc
) -> dict:
    """Replace the asyncio subprocess factory and capture its argv."""
    captured: dict = {}

    async def _fake_exec(*args, **kwargs):
        captured["argv"] = list(args)
        captured["kwargs"] = kwargs
        return proc

    monkeypatch.setattr(
        quarkdown_mod.asyncio, "create_subprocess_exec", _fake_exec
    )
    return captured


def test_render_qd_calls_quarkdown_with_correct_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qd_path = tmp_path / "paper.qd"
    qd_path.write_text(".docname {X}\n.doctype {paged}\n\n# Hi")
    out_dir = tmp_path / "out"

    proc = _FakeProc(stdout=b"out", stderr=b"")
    captured = _patch_subprocess(monkeypatch, proc)

    result = asyncio.run(render_qd(qd_path, out_dir, pdf=False))

    assert isinstance(result, RenderResult)
    argv = captured["argv"]
    # The first six tokens are the load-bearing contract: command,
    # subcommand, input file, -o flag, output dir, --strict.
    assert argv[:6] == [
        "quarkdown",
        "c",
        str(qd_path),
        "-o",
        str(out_dir),
        "--strict",
    ]


def test_render_qd_passes_pdf_flag_when_pdf_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qd_path = tmp_path / "paper.qd"
    qd_path.write_text(".docname {X}\n.doctype {paged}\n")
    out_dir = tmp_path / "out"

    # pdf=True path: --pdf and --pdf-no-sandbox both present.
    proc = _FakeProc()
    captured = _patch_subprocess(monkeypatch, proc)
    asyncio.run(render_qd(qd_path, out_dir, pdf=True))
    argv = captured["argv"]
    assert "--pdf" in argv
    assert "--pdf-no-sandbox" in argv

    # pdf=False path: neither flag present. Pin no_sandbox=False to
    # keep the absence assertion crisp (in production no_sandbox is
    # independent of pdf, but a separate flag would muddy this check).
    proc2 = _FakeProc()
    captured2 = _patch_subprocess(monkeypatch, proc2)
    asyncio.run(render_qd(qd_path, out_dir, pdf=False, no_sandbox=False))
    argv2 = captured2["argv"]
    assert "--pdf" not in argv2
    assert "--pdf-no-sandbox" not in argv2


def test_render_qd_timeout_raises_runtime_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qd_path = tmp_path / "paper.qd"
    qd_path.write_text(".docname {X}\n.doctype {paged}\n")
    out_dir = tmp_path / "out"

    proc = _FakeProc(timeout=True)
    _patch_subprocess(monkeypatch, proc)

    with pytest.raises(RuntimeError, match="timed out"):
        # 1s timeout keeps the test fast; the FakeProc would otherwise
        # sleep 10s.
        asyncio.run(render_qd(qd_path, out_dir, pdf=False, timeout_s=1))

    assert proc._killed is True


# --------------------------------------------------------------------- #
# pipeline.render_all_artifacts — slides bucket gating
# --------------------------------------------------------------------- #
def _ok_render_result() -> RenderResult:
    return RenderResult(
        html_path=Path("/fake/x.html"),
        pdf_path=Path("/fake/x.pdf"),
        stdout="ok",
        stderr="",
        returncode=0,
    )


def test_render_all_artifacts_skips_slides_when_slides_md_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``slides_md=None`` (or empty string) must keep the slides bucket
    out of the result dict — the slide_outline node didn't run, so we
    have nothing to render and the UI shows "skipped" rather than a
    phantom completion."""

    async def _fake_safe_render(qd, out_dir, *, doctype):
        return _ok_render_result()

    async def _fake_render_qd(*args, **kwargs):
        return _ok_render_result()

    monkeypatch.setattr(pipeline_mod, "_safe_render", _fake_safe_render)
    monkeypatch.setattr(pipeline_mod, "render_qd", _fake_render_qd)

    project_root = tmp_path / "proj"
    project_root.mkdir()

    results = asyncio.run(
        render_all_artifacts(
            project_root,
            paper_md="# Hi",
            slides_md=None,
            meta=DocMeta(name="X"),
        )
    )

    assert "paged" in results
    assert "plain" in results
    assert "docs" in results
    assert "slides" not in results
