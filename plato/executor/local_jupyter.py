"""
``LocalJupyterExecutor`` — execute generated code in a local Jupyter kernel.

The methodology field of an Executor invocation may arrive in three shapes:

1. **Explicit code** via ``kwargs["code"]`` — a literal Python script the
   caller wants run as-is. Highest priority, never re-extracted.
2. **Markdown with fenced ``python`` blocks** — typical LLM output. We
   concatenate every ``` ```python ... ``` ``` block in document order.
3. **Plain text** — used directly as the script body. The "is this code"
   judgement is left to the caller; we don't try to compile-check.

Each script runs in a freshly launched kernel. Outputs are captured from
the IOPub channel (stream / display_data / execute_result / error) and
flattened into a markdown summary. ``image/png`` payloads are
base64-decoded and written to ``project_dir/plots/local_jupyter/`` so the
existing ``ExecutorResult.plot_paths`` contract round-trips cleanly.

The execution loop runs in a worker thread via ``asyncio.to_thread`` so
the protocol's ``async def run`` stays awaitable without blocking the
caller's event loop on ``KernelClient.get_iopub_msg``.
"""
from __future__ import annotations

import asyncio
import base64
import re
import textwrap
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import ExecutorResult, register_executor

__all__ = ["LocalJupyterExecutor"]


# Capture both fenced styles: ``` ```python ... ``` ``` and the bare
# ``` ``` ... ``` ``` form. We only collect the python-tagged blocks; bare
# fences are ambiguous (could be shell, JSON, ...) and skipped to avoid
# silently feeding non-python content to the kernel.
_FENCE_RE = re.compile(
    r"```(?:python|py|ipython)\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)


def _extract_code_cells(methodology: str) -> list[str]:
    """Return one cell per fenced python block, or one cell holding the whole text.

    The "fall back to whole text" path is what makes this executor usable
    for callers who hand it raw scripts — the more common path in
    practice when ``methodology`` is built from a hand-written cell rather
    than from LLM output.
    """
    if not methodology or not methodology.strip():
        return []
    fenced = _FENCE_RE.findall(methodology)
    if fenced:
        return [block.strip() for block in fenced if block.strip()]
    return [methodology.strip()]


def _format_traceback(payload: dict[str, Any]) -> str:
    raw = payload.get("traceback")
    if isinstance(raw, list):
        return "\n".join(str(line) for line in raw)
    return str(raw or payload.get("evalue") or "<unknown error>")


class LocalJupyterExecutor:
    """Executor that runs code cells in a locally launched Jupyter kernel."""

    name = "local_jupyter"

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
        # Lazy import — keeps the module cheap when jupyter-client isn't
        # installed in the active environment. The clean error message is
        # the same one the iter-17 stub used so anyone scripting against
        # ``ImportError`` doesn't see a regression.
        try:
            from jupyter_client.manager import KernelManager  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "LocalJupyterExecutor requires jupyter-client. "
                "Install it with: pip install jupyter-client"
            ) from exc

        explicit_code = kwargs.get("code")
        if isinstance(explicit_code, str) and explicit_code.strip():
            cells: list[str] = [explicit_code.strip()]
        else:
            cells = _extract_code_cells(methodology)

        if not cells:
            # Nothing executable supplied — return an empty-but-honest
            # result rather than spinning up a kernel for no work.
            return ExecutorResult(
                results="No executable code found in methodology.",
                plot_paths=[],
                artifacts={"cells_executed": 0},
            )

        kernel_name = kwargs.get("kernel_name") or "python3"
        execute_timeout = float(kwargs.get("execute_timeout") or 120.0)
        plots_dir = Path(project_dir) / "plots" / "local_jupyter"
        plots_dir.mkdir(parents=True, exist_ok=True)

        def _run_sync() -> tuple[list[str], list[str], list[dict[str, Any]]]:
            km = KernelManager(kernel_name=kernel_name)
            km.start_kernel()
            try:
                client = km.client()
                client.start_channels()
                try:
                    client.wait_for_ready(timeout=30)
                except Exception as exc:  # pragma: no cover — env-dep
                    raise RuntimeError(
                        f"jupyter kernel failed to become ready: {exc!r}"
                    ) from exc

                cell_outputs: list[str] = []
                plot_files: list[str] = []
                cell_records: list[dict[str, Any]] = []

                for idx, cell_src in enumerate(cells):
                    msg_id = client.execute(cell_src, allow_stdin=False)
                    cell_text_chunks: list[str] = []
                    cell_error: dict[str, Any] | None = None

                    while True:
                        try:
                            msg = client.get_iopub_msg(timeout=execute_timeout)
                        except Exception as exc:
                            cell_error = {
                                "ename": "JupyterTimeout",
                                "evalue": str(exc),
                                "traceback": [traceback.format_exc()],
                            }
                            break

                        if msg.get("parent_header", {}).get("msg_id") != msg_id:
                            continue
                        msg_type = msg.get("msg_type", "")
                        content = msg.get("content", {}) or {}

                        if msg_type == "stream":
                            text = content.get("text") or ""
                            if text:
                                cell_text_chunks.append(text)
                        elif msg_type in {"display_data", "execute_result"}:
                            data = content.get("data") or {}
                            txt = data.get("text/plain")
                            if isinstance(txt, str) and txt.strip():
                                cell_text_chunks.append(txt)
                            png = data.get("image/png")
                            if isinstance(png, str) and png:
                                fname = (
                                    f"cell{idx:02d}_"
                                    f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.png"
                                )
                                fpath = plots_dir / fname
                                try:
                                    fpath.write_bytes(base64.b64decode(png))
                                    plot_files.append(str(fpath))
                                except Exception:
                                    # Bad base64 — skip the figure rather
                                    # than abort the run.
                                    pass
                        elif msg_type == "error":
                            cell_error = {
                                "ename": content.get("ename") or "Error",
                                "evalue": content.get("evalue") or "",
                                "traceback": content.get("traceback") or [],
                            }
                        elif msg_type == "status" and content.get(
                            "execution_state"
                        ) == "idle":
                            # Kernel finished this cell. Done.
                            break

                    cell_text = "".join(cell_text_chunks).rstrip()
                    cell_outputs.append(cell_text)
                    cell_records.append(
                        {
                            "index": idx,
                            "source": cell_src,
                            "stdout": cell_text,
                            "error": cell_error,
                        }
                    )
                    if cell_error is not None:
                        # Stop on the first error — same semantics as
                        # ``jupyter nbconvert --execute --on-error=abort``.
                        break

                client.stop_channels()
                return cell_outputs, plot_files, cell_records
            finally:
                # Best-effort kernel shutdown. ``shutdown_kernel`` blocks
                # until the kernel exits or the timeout elapses; we keep
                # it short so the executor never hangs the caller.
                try:
                    km.shutdown_kernel(now=True, restart=False)
                except Exception:
                    pass

        cell_outputs, plot_files, cell_records = await asyncio.to_thread(_run_sync)

        # Build the markdown summary. Each cell becomes its own section so
        # the paper-drafting prompts can quote them individually.
        sections = ["# LocalJupyterExecutor results", ""]
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
                tb_text = _format_traceback(err)
                if tb_text:
                    sections.append("")
                    sections.append("```")
                    sections.append(tb_text)
                    sections.append("```")
            sections.append("")

        results_md = "\n".join(sections).rstrip() + "\n"
        any_error = any(r.get("error") for r in cell_records)

        return ExecutorResult(
            results=results_md,
            plot_paths=plot_files,
            artifacts={
                "cells_executed": len(cell_records),
                "cells_succeeded": sum(1 for r in cell_records if not r.get("error")),
                "had_error": any_error,
                "kernel_name": kernel_name,
                "cells": cell_records,
            },
            cost_usd=0.0,
            tokens_in=0,
            tokens_out=0,
        )


register_executor(LocalJupyterExecutor(), overwrite=True)
