"""Stream 8 (F8) — autonomous research loop control plane.

Wraps :class:`plato.loop.research_loop.ResearchLoop` behind a small FastAPI
surface so the dashboard can start, stop, and watch a loop without going
through the CLI. Loops live entirely in process memory: spawn an asyncio
task, keep its handle in ``_LOOPS``, hand the loop_id back to the client.
The registry survives only as long as uvicorn does, which is the right
shape for a single-tenant developer tool — Phase 5 will promote it to
Redis/SQLite if multi-host operation lands.

Endpoints
---------
``POST   /api/v1/loop/start``       schedule a loop, return ``loop_id``
``GET    /api/v1/loop/{id}/status`` lightweight status snapshot
``POST   /api/v1/loop/{id}/stop``   cancel the asyncio task (idempotent)
``GET    /api/v1/loop/{id}/tsv``    parsed runs.tsv rows
``GET    /api/v1/loop``             list every known loop

The default ``score_fn`` is :func:`plato.loop.research_loop.latest_manifest_score`,
and the default ``plato_factory`` returns ``None`` — :class:`ResearchLoop`
calls the factory each iteration but never dereferences the result when the
score function is independent (which the default one is). Real workflows
inject richer factories via the CLI.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from ..settings import Settings, get_settings

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Request / response schemas
# --------------------------------------------------------------------------- #
class LoopStartRequest(BaseModel):
    project_dir: str = Field(
        ...,
        max_length=4096,
        description="Absolute path to the Plato project directory.",
    )
    max_iters: Optional[int] = Field(
        default=None,
        description="Hard iteration cap. ``null`` means run until time/cost cap fires.",
        ge=1,
        le=10_000,
    )
    time_budget_hours: float = Field(default=8.0, gt=0, le=24 * 30)
    max_cost_usd: float = Field(default=50.0, gt=0, le=10_000)
    # branch_prefix flows into ``git checkout -b <prefix>-<n>`` so we
    # restrict it to git-safe characters and a sensible length.
    branch_prefix: str = Field(
        default="plato-runs",
        max_length=64,
        pattern=r"^[A-Za-z0-9_./-]+$",
    )


class LoopStatus(BaseModel):
    loop_id: str
    # Discriminated by Literal so a typo in _supervise (e.g. "errored")
    # would fail validation at write-time rather than silently
    # producing a value the frontend can't match.
    status: Literal["running", "stopped", "interrupted", "error"]
    iterations: int
    kept: int
    discarded: int
    best_composite: float
    started_at: str  # iso8601
    tsv_path: str
    error: Optional[str] = None


class LoopTsvRow(BaseModel):
    iter: int
    timestamp: str
    composite: float
    status: str
    description: str


# --------------------------------------------------------------------------- #
# In-memory registry
# --------------------------------------------------------------------------- #
class LoopRecord:
    """Mutable state for a single loop. Owned by the registry.

    ``task`` is set immediately after construction by ``start_loop`` —
    we keep it ``Optional`` so the record can hold the ``loop_id`` value
    referenced by the closure in ``_supervise``. The supervisor never
    runs before ``task`` is assigned.
    """

    def __init__(
        self,
        *,
        loop_id: str,
        loop: Any,  # plato.loop.research_loop.ResearchLoop
        started_at: datetime,
        owner: Optional[str],
    ) -> None:
        self.loop_id = loop_id
        self.loop = loop
        self.task: Optional[asyncio.Task[Any]] = None
        self.started_at = started_at
        self.owner = owner
        self.status: str = "running"
        self.error: Optional[str] = None

    def snapshot(self) -> LoopStatus:
        """Read the loop's mutable counters atomically into a flat status payload."""
        # ResearchLoop maintains the canonical counters as plain ints/floats so
        # reading them under no lock is fine — Python's GIL guarantees an
        # atomic int read, and stale-by-one-iteration data is acceptable for
        # a status poll.
        loop = self.loop
        best = loop._best_composite
        if best == float("-inf"):
            best = 0.0
        return LoopStatus(
            loop_id=self.loop_id,
            status=self.status,
            iterations=int(loop._iter),
            kept=int(loop._kept),
            discarded=int(loop._discarded),
            best_composite=float(best),
            started_at=self.started_at.isoformat(),
            tsv_path=str(loop.tsv_path),
            error=self.error,
        )


_LOOPS: dict[str, LoopRecord] = {}


def reset_registry() -> None:
    """Test helper: drop every record without cancelling tasks.

    Tests build their own fake tasks so cancellation is the test's
    responsibility — this just clears the dict.
    """
    _LOOPS.clear()


# --------------------------------------------------------------------------- #
# Tenant guard
# --------------------------------------------------------------------------- #
def _user_id(
    settings: Settings = Depends(get_settings),
    x_plato_user: Optional[str] = Header(default=None, alias="X-Plato-User"),
) -> Optional[str]:
    """Resolve the calling user. Required when ``settings.is_auth_required``.

    In single-user local mode auth is disabled; the header is optional and
    every loop is owned by ``None``. In auth-required deployments the
    header must be present, otherwise we 401 — same behavior the rest of
    the API will adopt once Phase 1.5 lands a session store.
    """
    if not settings.is_auth_required:
        return x_plato_user  # may be None in local mode
    if not x_plato_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "auth_required",
                "message": "Send X-Plato-User; auth is enabled.",
            },
        )
    return x_plato_user


def _require_owned(record: LoopRecord, user: Optional[str]) -> None:
    """403 if the caller doesn't own the loop in auth-required mode.

    When auth is disabled, ``user`` and ``record.owner`` are both ``None``
    and ownership is moot.
    """
    if record.owner is None and user is None:
        return
    if record.owner != user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "loop_not_owned"},
        )


# --------------------------------------------------------------------------- #
# Loop lifecycle
# --------------------------------------------------------------------------- #
def _build_loop(req: LoopStartRequest) -> Any:
    """Construct a real ResearchLoop. Imported lazily so test stubs can patch it."""
    from plato.loop.research_loop import ResearchLoop  # noqa: WPS433 — lazy on purpose

    return ResearchLoop(
        project_dir=req.project_dir,
        max_iters=req.max_iters,
        time_budget_hours=req.time_budget_hours,
        max_cost_usd=req.max_cost_usd,
        branch_prefix=req.branch_prefix,
    )


def _default_factory() -> Any:
    """Return ``None``. The default score function is project-dir-relative,
    so it never dereferences the factory result. CLI callers inject richer
    factories that return a real :class:`Plato` instance.
    """
    return None


def _default_score_fn(project_dir: str | Path):
    """Closure that calls :func:`latest_manifest_score` on each iteration."""
    from plato.loop.research_loop import latest_manifest_score  # noqa: WPS433

    def _score(_plato: Any):
        return latest_manifest_score(project_dir)

    return _score


async def _supervise(record: LoopRecord) -> None:
    """Await ``record.loop.run`` and mirror its terminal state into the record.

    Wrapping ``ResearchLoop.run`` in this supervisor keeps the cancellation
    handling in one place: any ``CancelledError`` flips the status to
    ``stopped``, any other exception flips it to ``error`` with the message
    captured. Without this, the API would have to inspect the asyncio task
    on every status read.
    """
    try:
        await record.loop.run(_default_factory, _default_score_fn(record.loop.project_dir))
        record.status = "stopped"
    except asyncio.CancelledError:
        record.status = "stopped"
        raise
    except KeyboardInterrupt:
        record.status = "interrupted"
    except Exception as exc:  # noqa: BLE001 — we deliberately surface every error
        logger.exception("ResearchLoop %s errored", record.loop_id)
        record.status = "error"
        record.error = f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------- #
# Router
# --------------------------------------------------------------------------- #
router = APIRouter(prefix="/api/v1/loop", tags=["loop"])


@router.post("/start", response_model=LoopStatus, status_code=status.HTTP_201_CREATED)
async def start_loop(
    req: LoopStartRequest,
    user: Optional[str] = Depends(_user_id),
) -> LoopStatus:
    loop_id = uuid.uuid4().hex[:12]
    research_loop = _build_loop(req)
    started_at = datetime.now(timezone.utc)

    # Create record first so _supervise can mutate it via closure.
    record = LoopRecord(
        loop_id=loop_id,
        loop=research_loop,
        started_at=started_at,
        owner=user,
    )
    record.task = asyncio.create_task(_supervise(record), name=f"loop-{loop_id}")
    _LOOPS[loop_id] = record
    return record.snapshot()


@router.get("", response_model=list[LoopStatus])
def list_loops(user: Optional[str] = Depends(_user_id)) -> list[LoopStatus]:
    """Return every loop visible to the caller, newest first."""
    rows: list[LoopStatus] = []
    for record in _LOOPS.values():
        # In auth-required mode hide loops owned by other tenants.
        if record.owner is not None and user is not None and record.owner != user:
            continue
        rows.append(record.snapshot())
    rows.sort(key=lambda r: r.started_at, reverse=True)
    return rows


@router.get("/{loop_id}/status", response_model=LoopStatus)
def get_loop_status(loop_id: str, user: Optional[str] = Depends(_user_id)) -> LoopStatus:
    record = _LOOPS.get(loop_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "loop_not_found"})
    _require_owned(record, user)
    return record.snapshot()


@router.post("/{loop_id}/stop", response_model=LoopStatus)
async def stop_loop(loop_id: str, user: Optional[str] = Depends(_user_id)) -> LoopStatus:
    """Cancel the asyncio task and return the resulting status. Idempotent."""
    record = _LOOPS.get(loop_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "loop_not_found"})
    _require_owned(record, user)

    task = record.task
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            # _supervise has already mapped the exception into record.status.
            pass

    if record.status == "running":
        # Race: task finished cleanly between the done() check and the await.
        # Reflect that as stopped rather than leaving stale "running".
        record.status = "stopped"
    return record.snapshot()


@router.get("/{loop_id}/tsv", response_model=dict)
def get_loop_tsv(loop_id: str, user: Optional[str] = Depends(_user_id)) -> dict:
    """Return parsed runs.tsv rows as JSON.

    Bytes-on-disk source of truth — no in-memory mirror — so the client
    sees exactly what ``ResearchLoop`` wrote. If the file hasn't been
    created yet (loop just started) we return an empty list rather than
    404'ing, which makes the polling UX simpler.
    """
    record = _LOOPS.get(loop_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "loop_not_found"})
    _require_owned(record, user)

    return {"rows": _read_tsv(Path(record.loop.tsv_path))}


def _read_tsv(path: Path) -> list[dict]:
    """Parse a ResearchLoop runs.tsv. Tolerates a missing or partial file."""
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    # Header is "iter\ttimestamp\tcomposite\tstatus\tdescription"; skip if present.
    body = lines[1:] if lines[0].startswith("iter\t") else lines
    rows: list[dict] = []
    for line in body:
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        try:
            iteration = int(parts[0])
        except ValueError:
            continue
        try:
            composite = float(parts[2])
        except ValueError:
            composite = float("nan")
        rows.append(
            {
                "iter": iteration,
                "timestamp": parts[1],
                "composite": composite,
                "status": parts[3],
                "description": parts[4],
            }
        )
    return rows
