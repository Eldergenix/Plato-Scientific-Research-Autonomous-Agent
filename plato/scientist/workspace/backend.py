"""Sandbox backends for the agent workspace.

A backend is a disposable Linux machine the agent may use freely: a shell, a file
system, package managers and (while allowed) the public internet. Everything higher
level (file search, package installs, dataset downloads, background jobs, document
compilation) is built on four primitives, so every backend behaves the same:

* ``run(command)``: a bash command with a hard wall-clock limit;
* ``write_bytes`` / ``read_bytes``;
* ``set_network(allow)``: cut or restore outbound traffic.

:class:`E2BBackend` is the production backend: each instance is its own Firecracker
microVM on E2B, so model-written commands never run on the scientist container and
never see its secrets (no environment variables are forwarded). :class:`LocalBackend`
runs the same commands in a temporary directory on the host; it exists for tests and
local development only and offers no isolation.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import signal
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# Exit status of coreutils `timeout` when the limit was hit.
_TIMEOUT_EXIT = 124
# Extra seconds the transport waits beyond the in-sandbox limit before giving up.
_TRANSPORT_GRACE = 30.0


@dataclass(frozen=True)
class CommandOutcome:
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class SandboxBackend(Protocol):
    sandbox_id: str
    workdir: str
    network_enforced: bool

    async def run(
        self, command: str, *, cwd: str | None = None, timeout: float = 120.0
    ) -> CommandOutcome: ...

    async def write_bytes(self, path: str, data: bytes) -> None: ...

    async def read_bytes(self, path: str) -> bytes: ...

    async def set_network(self, allow: bool) -> bool:
        """Allow or deny all outbound traffic. Returns True when the backend enforced it."""
        ...

    async def close(self) -> None: ...


def wrap_with_timeout(command: str, timeout: float) -> str:
    """Bound the command inside the sandbox, so a stuck process is killed there (the SDK's
    own timeout only drops the connection and would leave the process running)."""
    seconds = max(1, int(timeout))
    return f"timeout -k 5 {seconds} bash -lc {shlex.quote(command)}"


class E2BBackend:
    """One E2B sandbox (``e2b`` SDK 2.x, ``AsyncSandbox``)."""

    network_enforced = True

    def __init__(self, sandbox, workdir: str) -> None:
        self._sbx = sandbox
        self.sandbox_id: str = sandbox.sandbox_id
        self.workdir = workdir

    @classmethod
    async def create(
        cls,
        *,
        template: str | None,
        api_key: str | None,
        timeout_seconds: int,
        metadata: dict[str, str] | None = None,
        allow_internet: bool = True,
        workdir: str = "/home/user/work",
    ) -> E2BBackend:
        from e2b import AsyncSandbox

        kwargs: dict = {
            "timeout": int(timeout_seconds),
            "metadata": metadata or {},
            "allow_internet_access": allow_internet,
        }
        if template:
            kwargs["template"] = template
        if api_key:
            kwargs["api_key"] = api_key
        sbx = await AsyncSandbox.create(**kwargs)
        backend = cls(sbx, workdir)
        await backend.run(f"mkdir -p {shlex.quote(workdir)}", timeout=30)
        return backend

    async def run(
        self, command: str, *, cwd: str | None = None, timeout: float = 120.0
    ) -> CommandOutcome:
        from e2b import CommandExitException, TimeoutException

        started = time.monotonic()
        try:
            res = await self._sbx.commands.run(
                wrap_with_timeout(command, timeout),
                cwd=cwd or self.workdir,
                timeout=timeout + _TRANSPORT_GRACE,
            )
            exit_code, out, err = res.exit_code, res.stdout or "", res.stderr or ""
        except CommandExitException as exc:  # non-zero exit is a result, not an error
            exit_code, out, err = exc.exit_code, exc.stdout or "", exc.stderr or ""
        except TimeoutException as exc:
            return CommandOutcome(
                None, "", f"sandbox transport timed out: {exc}", time.monotonic() - started, True
            )
        return CommandOutcome(
            exit_code,
            out,
            err,
            time.monotonic() - started,
            timed_out=exit_code == _TIMEOUT_EXIT,
        )

    async def write_bytes(self, path: str, data: bytes) -> None:
        await self._sbx.files.write(self._abs(path), data)

    async def read_bytes(self, path: str) -> bytes:
        return bytes(await self._sbx.files.read(self._abs(path), format="bytes"))

    async def set_network(self, allow: bool) -> bool:
        from e2b import ALL_TRAFFIC

        # The update replaces all egress rules atomically; an empty update clears the deny.
        await self._sbx.update_network({} if allow else {"deny_out": [ALL_TRAFFIC]})
        return True

    async def extend(self, seconds: int) -> None:
        await self._sbx.set_timeout(int(seconds))

    async def close(self) -> None:
        try:
            await self._sbx.kill()
        except Exception:  # already gone (timeout) is fine
            pass

    def _abs(self, path: str) -> str:
        return path if path.startswith("/") else f"{self.workdir}/{path}"


class LocalBackend:
    """Same contract on the host, in a temporary directory. Tests and development only:
    it neither isolates commands nor controls the network."""

    network_enforced = False

    def __init__(self, root: Path) -> None:
        self._root = root
        self.workdir = str(root / "work")
        Path(self.workdir).mkdir(parents=True, exist_ok=True)
        self.sandbox_id = f"local-{root.name}"
        self.network_allowed = True

    @classmethod
    async def create(cls, **_: object) -> LocalBackend:
        return cls(Path(tempfile.mkdtemp(prefix="plato-ws-")))

    async def run(
        self, command: str, *, cwd: str | None = None, timeout: float = 120.0
    ) -> CommandOutcome:
        started = time.monotonic()
        # The running interpreter's environment comes first, so `python` in a command is
        # the same Python (and packages) as the service's.
        path = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")
        env = {
            "PATH": f"{os.path.dirname(sys.executable)}:{path}",
            "HOME": str(self._root),
            "LANG": "C.UTF-8",
        }
        proc = await asyncio.create_subprocess_exec(
            "bash",
            "-c",
            command,
            cwd=cwd or self.workdir,
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            out, err = await proc.communicate()
            return CommandOutcome(
                None,
                out.decode("utf-8", "replace"),
                err.decode("utf-8", "replace"),
                time.monotonic() - started,
                True,
            )
        return CommandOutcome(
            proc.returncode,
            out.decode("utf-8", "replace"),
            err.decode("utf-8", "replace"),
            time.monotonic() - started,
        )

    async def write_bytes(self, path: str, data: bytes) -> None:
        target = Path(self._abs(path))
        target.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, data)

    async def read_bytes(self, path: str) -> bytes:
        return await asyncio.to_thread(Path(self._abs(path)).read_bytes)

    async def set_network(self, allow: bool) -> bool:
        self.network_allowed = allow
        return False

    async def extend(self, seconds: int) -> None:
        return None

    async def close(self) -> None:
        await asyncio.to_thread(shutil.rmtree, self._root, True)

    def _abs(self, path: str) -> str:
        return path if path.startswith("/") else f"{self.workdir}/{path}"
