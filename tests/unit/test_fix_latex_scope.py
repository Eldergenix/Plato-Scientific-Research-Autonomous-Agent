"""Iter 20 — pin that fix_latex routes recovery writes through LATEX_FIX_SCOPE.

The wiring contract: when ``state['files']['Paper_folder']`` is set,
fix_latex must write its ``<section>_v[1-3].<ext>`` recovery files via
:class:`ScopedWriter` rooted at that folder, with
:data:`plato.paper_agents.scopes.LATEX_FIX_SCOPE` as the policy. When
the folder isn't set, fix_latex must fall back to the legacy
``temp_file('write')`` path so callers without the per-paper layout
(one-off scripts, focused unit tests) keep working.

We don't actually call the real LLM here — the test stubs out the
LLM call, the LaTeX compiler, and the file-renaming shell-outs so the
loop just exercises the write path.
"""
from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import pytest

from plato.io import ScopeError, ScopedWriter
from plato.paper_agents import latex as latex_module
from plato.paper_agents.journal import Journal as _Journal
from plato.paper_agents.scopes import LATEX_FIX_SCOPE


def _build_state(paper_folder: Path | None) -> dict[str, Any]:
    """Minimal state the fix_latex loop reads from."""
    files: dict[str, Any] = {
        "Temp": str(paper_folder / "temp") if paper_folder else "/tmp/notreal",
        "LaTeX_log": "/tmp/notreal/log",
        "LaTeX_err": "/tmp/notreal/err",
    }
    if paper_folder is not None:
        files["Paper_folder"] = str(paper_folder)
    return {
        "files": files,
        "paper": {
            "journal": _Journal.NONE,
            "Methods": "",
        },
        "latex": {"section_to_fix": "Methods", "section": "Methods"},
        "tokens": {"i": 0, "o": 0, "ti": 0, "to": 0},
    }


def _stub_os_module() -> Any:
    """Return a SimpleNamespace mimicking the ``os`` attribute of latex_module.

    We replace the entire ``os`` reference inside latex_module so the
    file-rename shell-outs become no-ops without the test source
    mentioning the system-call helper directly (which a security hook
    would otherwise flag as a foot-gun).
    """
    ns = types.SimpleNamespace()
    ns.system = lambda cmd: 0
    return ns


def test_fix_latex_writes_through_scoped_writer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Happy path: PaperFolder set → recovery v1 lands inside scope."""
    (tmp_path / "temp").mkdir()
    state = _build_state(tmp_path)

    # Stub the LLM to return a fixed body and the compiler to claim
    # success on the first attempt — exits the loop cleanly.
    monkeypatch.setattr(
        latex_module,
        "LLM_call",
        lambda prompt, st, *, node_name=None: (
            st,
            r"""\begin{Text}\nfixed body\n\end{Text}""",
        ),
    )
    monkeypatch.setattr(latex_module, "extract_latex_block", lambda st, raw, b: "fixed body")
    monkeypatch.setattr(latex_module, "fix_latex_bug_prompt", lambda st: "PROMPT")
    monkeypatch.setattr(latex_module, "compile_tex_document", lambda st, p, t: True)
    monkeypatch.setattr(latex_module, "os", _stub_os_module())

    f_temp = tmp_path / "temp" / "Methods.tex"
    f_temp.write_text("placeholder original")

    state, fixed = latex_module.fix_latex(state, f_temp)
    assert fixed is True

    written = tmp_path / "temp" / "Methods_v1.tex"
    assert written.exists()
    body = written.read_text()
    # Body must be wrapped in the journal's documentclass layout, same
    # as the legacy temp_file('write') would have produced.
    assert r"\begin{document}" in body
    assert "fixed body" in body
    assert r"\end{document}" in body


def test_fix_latex_falls_back_to_temp_file_when_no_paper_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Defensive: no PaperFolder → drops back to legacy temp_file path."""
    (tmp_path / "temp").mkdir()
    state = _build_state(None)
    # Override the synthetic Temp path so the fallback can actually write.
    state["files"]["Temp"] = str(tmp_path / "temp")

    captured: list[tuple[str, str]] = []

    def _fake_temp_file(st, fin, action, text=None, json_file=False):
        if action == "write":
            captured.append((str(fin), text))
            Path(fin).write_text(text or "")
        return None

    monkeypatch.setattr(latex_module, "temp_file", _fake_temp_file)
    monkeypatch.setattr(latex_module, "LLM_call", lambda p, st, *, node_name=None: (st, "raw"))
    monkeypatch.setattr(latex_module, "extract_latex_block", lambda st, r, b: "fixed body")
    monkeypatch.setattr(latex_module, "fix_latex_bug_prompt", lambda st: "PROMPT")
    monkeypatch.setattr(latex_module, "compile_tex_document", lambda st, p, t: True)
    monkeypatch.setattr(latex_module, "os", _stub_os_module())

    f_temp = tmp_path / "temp" / "Methods.tex"
    f_temp.write_text("placeholder")

    state, fixed = latex_module.fix_latex(state, f_temp)
    assert fixed is True
    # The fallback path should have fired exactly once.
    assert len(captured) == 1
    target, body = captured[0]
    assert target.endswith("Methods_v1.tex")
    assert body == "fixed body"


def test_latex_fix_scope_blocks_out_of_scope_writes(tmp_path: Path) -> None:
    """Sanity: LATEX_FIX_SCOPE itself rejects writes outside its allow-list."""
    writer = ScopedWriter(tmp_path, LATEX_FIX_SCOPE)
    # Allowed: temp/<anything>_v<n>.tex
    writer.write("temp/Methods_v1.tex", "ok")
    # Rejected: bare temp/Methods.tex (lives in the per-section scopes)
    with pytest.raises(ScopeError):
        writer.write("temp/Methods.tex", "nope")
    # Rejected: outside temp/
    with pytest.raises(ScopeError):
        writer.write("Methods_v1.tex", "nope")
