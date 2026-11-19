"""Document compilation inside a sandbox (LaTeX to PDF, pandoc conversions).

``compile_document`` uploads a self-contained bundle (sources, figures, bibliography,
CSL), cuts the network off, runs one fixed toolchain command and returns the output
bytes plus the log. It needs a template with TeX Live, latexmk and pandoc (the
``plato-lab`` template built by ``scripts/e2b_lab_template.py``).

Untrusted manuscripts are safe to compile here: the sandbox is a disposable VM with no
secrets, ``\\write18`` shell escape stays disabled (TeX's default), pandoc arguments are
limited to an allow-list, and the network is denied before compilation starts.
"""

from __future__ import annotations

import re
import shlex
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

from .backend import SandboxBackend

Target = str  # "pdf" | "docx" | "html" | "odt" | "epub" | "jats"
_PANDOC_TARGETS = {
    "pdf": ("pdf", ["--pdf-engine=xelatex"]),
    "docx": ("docx", []),
    "html": ("html", ["--standalone", "--embed-resources"]),
    "odt": ("odt", []),
    "epub": ("epub", []),
    "jats": ("xml", ["--to=jats_archiving", "--standalone"]),
}
# Flags whose value (if any) must name a file inside the bundle.
_FILE_FLAGS = {"--csl", "--bibliography", "--reference-doc", "--resource-path"}
_PLAIN_FLAGS = {
    "--citeproc",
    "--standalone",
    "-s",
    "--toc",
    "--number-sections",
    "--mathml",
    "--embed-resources",
}
_VALUE_FLAGS = {
    "--metadata",
    "-M",
    "--from",
    "-f",
    "--shift-heading-level-by",
    "--toc-depth",
}
_SAFE_VALUE = re.compile(r"^[A-Za-z0-9 _.,:=+/-]{1,200}$")


class CompileError(ValueError):
    pass


@dataclass(frozen=True)
class CompileResult:
    ok: bool
    output_name: str
    output: bytes
    log: str
    duration_seconds: float
    network_isolated: bool


def _safe_name(name: str) -> str:
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or not p.parts or name.startswith("-"):
        raise CompileError(f"unsafe file name {name!r}")
    return str(p)


def check_pandoc_args(args: list[str]) -> list[str]:
    """Allow-list pandoc arguments (no filters, no Lua, no arbitrary output paths)."""
    out: list[str] = []
    it = iter(args)
    for arg in it:
        flag, eq, value = arg.partition("=")
        if flag in _PLAIN_FLAGS and not eq:
            out.append(arg)
        elif flag in _FILE_FLAGS:
            if not eq:
                value = next(it, "")
            out.append(f"{flag}={_safe_name(value)}")
        elif flag in _VALUE_FLAGS:
            if not eq:
                value = next(it, "")
            if not _SAFE_VALUE.match(value):
                raise CompileError(f"unsafe value for {flag}: {value!r}")
            out.append(f"{flag}={value}")
        else:
            raise CompileError(f"pandoc argument not allowed: {arg!r}")
    return out


def compile_command(
    main: str,
    target: Target,
    engine: str | None = None,
    pandoc_args: list[str] | None = None,
) -> tuple[str, str]:
    """Return (shell command, output file name) for compiling ``main`` to ``target``."""
    main = _safe_name(main)
    stem = str(PurePosixPath(main).with_suffix(""))
    is_tex = main.endswith(".tex")
    engine = engine or ("latexmk" if is_tex and target == "pdf" else "pandoc")
    q = shlex.quote(main)
    if engine in ("latexmk", "xelatex"):
        if target != "pdf" or not is_tex:
            raise CompileError(f"{engine} compiles .tex to pdf only")
        mode = "-pdf" if engine == "latexmk" else "-xelatex"
        # -no-shell-escape keeps \write18 off even if a texmf.cnf enables it.
        cmd = (
            f"latexmk {mode} -interaction=nonstopmode -halt-on-error -file-line-error "
            f"-no-shell-escape {q} > compile.log 2>&1; rc=$?; tail -c 4000 compile.log; exit $rc"
        )
        return cmd, f"{stem}.pdf"
    if engine != "pandoc":
        raise CompileError(f"unknown engine {engine!r}")
    if target not in _PANDOC_TARGETS:
        raise CompileError(f"unknown target {target!r}")
    ext, fixed = _PANDOC_TARGETS[target]
    output = f"{stem}.{ext}"
    extra = check_pandoc_args(pandoc_args or [])
    args = " ".join(shlex.quote(a) for a in [*fixed, *extra])
    cmd = (
        f"pandoc {q} {args} -o {shlex.quote(output)} > compile.log 2>&1; rc=$?; "
        "tail -c 4000 compile.log; exit $rc"
    )
    return cmd, output


BackendFactory = Callable[..., Awaitable[SandboxBackend]]


async def compile_document(
    files: dict[str, bytes],
    *,
    main: str,
    target: Target = "pdf",
    engine: str | None = None,
    pandoc_args: list[str] | None = None,
    backend_factory: BackendFactory | None = None,
    timeout_seconds: int = 600,
) -> CompileResult:
    """Compile a bundle in a fresh sandbox; never raises for a failed compile."""
    if main not in files:
        raise CompileError(f"main file {main!r} is not in the bundle")
    cmd, output_name = compile_command(main, target, engine, pandoc_args)
    if backend_factory is None:
        from .runtime import default_backend_factory

        backend_factory = default_backend_factory()
    backend = await backend_factory(
        timeout_seconds=timeout_seconds + 120, purpose="compile"
    )
    started = time.monotonic()
    try:
        for name, data in files.items():
            await backend.write_bytes(_safe_name(name), data)
        isolated = await backend.set_network(False)
        outcome = await backend.run(cmd, timeout=timeout_seconds)
        log = outcome.stdout + outcome.stderr
        output = b""
        if outcome.ok:
            try:
                output = await backend.read_bytes(output_name)
            except Exception as exc:  # noqa: BLE001 - a missing output is reported
                log += f"\noutput {output_name} missing: {exc}"
        return CompileResult(
            ok=outcome.ok and bool(output),
            output_name=output_name,
            output=output,
            log=log,
            duration_seconds=time.monotonic() - started,
            network_isolated=isolated,
        )
    finally:
        await backend.close()
