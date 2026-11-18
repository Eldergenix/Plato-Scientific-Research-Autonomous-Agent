"""The agent's tool surface inside a sandbox workspace.

The research-engineer agent drives a disposable Linux machine through these tools:
shell commands, file system navigation, search, reads and edits, package installs
(pip, conda/bioconda, apt, R/Bioconductor), public dataset downloads with checksums,
background jobs for long runs, document compilation, and finally
``submit_experiment``, which re-runs the work from scratch for the record.

Reproducibility is built in: every successful install and download is appended to a
setup recipe (``setup.sh``) that pins what was fetched (the sha256 of each download is
re-checked on replay), so replication and sealed evaluation rebuild the same
environment in a fresh sandbox.

Tool results are program output, i.e. untrusted data: the caller frames them before
they reach the model.
"""

from __future__ import annotations

import json
import re
import shlex
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .backend import CommandOutcome, SandboxBackend

MAX_TOOL_OUTPUT_CHARS = 12_000
MAX_COMMAND_SECONDS = 1_800
DEFAULT_COMMAND_SECONDS = 120
MAX_WAIT_SECONDS = 600
DEFAULT_MAX_DOWNLOAD_BYTES = 8 * 1024**3
SETUP_SCRIPT = "setup.sh"
JOBS_DIR = ".jobs"

_PKG_PATTERNS = {
    "pip": re.compile(
        r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9,._-]+\])?((==|>=|<=|~=|!=|>|<)[A-Za-z0-9.*+!_-]+)?$"
    ),
    "conda": re.compile(r"^([a-z0-9_-]+::)?[A-Za-z0-9][A-Za-z0-9._-]*((==|=|>=|<=)[A-Za-z0-9.*_-]+)?$"),
    "apt": re.compile(r"^[a-z0-9][a-z0-9.+-]*(=[A-Za-z0-9.+:~-]+)?$"),
    "r": re.compile(r"^[A-Za-z][A-Za-z0-9.]*$"),
}
_JOB_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_URL = re.compile(r"^https?://[^\s'\"`$\\]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def clip(text: str, limit: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    """Keep the head and (longer) tail: errors and summaries are usually at the end."""
    if len(text) <= limit:
        return text
    head = limit // 3
    tail = limit - head
    return f"{text[:head]}\n...[{len(text) - limit} chars elided]...\n{text[-tail:]}"


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


_STR = {"type": "string"}
_INT = {"type": "integer"}

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "bash",
        "description": (
            "Run a bash command in the workspace (login shell, working directory is the "
            "workspace root unless cwd is given). Use it for anything the other tools do not "
            "cover: running tools such as samtools or plink2, python scripts, pipes, "
            f"inspecting outputs. Hard limit timeout_seconds (default {DEFAULT_COMMAND_SECONDS}, "
            f"max {MAX_COMMAND_SECONDS}); for longer work use start_job. Returns exit code, "
            "stdout and stderr (long output is clipped in the middle)."
        ),
        "input_schema": _schema(
            {"command": _STR, "timeout_seconds": _INT, "cwd": _STR}, ["command"]
        ),
    },
    {
        "name": "list_files",
        "description": "List files and directories under a path with type and size, up to a depth (default 2).",
        "input_schema": _schema({"path": _STR, "depth": _INT}, ["path"]),
    },
    {
        "name": "read_file",
        "description": (
            "Read a text file, optionally a line range (start_line is 1-based; default the first "
            "400 lines). Binary files are reported, not dumped; use bash (head, zcat, samtools "
            "view) for those."
        ),
        "input_schema": _schema(
            {"path": _STR, "start_line": _INT, "max_lines": _INT}, ["path"]
        ),
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a text file (parent directories are created).",
        "input_schema": _schema({"path": _STR, "content": _STR}, ["path", "content"]),
    },
    {
        "name": "edit_file",
        "description": "Replace one exact, unique occurrence of old_text with new_text in a file.",
        "input_schema": _schema(
            {"path": _STR, "old_text": _STR, "new_text": _STR},
            ["path", "old_text", "new_text"],
        ),
    },
    {
        "name": "search_files",
        "description": (
            "Search file contents (ripgrep, regex) under path, optionally only files matching a "
            "glob such as '*.py'. With names_only=true, find files whose names match the glob "
            "instead and ignore pattern."
        ),
        "input_schema": _schema(
            {"pattern": _STR, "path": _STR, "glob": _STR, "names_only": {"type": "boolean"}},
            ["pattern"],
        ),
    },
    {
        "name": "install_packages",
        "description": (
            "Install packages and record them in setup.sh for replication. manager: 'conda' "
            "(conda-forge + bioconda; preferred for bioinformatics tools), 'pip', 'apt', or 'r' "
            "(Bioconductor/CRAN via BiocManager). Pin versions where it matters, e.g. "
            "'samtools=1.21' or 'scanpy==1.10.4'."
        ),
        "input_schema": _schema(
            {
                "manager": {"type": "string", "enum": ["conda", "pip", "apt", "r"]},
                "packages": {"type": "array", "items": _STR},
            },
            ["manager", "packages"],
        ),
    },
    {
        "name": "download_file",
        "description": (
            "Download a public file over HTTP(S) into the workspace and record it (URL and sha256) "
            "in setup.sh, so replication re-downloads and verifies the same bytes. Give sha256 when "
            "the source publishes one. extract=true unpacks .tar(.gz/.bz2/.xz), .zip or .gz next to "
            "the file."
        ),
        "input_schema": _schema(
            {"url": _STR, "dest": _STR, "sha256": _STR, "extract": {"type": "boolean"}},
            ["url", "dest"],
        ),
    },
    {
        "name": "start_job",
        "description": (
            "Start a long-running command in the background (alignment, variant calling, model "
            "training). Output goes to a log; check it with job_status or wait_job."
        ),
        "input_schema": _schema({"name": _STR, "command": _STR}, ["name", "command"]),
    },
    {
        "name": "job_status",
        "description": "State of a background job (running, exited with code, or lost) and the tail of its log.",
        "input_schema": _schema({"name": _STR, "tail_lines": _INT}, ["name"]),
    },
    {
        "name": "wait_job",
        "description": (
            f"Block until a background job finishes or max_wait_seconds pass (max {MAX_WAIT_SECONDS}), "
            "then report like job_status. Cheaper than polling."
        ),
        "input_schema": _schema({"name": _STR, "max_wait_seconds": _INT}, ["name"]),
    },
    {
        "name": "stop_job",
        "description": "Kill a background job and its child processes.",
        "input_schema": _schema({"name": _STR}, ["name"]),
    },
    {
        "name": "compile_document",
        "description": (
            "Compile a document in the workspace. engine 'latexmk' (pdflatex) or 'xelatex' for "
            ".tex to PDF; 'pandoc' converts Markdown/LaTeX to target docx, html, odt, epub, jats "
            "or pdf. Returns the output path and the end of the log."
        ),
        "input_schema": _schema(
            {
                "main": _STR,
                "target": {
                    "type": "string",
                    "enum": ["pdf", "docx", "html", "odt", "epub", "jats"],
                },
                "engine": {"type": "string", "enum": ["latexmk", "xelatex", "pandoc"]},
            },
            ["main", "target"],
        ),
    },
    {
        "name": "submit_experiment",
        "description": (
            "Submit the experiment for the record. It runs in a FRESH sandbox: first "
            "setup_path (default: the recorded setup.sh) with internet access, then "
            "experiment_path with python and the network cut off. Datasets and the seed file are "
            "provided again. The run must print the PLATO_METRICS line. Returns the outcome; on "
            "failure fix the problem and submit again."
        ),
        "input_schema": _schema(
            {"experiment_path": _STR, "setup_path": _STR}, ["experiment_path"]
        ),
    },
]

TOOL_NAMES = frozenset(t["name"] for t in TOOL_SPECS)


@dataclass
class ToolResult:
    text: str
    is_error: bool = False
    submitted: Any = None  # set when submit_experiment succeeded


SubmitHandler = Callable[[str, str], Awaitable[tuple[str, bool, Any]]]
"""(experiment_code, setup_script) -> (report text, accepted, payload)."""


def _fmt(outcome: CommandOutcome) -> str:
    status = "TIMED OUT" if outcome.timed_out else f"exit code {outcome.exit_code}"
    parts = [f"[{status}, {outcome.duration_seconds:.1f}s]"]
    if outcome.stdout:
        parts.append(f"stdout:\n{outcome.stdout}")
    if outcome.stderr:
        parts.append(f"stderr:\n{outcome.stderr}")
    return clip("\n".join(parts))


@dataclass
class Workspace:
    """Tool dispatcher bound to one sandbox backend."""

    backend: SandboxBackend
    on_submit: SubmitHandler | None = None
    max_download_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES
    setup_lines: list[str] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    # Set by the submit handler when no further submissions will be accepted.
    exhausted: bool = False

    # -- recipe ----------------------------------------------------------------------

    def setup_script(self) -> str:
        body = "\n".join(self.setup_lines)
        return (
            "#!/usr/bin/env bash\n"
            "# Environment recipe recorded by the Plato workspace; replayed before each run.\n"
            "set -euo pipefail\n" + (f"{body}\n" if body else "")
        )

    async def _record_setup(self, line: str) -> None:
        self.setup_lines.append(line)
        await self.backend.write_bytes(SETUP_SCRIPT, self.setup_script().encode())

    # -- dispatch --------------------------------------------------------------------

    async def call(self, name: str, args: dict[str, Any]) -> ToolResult:
        started = time.monotonic()
        handler = getattr(self, f"_t_{name}", None)
        if name not in TOOL_NAMES or handler is None:
            return ToolResult(f"unknown tool {name!r}", is_error=True)
        try:
            result = await handler(**args)
        except TypeError as exc:
            result = ToolResult(f"bad arguments for {name}: {exc}", is_error=True)
        except Exception as exc:  # sandbox transport errors surface to the model as errors
            result = ToolResult(f"{type(exc).__name__}: {exc}", is_error=True)
        self.actions.append(
            {
                "tool": name,
                "args": {k: (v if len(str(v)) <= 300 else f"{str(v)[:300]}…") for k, v in args.items()},
                "is_error": result.is_error,
                "seconds": round(time.monotonic() - started, 2),
            }
        )
        return result

    # -- tools -----------------------------------------------------------------------

    async def _t_bash(
        self, command: str, timeout_seconds: int | None = None, cwd: str | None = None
    ) -> ToolResult:
        seconds = min(max(1, timeout_seconds or DEFAULT_COMMAND_SECONDS), MAX_COMMAND_SECONDS)
        outcome = await self.backend.run(command, cwd=cwd, timeout=seconds)
        return ToolResult(_fmt(outcome))

    async def _t_list_files(self, path: str, depth: int | None = None) -> ToolResult:
        d = min(max(1, depth or 2), 6)
        cmd = (
            f"find {shlex.quote(path)} -mindepth 1 -maxdepth {d} -not -path '*/.git/*' "
            "-printf '%y %10s %p\\n' 2>&1 | sort -k3 | head -n 500"
        )
        outcome = await self.backend.run(cmd, timeout=60)
        if not outcome.ok:
            return ToolResult(_fmt(outcome), is_error=True)
        return ToolResult(clip(outcome.stdout or "(empty)"))

    async def _t_read_file(
        self, path: str, start_line: int | None = None, max_lines: int | None = None
    ) -> ToolResult:
        start = max(1, start_line or 1)
        count = min(max(1, max_lines or 400), 2_000)
        q = shlex.quote(path)
        cmd = (
            f"if [ ! -f {q} ]; then echo 'not a file: '{q} >&2; exit 2; fi; "
            f"if grep -Iq . {q} 2>/dev/null || [ ! -s {q} ]; then "
            f"total=$(wc -l < {q}); echo \"# lines $(({start})) to $(({start}+{count}-1)) of $total\"; "
            f"tail -n +{start} {q} | head -n {count}; "
            f"else echo \"binary file ($(stat -c %s {q}) bytes): $(file -b {q} 2>/dev/null)\"; fi"
        )
        outcome = await self.backend.run(cmd, timeout=60)
        if not outcome.ok:
            return ToolResult(_fmt(outcome), is_error=True)
        return ToolResult(clip(outcome.stdout))

    async def _t_write_file(self, path: str, content: str) -> ToolResult:
        await self.backend.write_bytes(path, content.encode("utf-8"))
        return ToolResult(f"wrote {len(content.encode('utf-8'))} bytes to {path}")

    async def _t_edit_file(self, path: str, old_text: str, new_text: str) -> ToolResult:
        text = (await self.backend.read_bytes(path)).decode("utf-8")
        count = text.count(old_text)
        if count != 1:
            return ToolResult(
                f"old_text occurs {count} times in {path}; it must occur exactly once",
                is_error=True,
            )
        await self.backend.write_bytes(path, text.replace(old_text, new_text).encode("utf-8"))
        return ToolResult(f"edited {path}")

    async def _t_search_files(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        names_only: bool | None = None,
    ) -> ToolResult:
        root = shlex.quote(path or ".")
        if names_only:
            name = shlex.quote(glob or pattern)
            cmd = f"find {root} -name {name} -not -path '*/.git/*' 2>/dev/null | head -n 300"
        else:
            g = f"--glob {shlex.quote(glob)} " if glob else ""
            gg = f"--include={shlex.quote(glob)} " if glob else ""
            p = shlex.quote(pattern)
            cmd = (
                f"if command -v rg >/dev/null; then rg -n --no-heading --max-count 50 "
                f"--max-columns 300 {g}-e {p} {root}; else grep -rnE {gg}-e {p} {root}; fi "
                "| head -n 300"
            )
        outcome = await self.backend.run(cmd, timeout=120)
        return ToolResult(clip(outcome.stdout or "(no matches)"))

    async def _t_install_packages(self, manager: str, packages: list[str]) -> ToolResult:
        pattern = _PKG_PATTERNS.get(manager)
        if pattern is None:
            return ToolResult(f"unknown manager {manager!r}", is_error=True)
        bad = [p for p in packages if not pattern.match(p)]
        if bad or not packages:
            return ToolResult(f"invalid package names for {manager}: {bad or packages}", is_error=True)
        pk = " ".join(shlex.quote(p) for p in packages)
        if manager == "pip":
            cmd = f"python -m pip install --no-input --progress-bar off -q {pk}"
        elif manager == "conda":
            cmd = (
                "micromamba install -y -q -n base -c conda-forge -c bioconda "
                f"--channel-priority strict {pk}"
            )
        elif manager == "apt":
            cmd = (
                "sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq && "
                f"sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends {pk}"
            )
        else:
            vec = ", ".join(json.dumps(p) for p in packages)
            r = (
                "if (!requireNamespace('BiocManager', quietly=TRUE)) "
                "install.packages('BiocManager', repos='https://cloud.r-project.org'); "
                f"BiocManager::install(c({vec}), ask=FALSE, update=FALSE); "
                f"stopifnot(all(sapply(c({vec}), requireNamespace, quietly=TRUE)))"
            )
            cmd = f"Rscript -e {shlex.quote(r)}"
        outcome = await self.backend.run(cmd, timeout=MAX_COMMAND_SECONDS)
        if outcome.ok:
            await self._record_setup(cmd)
        return ToolResult(_fmt(outcome), is_error=not outcome.ok)

    async def _t_download_file(
        self, url: str, dest: str, sha256: str | None = None, extract: bool | None = None
    ) -> ToolResult:
        if not _URL.match(url):
            return ToolResult("url must be a plain http(s) URL", is_error=True)
        if sha256 is not None and not _SHA256.match(sha256.lower()):
            return ToolResult("sha256 must be 64 hex characters", is_error=True)
        if dest.startswith("/") or ".." in dest.split("/"):
            return ToolResult("dest must be a relative path inside the workspace", is_error=True)
        q_dest, q_url = shlex.quote(dest), shlex.quote(url)
        fetch = (
            f"mkdir -p \"$(dirname {q_dest})\" && curl -fsSL --retry 3 --retry-delay 2 "
            f"--connect-timeout 30 --max-filesize {self.max_download_bytes} -o {q_dest} {q_url}"
        )
        outcome = await self.backend.run(f"{fetch} && sha256sum {q_dest}", timeout=MAX_COMMAND_SECONDS)
        if not outcome.ok:
            return ToolResult(_fmt(outcome), is_error=True)
        digest = outcome.stdout.split()[0] if outcome.stdout.split() else ""
        if sha256 and digest != sha256.lower():
            await self.backend.run(f"rm -f {q_dest}", timeout=30)
            return ToolResult(
                f"checksum mismatch for {url}: expected {sha256.lower()}, got {digest}; file removed",
                is_error=True,
            )
        verify = f"echo {shlex.quote(f'{digest}  {dest}')} | sha256sum -c --quiet"
        steps = [fetch, verify]
        report = [f"downloaded {url} -> {dest}", f"sha256 {digest}"]
        if extract:
            unpack = _extract_command(dest)
            if unpack is None:
                return ToolResult("\n".join(report) + "\ncannot extract: unknown archive type", is_error=True)
            ex = await self.backend.run(unpack, timeout=MAX_COMMAND_SECONDS)
            if not ex.ok:
                return ToolResult("\n".join(report) + "\n" + _fmt(ex), is_error=True)
            steps.append(unpack)
            report.append("extracted")
        size = await self.backend.run(f"stat -c %s {q_dest} 2>/dev/null || echo 0", timeout=30)
        report.append(f"bytes {size.stdout.strip()}")
        await self._record_setup(" && ".join(steps))
        return ToolResult("\n".join(report))

    async def _t_start_job(self, name: str, command: str) -> ToolResult:
        if not _JOB_NAME.match(name):
            return ToolResult("job name: letters, digits, '_' or '-', at most 64", is_error=True)
        base = f"{JOBS_DIR}/{name}"
        exists = await self.backend.run(f"test -e {base}.pid", timeout=30)
        if exists.ok:
            return ToolResult(f"job {name!r} already exists; pick another name", is_error=True)
        await self.backend.write_bytes(f"{base}.sh", command.encode("utf-8"))
        # setsid detaches the job from the tool call's process group so it outlives it.
        launch = (
            f"setsid nohup bash -c 'bash -l {base}.sh > {base}.log 2>&1; echo $? > {base}.exit' "
            f">/dev/null 2>&1 < /dev/null & echo $! > {base}.pid; date +%s > {base}.start; "
            f"cat {base}.pid"
        )
        outcome = await self.backend.run(launch, timeout=30)
        if not outcome.ok:
            return ToolResult(_fmt(outcome), is_error=True)
        return ToolResult(f"started job {name} (pid {outcome.stdout.strip()}); log at {base}.log")

    async def _job_report(self, name: str, tail_lines: int = 40) -> ToolResult:
        if not _JOB_NAME.match(name):
            return ToolResult("invalid job name", is_error=True)
        base = f"{JOBS_DIR}/{name}"
        n = min(max(1, tail_lines), 400)
        cmd = (
            f"if [ ! -f {base}.pid ]; then echo 'no such job'; exit 3; fi; "
            f"el=$(( $(date +%s) - $(cat {base}.start) )); "
            f"if [ -f {base}.exit ]; then echo \"state: exited with code $(cat {base}.exit) after ${{el}}s\"; "
            f"elif kill -0 $(cat {base}.pid) 2>/dev/null; then echo \"state: running for ${{el}}s\"; "
            f"else echo 'state: lost (process gone without an exit code)'; fi; "
            f"echo '--- log tail ---'; tail -n {n} {base}.log 2>/dev/null"
        )
        outcome = await self.backend.run(cmd, timeout=60)
        return ToolResult(clip(outcome.stdout + outcome.stderr), is_error=outcome.exit_code == 3)

    async def _t_job_status(self, name: str, tail_lines: int | None = None) -> ToolResult:
        return await self._job_report(name, tail_lines or 40)

    async def _t_wait_job(self, name: str, max_wait_seconds: int | None = None) -> ToolResult:
        if not _JOB_NAME.match(name):
            return ToolResult("invalid job name", is_error=True)
        wait = min(max(1, max_wait_seconds or 300), MAX_WAIT_SECONDS)
        base = f"{JOBS_DIR}/{name}"
        cmd = (
            f"for i in $(seq 1 {wait}); do [ -f {base}.exit ] && break; "
            f"kill -0 $(cat {base}.pid 2>/dev/null) 2>/dev/null || break; sleep 1; done"
        )
        await self.backend.run(cmd, timeout=wait + 30)
        return await self._job_report(name)

    async def _t_stop_job(self, name: str) -> ToolResult:
        if not _JOB_NAME.match(name):
            return ToolResult("invalid job name", is_error=True)
        base = f"{JOBS_DIR}/{name}"
        cmd = (
            f"pid=$(cat {base}.pid 2>/dev/null) || {{ echo 'no such job'; exit 3; }}; "
            f"kill -TERM -- -$pid 2>/dev/null || kill -TERM $pid 2>/dev/null; sleep 2; "
            f"kill -KILL -- -$pid 2>/dev/null; [ -f {base}.exit ] || echo 143 > {base}.exit; echo stopped"
        )
        outcome = await self.backend.run(cmd, timeout=60)
        return ToolResult(_fmt(outcome), is_error=not outcome.ok)

    async def _t_compile_document(
        self, main: str, target: str, engine: str | None = None
    ) -> ToolResult:
        from .compile import CompileError, compile_command

        try:
            cmd, output = compile_command(main, target, engine)
        except CompileError as exc:
            return ToolResult(str(exc), is_error=True)
        outcome = await self.backend.run(cmd, timeout=600)
        if not outcome.ok:
            return ToolResult(_fmt(outcome), is_error=True)
        return ToolResult(f"compiled {main} -> {output}\n{clip(outcome.stdout[-3000:])}")

    async def _t_submit_experiment(
        self, experiment_path: str, setup_path: str | None = None
    ) -> ToolResult:
        if self.on_submit is None:
            return ToolResult("submission is not available in this session", is_error=True)
        code = (await self.backend.read_bytes(experiment_path)).decode("utf-8")
        setup = (
            (await self.backend.read_bytes(setup_path)).decode("utf-8")
            if setup_path
            else self.setup_script()
        )
        text, accepted, payload = await self.on_submit(code, setup)
        return ToolResult(text, is_error=not accepted, submitted=payload if accepted else None)


def _extract_command(dest: str) -> str | None:
    q = shlex.quote(dest)
    parent = f"\"$(dirname {q})\""
    lower = dest.lower()
    if lower.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".tar")):
        return f"tar -xf {q} -C {parent}"
    if lower.endswith(".zip"):
        return f"unzip -o -q {q} -d {parent}"
    if lower.endswith(".gz"):
        return f"gunzip -kf {q}"
    return None
