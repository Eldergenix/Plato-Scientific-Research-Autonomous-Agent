"""Run TeX and pandoc on untrusted manuscript text with the sandbox's protections.

* Under root the tool runs as ``nobody`` (``setpriv``), so it cannot read the service's
  environment (API keys, database URL) through ``/proc``.
* The environment is scrubbed to PATH, HOME and locale.
* kpathsea runs in paranoid mode (``openin_any=p``, ``openout_any=p``): no absolute
  paths, no parent directories, no dot files.
* Without network (``unshare -n``) where the host allows it.
* rlimits (CPU, memory, file size, processes) and a wall-clock timeout that kills the
  whole process group.
"""

from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass
from pathlib import Path

from plato.scientist.guard.sandbox import (
    SandboxLimits,
    _apply_limits,
    network_isolation_prefix,
    privilege_drop_prefix,
)

_UID = 65534
TOOL_LIMITS = SandboxLimits(
    wall_seconds=90.0,
    cpu_seconds=90,
    memory_bytes=3 * 1024**3,
    max_file_bytes=256 * 1024**2,
    max_open_files=512,
    max_processes=1024,
)


class ToolError(RuntimeError):
    def __init__(self, message: str, output: str = "") -> None:
        super().__init__(message)
        self.output = output


@dataclass
class ToolResult:
    code: int
    output: str


def hand_to_sandbox_user(root: Path) -> None:
    """Give the work tree to ``nobody`` when tools will run as ``nobody``."""
    if not privilege_drop_prefix():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        os.chown(dirpath, _UID, _UID)
        for name in filenames:
            os.chown(os.path.join(dirpath, name), _UID, _UID)


async def run_tool(
    argv: list[str],
    cwd: Path,
    *,
    limits: SandboxLimits = TOOL_LIMITS,
    stdin: bytes | None = None,
    check: bool = True,
) -> ToolResult:
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(cwd),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "openin_any": "p",
        "openout_any": "p",
        "shell_escape": "f",
        "TEXMFVAR": str(cwd / ".texmf-var"),
        "TEXMFCONFIG": str(cwd / ".texmf-config"),
        "SOURCE_DATE_EPOCH": "1700000000",  # reproducible PDF timestamps and IDs
        "FORCE_SOURCE_DATE": "1",
    }
    # Namespace first (needs root), then drop to nobody inside it.
    prefix = [*network_isolation_prefix(), *privilege_drop_prefix()]
    proc = await asyncio.create_subprocess_exec(
        *prefix,
        *argv,
        cwd=str(cwd),
        env=env,
        stdin=asyncio.subprocess.PIPE
        if stdin is not None
        else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        preexec_fn=lambda: _apply_limits(limits),
    )
    try:
        out, _ = await asyncio.wait_for(
            proc.communicate(stdin), timeout=limits.wall_seconds
        )
    except TimeoutError:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await proc.wait()
        raise ToolError(
            f"{argv[0]} timed out after {limits.wall_seconds:.0f}s"
        ) from None
    text = out.decode("utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise ToolError(f"{argv[0]} exited with {proc.returncode}", text[-4000:])
    return ToolResult(proc.returncode or 0, text)
