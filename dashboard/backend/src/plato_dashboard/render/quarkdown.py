import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DocType = Literal["plain", "paged", "slides", "docs"]


@dataclass
class RenderResult:
    html_path: Path | None
    pdf_path: Path | None
    stdout: str
    stderr: str
    returncode: int


async def render_qd(
    qd_path: Path,
    out_dir: Path,
    *,
    pdf: bool = True,
    timeout_s: int = 90,
    no_sandbox: bool = True,  # required inside container
) -> RenderResult:
    """Run the Quarkdown CLI on ``qd_path`` and return discovered outputs.

    Mirrors the subprocess pattern used by ``plato/paper_agents/latex.py``
    (capture_output + structured error surfacing) but runs under asyncio
    so the FastAPI worker stays non-blocking. We avoid the shell entirely
    via ``asyncio.create_subprocess_exec`` (argv list, not a string), so
    user-provided ``qd_path`` / ``out_dir`` cannot inject shell tokens.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "quarkdown",
        "c",
        str(qd_path),
        "-o",
        str(out_dir),
        "--strict",
        "--timeout",
        str(timeout_s),
    ]
    if pdf:
        cmd.append("--pdf")
    if no_sandbox:
        cmd.append("--pdf-no-sandbox")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=out_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_s
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"Quarkdown render timed out after {timeout_s}s")
    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    # Discover output files (Quarkdown writes <stem>.html / <stem>.pdf into out_dir).
    html = next(iter(out_dir.glob("*.html")), None)
    pdf_file = next(iter(out_dir.glob("*.pdf")), None) if pdf else None
    return RenderResult(
        html_path=html,
        pdf_path=pdf_file,
        stdout=stdout,
        stderr=stderr,
        returncode=proc.returncode or 0,
    )
