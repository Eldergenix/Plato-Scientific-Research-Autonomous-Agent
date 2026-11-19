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
import logging
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
# Seconds to wait for a request stream to open. The SDK default (60 s) is too short for a
# busy sandbox: live verification saw a long-running check fail before its command started.
# Commands are not retried (they are not idempotent), so the wait is generous instead.
_REQUEST_TIMEOUT = 180.0
# Attempts to create a sandbox; creation is retried on transport errors only.
_CREATE_ATTEMPTS = 3

logger = logging.getLogger(__name__)


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


def _transient(exc: BaseException) -> bool:
    """Network-level failures (dropped connection, timeout) worth one more attempt."""
    import httpx
    from e2b import TimeoutException

    return isinstance(
        exc, (httpx.TransportError, TimeoutException, TimeoutError, ConnectionError)
    )


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
        for attempt in range(1, _CREATE_ATTEMPTS + 1):
            try:
                sbx = await AsyncSandbox.create(**kwargs)
                break
            except Exception as exc:
                # Auth, quota and template errors are permanent; only transport errors retry.
                # A sandbox half-created by a failed attempt is reaped by its own timeout.
                if attempt == _CREATE_ATTEMPTS or not _transient(exc):
                    raise
                await asyncio.sleep(2 * attempt)
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
                request_timeout=_REQUEST_TIMEOUT,
            )
            exit_code, out, err = res.exit_code, res.stdout or "", res.stderr or ""
        except CommandExitException as exc:  # non-zero exit is a result, not an error
            exit_code, out, err = exc.exit_code, exc.stdout or "", exc.stderr or ""
        except TimeoutException as exc:
            return CommandOutcome(
                None,
                "",
                f"sandbox transport timed out: {exc}",
                time.monotonic() - started,
                True,
            )
        return CommandOutcome(
            exit_code,
            out,
            err,
            time.monotonic() - started,
            timed_out=exit_code == _TIMEOUT_EXIT,
        )

    async def write_bytes(self, path: str, data: bytes) -> None:
        await self._sbx.files.write(
            self._abs(path), data, request_timeout=_REQUEST_TIMEOUT
        )

    async def read_bytes(self, path: str) -> bytes:
        return bytes(
            await self._sbx.files.read(
                self._abs(path), format="bytes", request_timeout=_REQUEST_TIMEOUT
            )
        )

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
        except Exception as exc:  # noqa: BLE001 - already gone (timeout) is fine
            logger.debug("E2B sandbox kill: %s", exc)

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
