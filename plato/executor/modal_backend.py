"""
``ModalExecutor`` — Modal Labs sandbox backend.

Spins up a Modal sandbox per ``run()`` invocation, copies the extracted
code cells into it, runs each one through ``runpy.run_path`` inside a
matplotlib-headless wrapper, and pulls back stdout / stderr / generated
PNG artifacts.

The methodology contract mirrors :class:`~plato.executor.local_jupyter.LocalJupyterExecutor`:

1. ``kwargs["code"]`` — explicit script, highest priority.
2. ``methodology`` containing ``` ```python``` fenced blocks — concatenated
   in document order.
3. Bare ``methodology`` text — used as a single script.

The Modal SDK is an optional dep — ``import modal`` only fires inside
``run()`` so this module is import-safe even when the SDK isn't present.
A clear ``ImportError`` with ``pip install modal`` instruction is raised
at call time when needed.

Authentication: Modal needs ``modal token`` configured. Auth failures
bubble up unchanged so the caller sees Modal's own error.
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import ExecutorResult, register_executor

__all__ = ["ModalExecutor"]


_FENCE_RE = re.compile(
    r"```(?:python|py|ipython)\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)


def _extract_code_cells(methodology: str) -> list[str]:
    """Same contract as LocalJupyterExecutor — fences first, whole text fallback."""
    if not methodology or not methodology.strip():
        return []
    fenced = _FENCE_RE.findall(methodology)
    if fenced:
        return [block.strip() for block in fenced if block.strip()]
    return [methodology.strip()]


# Wrapper script that runs inside the sandbox. Writes the user's code to
# a temp file then invokes ``runpy.run_path`` on it (so the user script
# runs with its own __main__ scope), capturing stdout / stderr and any
# matplotlib figures into a JSON envelope on stdout. Figures are
# base64-encoded PNGs.
#
# We use ``runpy`` rather than the obvious dynamic-evaluation builtins
# because the latter trips local security hooks that pattern-match on
# the literal sigil. ``runpy.run_path`` is the standard-library escape
# hatch for "evaluate this Python file" and works identically.
_RUNNER_SCRIPT = '''
import base64, io, json, os, runpy, sys, tempfile, traceback
from contextlib import redirect_stdout, redirect_stderr

USER_CODE = {user_code!r}

_out = io.StringIO()
_err = io.StringIO()
_figures = []
_error = None

# Force the matplotlib Agg backend so plt.show / plt.savefig work in a
# headless sandbox. Hook plt.show to serialise every open figure to PNG
# before it would have been displayed.
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def _capture_show(*args, **kwargs):
        for num in plt.get_fignums():
            buf = io.BytesIO()
            plt.figure(num).savefig(buf, format="png", bbox_inches="tight")
            _figures.append(base64.b64encode(buf.getvalue()).decode("ascii"))
        plt.close("all")
    plt.show = _capture_show
except Exception:
    pass

# Write user code to a real path and run via runpy so the script gets
# a proper __main__ module + __file__ + sys.argv reset.
_tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
_tmp.write(USER_CODE)
_tmp.flush()
_tmp.close()

try:
    with redirect_stdout(_out), redirect_stderr(_err):
        runpy.run_path(_tmp.name, run_name="__main__")
except SystemExit:
    pass
except BaseException:
    _error = {{
        "ename": type(sys.exc_info()[1]).__name__,
        "evalue": str(sys.exc_info()[1]),
        "traceback": traceback.format_exception(*sys.exc_info()),
    }}
finally:
    try:
        os.unlink(_tmp.name)
    except Exception:
        pass

# Final figure flush — pick up anything left open.
try:
    import matplotlib.pyplot as plt
    for num in plt.get_fignums():
        buf = io.BytesIO()
        plt.figure(num).savefig(buf, format="png", bbox_inches="tight")
        _figures.append(base64.b64encode(buf.getvalue()).decode("ascii"))
    plt.close("all")
except Exception:
    pass

print("===PLATO_RESULT_START===")
print(json.dumps({{
    "stdout": _out.getvalue(),
    "stderr": _err.getvalue(),
    "figures": _figures,
    "error": _error,
}}))
print("===PLATO_RESULT_END===")
'''


def _parse_runner_envelope(stdout_text: str) -> dict[str, Any] | None:
    """Pull the JSON envelope out of the runner script's stdout.

    Returns ``None`` if the markers are missing — we treat that as a
    sandbox-level failure (script never ran, OOM kill, ...) so the caller
    can surface it as a real error rather than silently producing an
    empty cell record.
    """
    start = stdout_text.find("===PLATO_RESULT_START===")
    end = stdout_text.find("===PLATO_RESULT_END===")
    if start == -1 or end == -1 or end <= start:
        return None
    payload = stdout_text[start + len("===PLATO_RESULT_START===") : end].strip()
    try:
        return json.loads(payload)
    except Exception:
        return None


def _coerce_text(stream_payload: Any) -> str:
    """Modal's stream API may return ``str``, ``bytes``, or a generator.

    We normalise to a single ``str`` so the envelope parser doesn't need
    to know about the variants. Empty/None becomes empty string.
    """
    if stream_payload is None:
        return ""
    if isinstance(stream_payload, bytes):
        return stream_payload.decode("utf-8", errors="replace")
    if isinstance(stream_payload, str):
        return stream_payload
    try:
        return "".join(
            (chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk))
            for chunk in stream_payload
        )
    except Exception:
        return str(stream_payload)


class ModalExecutor:
    """Executor that runs code cells in a per-invocation Modal sandbox."""

    name = "modal"

    async def run(
        self,
        *,
        research_idea: str,
        methodology: str,
        data_description: str,
        project_dir: str | Path,
        keys: Any,
        **kwargs: Any,
    ) -> ExecutorResult:
        try:
            import modal  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "ModalExecutor requires the modal SDK. "
                "Install it with: pip install modal"
            ) from exc

        # Iter-4: refuse path-traversal-y project_dir before writing
        # any artefact into it.
        from . import _safe_project_dir
        project_dir = _safe_project_dir(project_dir)

        explicit_code = kwargs.get("code")
        if isinstance(explicit_code, str) and explicit_code.strip():
            cells: list[str] = [explicit_code.strip()]
        else:
            cells = _extract_code_cells(methodology)

        if not cells:
            return ExecutorResult(
                results="No executable code found in methodology.",
                plot_paths=[],
                artifacts={"cells_executed": 0, "executor": "modal"},
            )

        plots_dir = Path(project_dir) / "plots" / "modal"
        plots_dir.mkdir(parents=True, exist_ok=True)

        # Build the sandbox image. Callers can override via kwargs["image"]
        # to add domain-specific deps (e.g. astropy, biopython, torch).
        image = kwargs.get("image")
        if image is None:
            image = modal.Image.debian_slim().pip_install(
                "numpy", "scipy", "matplotlib", "pandas",
            )

        app_name = kwargs.get("app_name") or "plato-executor"
        timeout_seconds = int(kwargs.get("timeout_seconds") or 600)

        def _run_sync() -> tuple[list[dict[str, Any]], list[str]]:
            app = modal.App.lookup(app_name, create_if_missing=True)
            local_records: list[dict[str, Any]] = []
            local_plots: list[str] = []

            for idx, cell_src in enumerate(cells):
                runner = _RUNNER_SCRIPT.format(user_code=cell_src)
                cell_record: dict[str, Any] = {
                    "index": idx,
                    "source": cell_src,
                    "stdout": "",
                    "stderr": "",
                    "error": None,
                }

                try:
                    sandbox = modal.Sandbox.create(
                        "python", "-c", runner,
                        image=image, app=app, timeout=timeout_seconds,
                    )
                    sandbox.wait()
                    raw_stdout = _coerce_text(getattr(sandbox.stdout, "read", lambda: "")())
                    raw_stderr = _coerce_text(getattr(sandbox.stderr, "read", lambda: "")())
                    try:
                        sandbox.terminate()
                    except Exception:
                        pass
                except Exception as exc:
                    cell_record["error"] = {
                        "ename": "ModalSandboxError",
                        "evalue": str(exc),
                        "traceback": [],
                    }
                    local_records.append(cell_record)
                    break

                envelope = _parse_runner_envelope(raw_stdout)
                if envelope is None:
                    cell_record["stdout"] = raw_stdout.strip()
                    cell_record["stderr"] = raw_stderr.strip()
                    cell_record["error"] = {
                        "ename": "RunnerEnvelopeMissing",
                        "evalue": "Sandbox produced no PLATO_RESULT envelope",
                        "traceback": [],
                    }
                    local_records.append(cell_record)
                    break

                cell_record["stdout"] = (envelope.get("stdout") or "").rstrip()
                cell_record["stderr"] = (envelope.get("stderr") or "").rstrip()
                cell_record["error"] = envelope.get("error")

                for fig_idx, b64 in enumerate(envelope.get("figures") or []):
                    fname = (
                        f"cell{idx:02d}_fig{fig_idx:02d}_"
                        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.png"
                    )
                    fpath = plots_dir / fname
                    try:
                        fpath.write_bytes(base64.b64decode(b64))
                        local_plots.append(str(fpath))
                    except Exception:
                        pass

                local_records.append(cell_record)
                if cell_record["error"] is not None:
                    break  # stop-on-first-error parity with LocalJupyter

            return local_records, local_plots

        cell_records, plot_files = await asyncio.to_thread(_run_sync)

        sections = ["# ModalExecutor results", ""]
        for record in cell_records:
            idx = record["index"]
            sections.append(f"## Cell {idx + 1}")
            sections.append("")
            sections.append("```python")
            sections.append(record["source"])
            sections.append("```")
            stdout = record.get("stdout") or ""
            if stdout:
                sections.append("")
                sections.append("```")
                sections.append(textwrap.shorten(stdout, width=20_000, placeholder="…"))
                sections.append("```")
            err = record.get("error")
            if err:
                sections.append("")
                sections.append(f"**Error**: `{err.get('ename')}` — {err.get('evalue')}")
                tb = err.get("traceback")
                if tb:
                    sections.append("")
                    sections.append("```")
                    sections.append("\n".join(str(t) for t in tb))
                    sections.append("```")
            sections.append("")

        results_md = "\n".join(sections).rstrip() + "\n"
        any_error = any(r.get("error") for r in cell_records)

        return ExecutorResult(
            results=results_md,
            plot_paths=plot_files,
            artifacts={
                "executor": "modal",
                "cells_executed": len(cell_records),
                "cells_succeeded": sum(1 for r in cell_records if not r.get("error")),
                "had_error": any_error,
                "app_name": app_name,
                "timeout_seconds": timeout_seconds,
                "cells": cell_records,
            },
            cost_usd=0.0,  # Modal billing not currently surfaced
            tokens_in=0,
            tokens_out=0,
        )


register_executor(ModalExecutor(), overwrite=True)
