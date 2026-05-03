"""Iter 16 — pin that every LLM_call site in production code passes ``node_name=``.

This is a static-analysis test: it greps the source tree for ``LLM_call(``
and ``LLM_call_stream(`` calls, then asserts each one threads
``node_name=`` through. Without this guard a casual LLM_call added to a
new node would silently leave the R9 manifest's ``prompt_hashes`` empty —
and there's no visible test failure to catch the regression.

The helper itself (``def LLM_call`` / ``def LLM_call_stream``) is
exempt, as is anything inside a ``# noqa: node-name`` comment, in case a
future reviewer panel reviewer needs a one-off bypass.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


# Only scan the production package, not tests / docs / vendored LaTeX.
_PROD_ROOTS = (
    Path(__file__).parent.parent.parent / "plato",
)
# Anything matching this pattern is the function declaration itself.
_DEF_RE = re.compile(r"\bdef\s+LLM_call(_stream)?\b")
# Anything matching this is a call site we need to inspect.
_CALL_RE = re.compile(r"\bLLM_call(?:_stream)?\(")


def _python_sources() -> list[Path]:
    out: list[Path] = []
    for root in _PROD_ROOTS:
        out.extend(p for p in root.rglob("*.py") if p.is_file())
    return out


@pytest.mark.parametrize("source_path", _python_sources(), ids=lambda p: str(p.relative_to(_PROD_ROOTS[0])))
def test_every_llm_call_passes_node_name(source_path: Path) -> None:
    """Each ``LLM_call(...)`` / ``LLM_call_stream(...)`` call must include ``node_name=``."""
    text = source_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    offenders: list[tuple[int, str]] = []
    for lineno, line in enumerate(lines, start=1):
        # Skip the helper definition itself.
        if _DEF_RE.search(line):
            continue
        # Skip docstrings/comments — only Python statement lines matter.
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        # Skip conditional opt-out for one-off bypasses.
        if "# noqa: node-name" in line:
            continue

        if _CALL_RE.search(line) and "node_name=" not in line:
            # Multi-line calls: scan the next few lines for ``node_name=``.
            window = "\n".join(lines[lineno - 1 : lineno + 4])
            if "node_name=" not in window:
                offenders.append((lineno, stripped))

    assert not offenders, (
        f"{source_path}: found LLM_call sites missing node_name=:\n"
        + "\n".join(f"  L{n}: {s}" for n, s in offenders)
    )
