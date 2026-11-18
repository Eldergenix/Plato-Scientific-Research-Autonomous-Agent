"""Backend selection and the reproducible experiment runner.

Configuration comes from the scientist container's environment only:

* ``E2B_API_KEY``: E2B credentials (a Worker secret forwarded to the container; it is
  never passed into a sandbox).
* ``PLATO_E2B_TEMPLATE``: the sandbox template, default ``plato-lab``.
* ``PLATO_WORKSPACE_BACKEND=local``: run workspaces on the host instead (tests and
  development only, no isolation).
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

from ..guard.sandbox import SandboxResult
from .backend import E2BBackend, LocalBackend, SandboxBackend

DEFAULT_TEMPLATE = "plato-lab"
EXPERIMENT_SCRIPT = "experiment.py"
SETUP_SCRIPT = "setup.sh"
_COLLECT_SUFFIXES = (".png", ".json", ".csv", ".tsv", ".txt", ".tex", ".pdf")
_COLLECT_MAX_BYTES = 1_048_576
_MAX_OUTPUT_CHARS = 200_000

BackendFactory = Callable[..., Awaitable[SandboxBackend]]


def e2b_configured() -> bool:
    return bool(os.environ.get("E2B_API_KEY")) or os.environ.get(
        "PLATO_WORKSPACE_BACKEND"
    ) == "local"


def default_backend_factory() -> BackendFactory:
    if os.environ.get("PLATO_WORKSPACE_BACKEND") == "local":

        async def local(**_: Any) -> SandboxBackend:
            return await LocalBackend.create()

        return local

    template = os.environ.get("PLATO_E2B_TEMPLATE", DEFAULT_TEMPLATE)

    async def e2b(
        *,
        timeout_seconds: int,
        purpose: str = "workspace",
        metadata: dict[str, str] | None = None,
    ) -> SandboxBackend:
        api_key = os.environ.get("E2B_API_KEY")
        if not api_key:
            raise RuntimeError("E2B_API_KEY is not set in the scientist container")
        return await E2BBackend.create(
            template=template,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            metadata={"app": "plato-scientist", "purpose": purpose, **(metadata or {})},
        )

    return e2b


async def _snapshot(backend: SandboxBackend) -> dict[str, tuple[str, int]]:
    out = await backend.run("find . -maxdepth 1 -type f -printf '%T@ %s %f\\n'", timeout=60)
    snap: dict[str, tuple[str, int]] = {}
    for line in out.stdout.splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3 and parts[1].isdigit():
            snap[parts[2]] = (parts[0], int(parts[1]))
    return snap


def _clip(text: str, limit: int = _MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n...[{len(text) - limit} chars elided]...\n{text[-half:]}"


async def run_recipe(
    backend_factory: BackendFactory,
    *,
    code: str,
    setup: str | None,
    inputs: dict[str, bytes],
    setup_seconds: int,
    run_seconds: int,
    metadata: dict[str, str] | None = None,
) -> SandboxResult:
    """Run ``setup`` (network on), then ``code`` (network off) in a fresh sandbox.

    This is the only way a result enters the record: the environment is rebuilt from
    the recipe every time, so seed-2 replication and sealed evaluation exercise exactly
    what the original run did. ``duration_seconds`` covers the experiment only.
    """
    backend = await backend_factory(
        timeout_seconds=setup_seconds + run_seconds + 300,
        purpose="experiment",
        metadata=metadata,
    )
    try:
        for name, data in inputs.items():
            safe = os.path.basename(name)
            if not safe or safe.startswith(".") or safe in (EXPERIMENT_SCRIPT, SETUP_SCRIPT):
                raise ValueError(f"invalid input file name {name!r}")
            await backend.write_bytes(safe, data)
        await backend.write_bytes(EXPERIMENT_SCRIPT, code.encode("utf-8"))
        if setup and setup.strip():
            await backend.write_bytes(SETUP_SCRIPT, setup.encode("utf-8"))
            prep = await backend.run(f"bash {SETUP_SCRIPT}", timeout=setup_seconds)
            if not prep.ok:
                reason = "timed out" if prep.timed_out else f"exited with code {prep.exit_code}"
                return SandboxResult(
                    exit_code=prep.exit_code if prep.exit_code not in (None, 0) else 1,
                    stdout="",
                    stderr=_clip(f"setup.sh {reason}\n{prep.stdout}\n{prep.stderr}"),
                    duration_seconds=0.0,
                    timed_out=prep.timed_out,
                    network_isolated=False,
                )
        # Outputs are files the experiment created or changed, not what setup fetched.
        before = await _snapshot(backend)
        isolated = await backend.set_network(False)
        run = await backend.run(
            f"MPLBACKEND=Agg python {EXPERIMENT_SCRIPT}", timeout=run_seconds
        )
        files: dict[str, bytes] = {}
        after = await _snapshot(backend)
        skip = {EXPERIMENT_SCRIPT, SETUP_SCRIPT, *inputs}
        for name, (mtime, size) in sorted(after.items()):
            if (
                name.endswith(_COLLECT_SUFFIXES)
                and name not in skip
                and size <= _COLLECT_MAX_BYTES
                and before.get(name, (None, None))[0] != mtime
            ):
                data = await backend.read_bytes(name)
                if len(data) <= _COLLECT_MAX_BYTES:
                    files[name] = data
        return SandboxResult(
            exit_code=run.exit_code,
            stdout=_clip(run.stdout),
            stderr=_clip(run.stderr),
            duration_seconds=run.duration_seconds,
            timed_out=run.timed_out,
            network_isolated=isolated,
            files=files,
        )
    finally:
        await backend.close()
