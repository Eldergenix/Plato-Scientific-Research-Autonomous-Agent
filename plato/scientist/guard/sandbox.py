"""Isolated execution of model-written experiment code.

Layers (outermost first):

1. **Container boundary.** In production every run happens inside a Cloudflare
   Container (its own VM), so a breakout reaches only a disposable instance.
2. **Network namespace.** When ``unshare`` works, the experiment gets an empty
   network namespace (no interfaces besides loopback), so it cannot exfiltrate
   data or fetch held-out test sets. Availability is probed once and reported.
3. **Privilege drop.** Under root, the experiment runs as ``nobody`` via ``setpriv``.
4. **Fixed argv.** Only ``<python> -I -B <script>`` is executed, never a shell.
5. **Scrubbed environment.** The child gets a minimal env: no API keys, no DB URL.
6. **rlimits.** CPU seconds, address space, file size, open files, process count.
7. **Wall-clock timeout** with process-group kill.
8. **Data minimisation.** Only files the caller materialises into the work dir
   are visible; sealed-eval assets are never materialised before the sealed phase.
"""

from __future__ import annotations

import ast
import asyncio
import functools
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

# Modules whose import is refused by the static pre-check. This is a cheap first filter that
# catches the common case and produces a useful error for the model; the namespace, env and
# rlimit layers are what actually contain hostile code.
_BLOCKED_IMPORTS = frozenset(
    {
        "socket",
        "subprocess",
        "ctypes",
        "multiprocessing",
        "requests",
        "httpx",
        "urllib",
        "http",
        "ftplib",
        "smtplib",
        "telnetlib",
        "pty",
        "asyncio.subprocess",
    }
)
_BLOCKED_CALLS = frozenset(
    {"system", "popen", "execv", "execve", "execvp", "fork", "spawnv", "__import__"}
)


@dataclass(frozen=True)
class SandboxLimits:
    wall_seconds: float = 120.0
    cpu_seconds: int = 120
    memory_bytes: int = 2 * 1024**3
    max_file_bytes: int = 64 * 1024**2
    max_open_files: int = 256
    # RLIMIT_NPROC counts every thread of the uid, so keep headroom for BLAS thread pools.
    max_processes: int = 1024
    max_output_chars: int = 200_000


DEFAULT_LIMITS = SandboxLimits()


@dataclass
class SandboxResult:
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    network_isolated: bool
    files: dict[str, bytes] = field(default_factory=dict)
    rejected: str | None = None

    @classmethod
    def reject(cls, reason: str) -> SandboxResult:
        return cls(None, "", "", 0.0, False, False, rejected=reason)

    @property
    def ok(self) -> bool:
        return self.rejected is None and not self.timed_out and self.exit_code == 0


def static_check(code: str) -> str | None:
    """Return a rejection reason, or None if the code passes the pre-check."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"syntax error: {exc.msg} (line {exc.lineno})"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if (
                    alias.name.split(".")[0] in _BLOCKED_IMPORTS
                    or alias.name in _BLOCKED_IMPORTS
                ):
                    return f"import of {alias.name!r} is not allowed in experiments"
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.split(".")[0] in _BLOCKED_IMPORTS or mod in _BLOCKED_IMPORTS:
                return f"import from {mod!r} is not allowed in experiments"
        elif isinstance(node, ast.Call):
            fn = node.func
            name = (
                fn.attr
                if isinstance(fn, ast.Attribute)
                else fn.id
                if isinstance(fn, ast.Name)
                else None
            )
            if name in _BLOCKED_CALLS:
                return f"call to {name}() is not allowed in experiments"
    return None


@functools.lru_cache(maxsize=1)
def network_isolation_prefix() -> tuple[str, ...]:
    """Probe for a working ``unshare`` network namespace. Returns the argv prefix to
    use, or ``()`` when isolation is unavailable on this host."""
    exe = shutil.which("unshare")
    if not exe:
        return ()
    for prefix in ((exe, "-n"), (exe, "-r", "-n")):
        try:
            done = subprocess.run(
                [*prefix, "true"], capture_output=True, timeout=5, check=False
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if done.returncode == 0:
            return prefix
    return ()


_UNPRIVILEGED_UID = 65534  # "nobody"


@functools.lru_cache(maxsize=1)
def privilege_drop_prefix() -> tuple[str, ...]:
    """When the service runs as root (as in the container image), run experiments as
    ``nobody`` so they cannot read the service's ``/proc/<pid>/environ`` (API keys,
    database URL) or write outside their work directory."""
    exe = shutil.which("setpriv")
    if os.geteuid() != 0 or not exe:
        return ()
    return (
        exe,
        f"--reuid={_UNPRIVILEGED_UID}",
        f"--regid={_UNPRIVILEGED_UID}",
        "--clear-groups",
        "--",
    )


def _apply_limits(limits: SandboxLimits) -> None:  # runs in the child before exec
    os.setsid()
    resource.setrlimit(
        resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds + 5)
    )
    try:
        resource.setrlimit(
            resource.RLIMIT_AS, (limits.memory_bytes, limits.memory_bytes)
        )
    except ValueError:
        # macOS refuses RLIMIT_AS below its (unlimited-looking) hard limit; development
        # Macs only. Linux, where the service runs, always takes this limit.
        if sys.platform != "darwin":
            raise
    resource.setrlimit(
        resource.RLIMIT_FSIZE, (limits.max_file_bytes, limits.max_file_bytes)
    )
    resource.setrlimit(
        resource.RLIMIT_NOFILE, (limits.max_open_files, limits.max_open_files)
    )
    resource.setrlimit(
        resource.RLIMIT_NPROC, (limits.max_processes, limits.max_processes)
    )
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _clip(text: bytes, limit: int) -> str:
    decoded = text.decode("utf-8", errors="replace")
    if len(decoded) <= limit:
        return decoded
    half = limit // 2
    return f"{decoded[:half]}\n...[{len(decoded) - limit} chars elided]...\n{decoded[-half:]}"


# Output files an experiment leaves in its working directory that are kept: figures,
# tables, molecular structures (proteins as PDB/mmCIF, small molecules as SDF/MOL/MOL2/XYZ),
# networks and pathways (SIF, GraphML) and documents. Every executor collects the same set.
_COLLECT_SUFFIXES = (
    ".png",
    ".json",
    ".csv",
    ".tsv",
    ".txt",
    ".tex",
    ".pdf",
    ".pdb",
    ".cif",
    ".mmcif",
    ".sdf",
    ".mol",
    ".mol2",
    ".xyz",
    ".sif",
    ".graphml",
)
_COLLECT_MAX_BYTES = 1_048_576


_SCRIPT = "experiment.py"


def _stage(code: str, inputs: dict[str, bytes], chown: bool) -> Path:
    workdir = Path(tempfile.mkdtemp(prefix="plato-exp-"))
    try:
        for name, data in inputs.items():
            safe = Path(name).name  # inputs are flat; no path components accepted
            if not safe or safe.startswith("."):
                raise ValueError(f"invalid input file name {name!r}")
            (workdir / safe).write_bytes(data)
        (workdir / _SCRIPT).write_text(code, encoding="utf-8")
        if chown:
            for path in (workdir, *workdir.iterdir()):
                os.chown(path, _UNPRIVILEGED_UID, _UNPRIVILEGED_UID)
    except BaseException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    return workdir


def _collect(workdir: Path, input_names: set[str]) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in sorted(workdir.iterdir()):
        if (
            path.is_file()
            and not path.is_symlink()
            and path.name != _SCRIPT
            and path.suffix.lower() in _COLLECT_SUFFIXES
            and path.name not in input_names
            and path.stat().st_size <= _COLLECT_MAX_BYTES
        ):
            files[path.name] = path.read_bytes()
    return files


async def run_python(
    code: str,
    *,
    inputs: dict[str, bytes] | None = None,
    limits: SandboxLimits = DEFAULT_LIMITS,
    python_executable: str | None = None,
    require_network_isolation: bool = False,
) -> SandboxResult:
    """Run ``code`` as a script in a fresh temporary directory and collect its outputs."""
    rejection = static_check(code)
    if rejection:
        return SandboxResult.reject(rejection)

    python = python_executable or sys.executable
    iso = network_isolation_prefix()
    if require_network_isolation and not iso:
        return SandboxResult.reject(
            "network isolation required but unavailable on this host"
        )

    drop = privilege_drop_prefix()
    # Filesystem work runs off the event loop so concurrent workers keep heartbeating.
    workdir = await asyncio.to_thread(_stage, code, inputs or {}, bool(drop))
    try:
        # Fixed argv: interpreter in isolated mode (-I: no env vars, no user site, no cwd on
        # sys.path), no bytecode writes (-B). The model only ever controls the script body.
        argv = (python, "-I", "-B", str(workdir / _SCRIPT))
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(workdir),
            "TMPDIR": str(workdir),
            "MPLBACKEND": "Agg",
            "MPLCONFIGDIR": str(workdir / ".mpl"),
            "PYTHONHASHSEED": "0",
            "OMP_NUM_THREADS": "2",
            "OPENBLAS_NUM_THREADS": "2",
            "LANG": "C.UTF-8",
        }
        started = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *iso,
            *drop,
            *argv,
            cwd=workdir,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=functools.partial(_apply_limits, limits),
        )
        timed_out = False
        try:
            out, err = await asyncio.wait_for(
                proc.communicate(), timeout=limits.wall_seconds
            )
        except TimeoutError:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            out, err = await proc.communicate()
        duration = time.monotonic() - started

        files = await asyncio.to_thread(_collect, workdir, set(inputs or {}))
        return SandboxResult(
            exit_code=proc.returncode,
            stdout=_clip(out, limits.max_output_chars),
            stderr=_clip(err, limits.max_output_chars),
            duration_seconds=duration,
            timed_out=timed_out,
            network_isolated=bool(iso),
            files=files,
        )
    finally:
        await asyncio.to_thread(shutil.rmtree, workdir, ignore_errors=True)
