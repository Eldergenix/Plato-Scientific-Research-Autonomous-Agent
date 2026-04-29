"""File-tail bridge for cmbagent log files.

cmbagent writes streaming logs to disk under the project directory:
    project_dir/idea_generation_output/idea.log
    project_dir/method_generation_output/methods.log
    project_dir/experiment_generation_output/<subdir>/chat_history.json (etc.)
    project_dir/literature_output/literature.log

This module watches the relevant directory for the given stage and tails any
``*.log`` / ``*.txt`` file it finds, publishing each new line as a ``log.line``
event on the dashboard event bus. Progress markers like ``Step 3 / 6`` and
``Attempt 2 / 5`` are also surfaced as ``stage.heartbeat`` events.

Usage::

    tailer = LogTailer(project_dir, run_id, "idea", get_bus())
    await tailer.start()
    ...
    await tailer.stop()
"""

from __future__ import annotations
import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from watchfiles import awatch, Change

from ..domain.models import StageId
from ..events.bus import EventBus


# ---------------------------------------------------------------------------
# Stage → directory mapping
# ---------------------------------------------------------------------------

# cmbagent emits its logs under per-phase dirs that don't perfectly mirror our
# StageId vocabulary, so we keep an explicit map.
_STAGE_DIRS: dict[StageId, str] = {
    "idea": "idea_generation_output",
    "method": "method_generation_output",
    "results": "experiment_generation_output",
    "literature": "literature_output",
}

# File extensions worth tailing as log streams. JSON files (chat_history.json)
# are append-mostly but not line-delimited, so we skip them here — a separate
# parser handles those.
_TAIL_EXTS = {".log", ".txt"}


# ---------------------------------------------------------------------------
# Line-parsing regexes
# ---------------------------------------------------------------------------

# cmbagent commonly prefixes turns with the agent name in brackets:
#   [engineer]: starting analysis ...
#   [planner] step 1
_AGENT_RE = re.compile(r"^\s*\[(?P<agent>[A-Za-z0-9_\-]+)\]\s*[:\-]?\s*(?P<rest>.*)$")

# "Step 3 / 6" or "Step 3 of 6" — used as the primary progress signal.
_STEP_RE = re.compile(r"\bStep\s+(?P<step>\d+)\s*(?:/|of)\s*(?P<total>\d+)\b", re.IGNORECASE)

# "Attempt 2 / 5" — secondary heartbeat (retry within a step).
_ATTEMPT_RE = re.compile(
    r"\bAttempt\s+(?P<attempt>\d+)\s*(?:/|of)\s*(?P<total>\d+)\b", re.IGNORECASE
)

# Crude level inference. cmbagent doesn't emit syslog levels, so we sniff for
# common error/warn words. Keep the patterns boundary-anchored so "errorless"
# doesn't trigger.
_ERROR_WORDS = re.compile(r"\b(error|exception|traceback|failed|failure)\b", re.IGNORECASE)
_WARN_WORDS = re.compile(r"\b(warning|warn|deprecat\w*)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helper: parse one line into an event dict
# ---------------------------------------------------------------------------

def tail_line_to_event(line: str, stage: StageId, run_id: str) -> dict:
    """Convert one raw log line into a ``log.line`` event payload.

    The bus consumer decides how to render this; we only attach light metadata
    (agent name, level, timestamp). Step/attempt parsing is handled separately
    so the caller can also publish a heartbeat.
    """
    text = line.rstrip("\n").rstrip("\r")
    agent: Optional[str] = None

    m = _AGENT_RE.match(text)
    if m and m.group("rest"):
        agent = m.group("agent")

    if _ERROR_WORDS.search(text):
        level = "error"
    elif _WARN_WORDS.search(text):
        level = "warn"
    else:
        level = "info"

    return {
        "kind": "log.line",
        "run_id": run_id,
        "stage": stage,
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": stage,
        "agent": agent,
        "level": level,
        "text": text,
    }


# ---------------------------------------------------------------------------
# LogTailer
# ---------------------------------------------------------------------------

class LogTailer:
    """Watch a stage output directory and stream its log files to the bus."""

    def __init__(
        self,
        project_dir: Path,
        run_id: str,
        stage: StageId,
        bus: EventBus,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.run_id = run_id
        self.stage = stage
        self.bus = bus

        subdir = _STAGE_DIRS.get(stage)
        if subdir is None:
            raise ValueError(f"LogTailer does not support stage {stage!r}")
        self.watch_dir = self.project_dir / subdir

        self._channel = f"run:{run_id}"
        self._main_task: Optional[asyncio.Task] = None
        self._tail_tasks: dict[Path, asyncio.Task] = {}
        self._stop_event = asyncio.Event()

    # ------------------------------------------------------------------ public
    async def start(self) -> None:
        """Kick off the watch + tail loop. Returns immediately."""
        if self._main_task is not None:
            return
        self._stop_event = asyncio.Event()
        self._main_task = asyncio.create_task(self._run(), name=f"log-tailer:{self.stage}")

    async def stop(self) -> None:
        """Cancel the watch task and any per-file tail tasks cleanly."""
        self._stop_event.set()
        if self._main_task is not None:
            self._main_task.cancel()
            try:
                await self._main_task
            except (asyncio.CancelledError, Exception):
                pass
            self._main_task = None
        # _run's TaskGroup propagates cancellation to children, but if anything
        # leaked (e.g. start() was never awaited cleanly) we mop up here.
        for task in list(self._tail_tasks.values()):
            task.cancel()
        self._tail_tasks.clear()

    # ------------------------------------------------------------------ core
    async def _run(self) -> None:
        """Top-level coroutine: wait for dir, then watch + tail under TaskGroup."""
        try:
            async with asyncio.TaskGroup() as tg:
                # Spawn directory watcher; per-file tail tasks are spawned from
                # within the watcher as new files appear.
                tg.create_task(self._watch_directory(tg), name=f"watch:{self.stage}")
        except* asyncio.CancelledError:
            # Cancellation is the normal shutdown path — swallow it.
            pass

    async def _wait_for_directory(self) -> None:
        """Poll until ``watch_dir`` exists, with a 500ms cadence."""
        while not self.watch_dir.exists() and not self._stop_event.is_set():
            await asyncio.sleep(0.5)

    async def _watch_directory(self, tg: asyncio.TaskGroup) -> None:
        """Watch ``watch_dir`` for new ``*.log``/``*.txt`` files and tail them."""
        await self._wait_for_directory()
        if self._stop_event.is_set():
            return

        # Tail any files that already exist before the watcher starts (cmbagent
        # may have written them in between our existence check and awatch).
        for path in sorted(self.watch_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in _TAIL_EXTS:
                self._spawn_tail(tg, path)

        stop_event_internal = asyncio.Event()

        async def _stop_when_signaled() -> None:
            await self._stop_event.wait()
            stop_event_internal.set()

        tg.create_task(_stop_when_signaled(), name="tailer-stop-bridge")

        try:
            async for changes in awatch(
                self.watch_dir,
                step=500,
                stop_event=stop_event_internal,
                recursive=True,
            ):
                for change, raw_path in changes:
                    path = Path(raw_path)
                    if path.suffix.lower() not in _TAIL_EXTS:
                        continue
                    if change in (Change.added, Change.modified):
                        if path not in self._tail_tasks and path.exists():
                            self._spawn_tail(tg, path)
        except FileNotFoundError:
            # Directory disappeared mid-watch — back to polling.
            await self._wait_for_directory()

    def _spawn_tail(self, tg: asyncio.TaskGroup, path: Path) -> None:
        task = tg.create_task(self._tail_file(path), name=f"tail:{path.name}")
        self._tail_tasks[path] = task

    # ---------------------------------------------------------------- per-file
    async def _tail_file(self, path: Path) -> None:
        """Read ``path`` line-by-line, publishing each new line.

        Restarts from offset 0 if the file is truncated or rotated. Decodes with
        ``errors='replace'`` so binary garbage doesn't crash the loop.
        """
        offset = 0
        try:
            while not self._stop_event.is_set():
                try:
                    stat = path.stat()
                except FileNotFoundError:
                    # File vanished (rotation in flight) — wait and retry.
                    await asyncio.sleep(0.25)
                    continue

                if stat.st_size < offset:
                    # Truncated — start over.
                    offset = 0

                if stat.st_size == offset:
                    await asyncio.sleep(0.2)
                    continue

                # Read whatever's available since last offset, in chunks of full
                # lines. We don't use aiofiles here because the file is already
                # local and the read is bounded; a small thread executor is fine.
                new_offset, lines = await asyncio.to_thread(_read_new_lines, path, offset)
                offset = new_offset
                for line in lines:
                    await self._publish_line(line)
        except asyncio.CancelledError:
            return

    async def _publish_line(self, line: str) -> None:
        if not line.strip():
            return
        event = tail_line_to_event(line, self.stage, self.run_id)
        await self.bus.publish(self._channel, event)

        m = _STEP_RE.search(line)
        if m:
            await self.bus.publish(
                self._channel,
                {
                    "kind": "stage.heartbeat",
                    "run_id": self.run_id,
                    "step": int(m.group("step")),
                    "total_steps": int(m.group("total")),
                },
            )
        m2 = _ATTEMPT_RE.search(line)
        if m2:
            await self.bus.publish(
                self._channel,
                {
                    "kind": "stage.heartbeat",
                    "run_id": self.run_id,
                    "attempt": int(m2.group("attempt")),
                    "total_attempts": int(m2.group("total")),
                },
            )


def _read_new_lines(path: Path, offset: int) -> tuple[int, list[str]]:
    """Synchronous helper run in a thread: read from offset to EOF as lines."""
    with path.open("rb") as f:
        f.seek(offset)
        data = f.read()
    if not data:
        return offset, []
    text = data.decode("utf-8", errors="replace")
    # If the trailing chunk doesn't end with a newline, hold it back so we
    # don't emit half-lines. Advance offset only past whole lines.
    if text.endswith("\n"):
        lines = text.splitlines()
        new_offset = offset + len(data)
    else:
        idx = text.rfind("\n")
        if idx < 0:
            # No complete line yet.
            return offset, []
        whole = text[: idx + 1]
        lines = whole.splitlines()
        new_offset = offset + len(whole.encode("utf-8"))
    return new_offset, lines


# ---------------------------------------------------------------------------
# Self-test (`python -m plato_dashboard.worker.log_tail`)
# ---------------------------------------------------------------------------

async def _selftest() -> None:
    import tempfile

    from ..events.bus import EventBus

    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        bus = EventBus()
        run_id = "run_demo"
        tailer = LogTailer(project_dir, run_id, "idea", bus)

        received: list[dict] = []

        async def consume() -> None:
            async for ev in bus.subscribe(f"run:{run_id}"):
                received.append(ev)
                print("EVENT:", ev)
                if len(received) >= 6:
                    return

        consumer = asyncio.create_task(consume())
        await tailer.start()

        await asyncio.sleep(0.2)
        idea_dir = project_dir / "idea_generation_output"
        idea_dir.mkdir(parents=True, exist_ok=True)
        log_file = idea_dir / "idea.log"

        with log_file.open("w") as f:
            f.write("[planner]: kicking off idea generation\n")
            f.flush()
        await asyncio.sleep(0.7)
        with log_file.open("a") as f:
            f.write("Step 1 / 3: brainstorm\n")
            f.write("[engineer]: warning: low signal\n")
            f.write("Attempt 2 / 5\n")
            f.write("Step 2 / 3: refine\n")
            f.write("traceback: oops\n")
            f.flush()

        try:
            await asyncio.wait_for(consumer, timeout=5.0)
        except asyncio.TimeoutError:
            print(f"timed out waiting for events; received {len(received)}")
        finally:
            await tailer.stop()

        print(f"\nTotal events received: {len(received)}")


if __name__ == "__main__":
    asyncio.run(_selftest())
