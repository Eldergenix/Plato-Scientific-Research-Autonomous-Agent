"""
``E2BExecutor`` — E2B (e2b.dev) Code Interpreter sandbox backend.

The E2B Code Interpreter SDK is purpose-built for this kind of
"send-code-to-a-jupyter-flavoured-sandbox-and-get-rich-results-back"
workflow: ``Sandbox.run_code(code)`` returns an execution object with
``.stdout``, ``.stderr``, ``.results`` (a list of display payloads
including ``png`` / ``jpeg`` / ``html``), and ``.error`` (an exception
record with ``name``, ``value``, ``traceback``). We don't need the
custom matplotlib runner script that ModalExecutor uses — E2B's
notebook surface captures plots natively.

Methodology contract is identical to the other executors:

1. ``kwargs["code"]`` — explicit script, highest priority.
2. ``methodology`` containing ``` ```python``` fenced blocks — concatenated
   in document order.
3. Bare ``methodology`` text — used as a single script.

The E2B SDK is an optional dep — ``import e2b_code_interpreter`` only
fires inside ``run()`` so this module is import-safe even when the SDK
isn't installed. A clear ``ImportError`` with the install hint is
raised at call time when needed.

Authentication: E2B uses ``E2B_API_KEY`` env var (or
``Sandbox(api_key=...)``). Auth failures bubble up unchanged so the
caller sees E2B's own error.
"""
from __future__ import annotations

import asyncio
import base64
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import ExecutorResult, register_executor

__all__ = ["E2BExecutor"]


_FENCE_RE = re.compile(
    r"```(?:python|py|ipython)\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)


def _extract_code_cells(methodology: str) -> list[str]:
    """Same contract as LocalJupyter / Modal — fences first, whole text fallback."""
    if not methodology or not methodology.strip():
        return []
    fenced = _FENCE_RE.findall(methodology)
    if fenced:
        return [block.strip() for block in fenced if block.strip()]
    return [methodology.strip()]


def _coerce_text(value: Any) -> str:
    """Normalise E2B output to ``str``.

    The SDK historically returned ``stdout`` as either ``str`` or
    ``list[str]`` (one entry per emit). We tolerate both so we don't
    pin a specific minor version.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return "".join(str(part) for part in value)
    return str(value)


def _extract_png(result_obj: Any) -> str | None:
    """Pull a base64 PNG payload off an E2B ``Result`` instance.

    Older SDK versions exposed it as ``.png`` (a ``str`` of base64),
    newer versions store rich payloads under ``.formats`` /
    ``.raw_data["image/png"]``. Try both shapes; return ``None`` if
    neither matches.
    """
    direct = getattr(result_obj, "png", None)
    if isinstance(direct, str) and direct:
        return direct

    raw = getattr(result_obj, "raw", None) or getattr(result_obj, "raw_data", None)
    if isinstance(raw, dict):
        png = raw.get("image/png")
        if isinstance(png, str) and png:
            return png
    return None


class E2BExecutor:
    """Executor that runs code cells in an E2B Code Interpreter sandbox."""

    name = "e2b"

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
            from e2b_code_interpreter import Sandbox  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "E2BExecutor requires the e2b-code-interpreter SDK. "
                "Install it with: pip install e2b-code-interpreter"
            ) from exc

        # Iter-4 path-traversal guard parity with the modal/local backends.
        # Refuse project_dir that resolves outside Path.home / tmp /
        # PLATO_PROJECT_ROOT before any artefact lands.
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
                artifacts={"cells_executed": 0, "executor": "e2b"},
            )

        plots_dir = Path(project_dir) / "plots" / "e2b"
        plots_dir.mkdir(parents=True, exist_ok=True)

        api_key = kwargs.get("api_key")
        timeout_seconds = int(kwargs.get("timeout_seconds") or 300)
        template = kwargs.get("template")  # Optional named E2B template

        def _run_sync() -> tuple[list[dict[str, Any]], list[str]]:
            sandbox_kwargs: dict[str, Any] = {}
            if api_key:
                sandbox_kwargs["api_key"] = api_key
            if template:
                sandbox_kwargs["template"] = template

            local_records: list[dict[str, Any]] = []
            local_plots: list[str] = []

            sandbox = Sandbox(**sandbox_kwargs)
            try:
                for idx, cell_src in enumerate(cells):
                    cell_record: dict[str, Any] = {
                        "index": idx,
                        "source": cell_src,
                        "stdout": "",
                        "stderr": "",
                        "error": None,
                    }

                    try:
                        execution = sandbox.run_code(
                            cell_src, timeout=timeout_seconds
                        )
                    except Exception as exc:
                        cell_record["error"] = {
                            "ename": "E2BSandboxError",
                            "evalue": str(exc),
                            "traceback": [],
                        }
                        local_records.append(cell_record)
                        break

                    # Newer SDKs expose ``.logs.stdout`` / ``.logs.stderr``
                    # while older ones expose ``.stdout`` / ``.stderr``
                    # directly. Tolerate both layouts.
                    logs = getattr(execution, "logs", None)
                    if logs is not None:
                        cell_record["stdout"] = _coerce_text(
                            getattr(logs, "stdout", "")
                        ).rstrip()
                        cell_record["stderr"] = _coerce_text(
                            getattr(logs, "stderr", "")
                        ).rstrip()
                    else:
                        cell_record["stdout"] = _coerce_text(
                            getattr(execution, "stdout", "")
                        ).rstrip()
                        cell_record["stderr"] = _coerce_text(
                            getattr(execution, "stderr", "")
                        ).rstrip()

                    err = getattr(execution, "error", None)
                    if err is not None:
                        cell_record["error"] = {
                            "ename": getattr(err, "name", "Error"),
                            "evalue": getattr(err, "value", ""),
                            "traceback": getattr(err, "traceback", []) or [],
                        }

                    for fig_idx, result_obj in enumerate(
                        getattr(execution, "results", []) or []
                    ):
                        png_b64 = _extract_png(result_obj)
                        if not png_b64:
                            continue
                        fname = (
                            f"cell{idx:02d}_fig{fig_idx:02d}_"
                            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.png"
                        )
                        fpath = plots_dir / fname
                        try:
                            fpath.write_bytes(base64.b64decode(png_b64))
                            local_plots.append(str(fpath))
                        except Exception:
                            pass

                    local_records.append(cell_record)
                    if cell_record["error"] is not None:
                        # Stop-on-first-error parity.
                        break
            finally:
                # Sandbox.kill() is the v1+ API; .close() is the legacy
                # one. Try the modern method first then fall through.
                kill = getattr(sandbox, "kill", None) or getattr(
                    sandbox, "close", None
                )
                if callable(kill):
                    try:
                        kill()
                    except Exception:
                        pass

            return local_records, local_plots

        cell_records, plot_files = await asyncio.to_thread(_run_sync)

        sections = ["# E2BExecutor results", ""]
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
                "executor": "e2b",
                "cells_executed": len(cell_records),
                "cells_succeeded": sum(1 for r in cell_records if not r.get("error")),
                "had_error": any_error,
                "template": template,
                "timeout_seconds": timeout_seconds,
                "cells": cell_records,
            },
            cost_usd=0.0,  # E2B billing not currently surfaced
            tokens_in=0,
            tokens_out=0,
        )


register_executor(E2BExecutor(), overwrite=True)
