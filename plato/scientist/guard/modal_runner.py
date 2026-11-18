"""Run one experiment script in a Modal Labs sandbox (optionally on a GPU).

Same contract as :func:`plato.scientist.guard.sandbox.run_python`: the script and its
input files are staged in a fresh working directory, run with a fixed argv and a
scrubbed environment, and every PNG/JSON/CSV/TXT/TeX file it writes (up to 1 MiB) comes
back. Isolation comes from Modal: each run gets its own gVisor container with outbound
network blocked (``block_network=True``), destroyed afterwards.

Credentials are read by the Modal SDK from ``MODAL_TOKEN_ID`` / ``MODAL_TOKEN_SECRET``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from .sandbox import (
    _COLLECT_MAX_BYTES,
    _COLLECT_SUFFIXES,
    SandboxLimits,
    SandboxResult,
    _clip,
    static_check,
)

logger = logging.getLogger(__name__)

APP_NAME = os.environ.get("PLATO_MODAL_APP", "plato-scientist-experiments")
WORKDIR = "/work"
_SCRIPT = "experiment.py"
# The experiment image mirrors the container's scientific stack (same pins), plus torch
# on GPU machines. Modal caches images by definition, so this builds once.
PACKAGES = (
    "numpy==2.5.5",
    "scipy==1.18.1",
    "pandas==3.1.1",
    "scikit-learn==1.9.1",
    "matplotlib==3.11.2",
    "statsmodels==0.15.0",
    "biopython==1.88",
    "astropy==8.0.3",
)
GPU_PACKAGES = ("torch",)
GPU_TYPES = frozenset({"T4", "L4", "A10G", "L40S", "A100", "A100-80GB", "H100"})


def modal_configured() -> bool:
    return bool(
        os.environ.get("MODAL_TOKEN_ID") and os.environ.get("MODAL_TOKEN_SECRET")
    )


def _image(modal: Any, gpu: str):
    image = modal.Image.debian_slim(python_version="3.13").pip_install(*PACKAGES)
    if gpu:
        image = image.pip_install(*GPU_PACKAGES)
    return image.env({"MPLBACKEND": "Agg"})


async def run_python_modal(
    code: str,
    *,
    inputs: dict[str, bytes] | None = None,
    limits: SandboxLimits | None = None,
    gpu: str = "",
) -> SandboxResult:
    limits = limits or SandboxLimits()
    rejection = static_check(code)
    if rejection:
        return SandboxResult.reject(rejection)
    if gpu and gpu not in GPU_TYPES:
        return SandboxResult.reject(f"unknown GPU type {gpu!r}")
    if not modal_configured():
        return SandboxResult.reject("Modal credentials are not configured")
    inputs = inputs or {}
    for name in inputs:
        if os.path.basename(name) != name or not name or name.startswith("."):
            return SandboxResult.reject(f"invalid input file name {name!r}")

    import modal  # imported lazily: the SDK is only needed when Modal is selected

    app = await modal.App.lookup.aio(APP_NAME, create_if_missing=True)
    wall = int(limits.wall_seconds)
    sb = await modal.Sandbox.create.aio(
        app=app,
        image=_image(modal, gpu),
        gpu=gpu or None,
        cpu=2.0,
        memory=max(512, limits.memory_bytes // 1024**2),
        timeout=wall + 120,  # sandbox lifetime: staging + run + collection
        block_network=True,
        workdir=WORKDIR,
    )
    try:
        for name, data in inputs.items():
            await sb.filesystem.write_bytes.aio(data, f"{WORKDIR}/{name}")
        await sb.filesystem.write_text.aio(code, f"{WORKDIR}/{_SCRIPT}")
        env = {
            "HOME": WORKDIR,
            "TMPDIR": WORKDIR,
            "MPLBACKEND": "Agg",
            "MPLCONFIGDIR": f"{WORKDIR}/.mpl",
            "PYTHONHASHSEED": "0",
            "LANG": "C.UTF-8",
        }
        started = time.monotonic()
        proc = await sb.exec.aio(
            "python",
            "-I",
            "-B",
            f"{WORKDIR}/{_SCRIPT}",
            workdir=WORKDIR,
            env=env,
            timeout=wall,
            text=False,
        )
        timed_out = False
        try:
            out, err = await asyncio.wait_for(
                asyncio.gather(proc.stdout.read.aio(), proc.stderr.read.aio()),
                timeout=wall + 15,
            )
            exit_code = await proc.wait.aio()
        except TimeoutError:
            timed_out, out, err, exit_code = True, b"", b"", None
        duration = time.monotonic() - started
        if duration >= wall:
            timed_out = True

        files: dict[str, bytes] = {}
        for entry in await sb.filesystem.list_files.aio(WORKDIR):
            if (
                entry.is_file()
                and entry.name != _SCRIPT
                and entry.name not in inputs
                and os.path.splitext(entry.name)[1] in _COLLECT_SUFFIXES
                and entry.size <= _COLLECT_MAX_BYTES
            ):
                files[entry.name] = await sb.filesystem.read_bytes.aio(
                    f"{WORKDIR}/{entry.name}"
                )
        return SandboxResult(
            exit_code=exit_code,
            stdout=_clip(
                out if isinstance(out, bytes) else out.encode(), limits.max_output_chars
            ),
            stderr=_clip(
                err if isinstance(err, bytes) else err.encode(), limits.max_output_chars
            ),
            duration_seconds=duration,
            timed_out=timed_out,
            network_isolated=True,
            files=files,
        )
    finally:
        try:
            await sb.terminate.aio()
        except Exception:
            logger.warning("could not terminate Modal sandbox", exc_info=True)
