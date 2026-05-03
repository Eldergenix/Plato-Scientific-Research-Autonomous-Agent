"""Phase 4 — R10: autonomous research loop.

This module implements the autoresearch-master-style overnight loop adapted
for Plato. Each iteration:

  1. Calls a user-supplied ``plato_factory`` to (re-)instantiate Plato.
  2. Runs ``score_fn`` to obtain an :class:`AcceptanceScore`.
  3. Compares the new composite score to the last accepted one.
  4. Accepts (commits to a tracking branch) or rejects (``git reset --hard``)
     the iteration.
  5. Appends a row to ``runs.tsv``.

The loop honors three hard caps — wall-clock time, max iterations, and
cumulative cost — and a SIGINT handler ensures the TSV is closed cleanly
on Ctrl-C. Git is treated as an *optional* checkpoint store: if ``git``
is unavailable or the project_dir isn't a repo, the loop logs a warning
once and runs without commits.
"""
from __future__ import annotations
import inspect
import logging
import shutil
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from plato.plato import Plato


logger = logging.getLogger(__name__)


class AcceptanceScore(BaseModel):
    """Composite acceptance score for a single research-loop iteration.

    Higher composite is better. The formula is:

        composite = citation_validation_rate
                  - unsupported_claim_rate
                  - 0.1 * (referee_severity_max or 0)
                  - 0.001 * simplicity_delta

    ``simplicity_delta`` represents lines-of-code change since the previous
    iteration; positive deltas (i.e. larger codebases) lightly penalize the
    score so the loop drifts toward simpler solutions when other terms tie.
    """

    citation_validation_rate: float = Field(
        description="Fraction of citations whose DOI/arXiv id resolved cleanly. [0,1]",
    )
    unsupported_claim_rate: float = Field(
        description="Fraction of paper claims with no supporting EvidenceLink. [0,1]",
    )
    referee_severity_max: int | None = Field(
        default=None,
        description="Worst referee-issue severity for this iteration (0-3). None means no referee run.",
    )
    simplicity_delta: float = Field(
        default=0.0,
        description="Lines-of-code delta vs. the previous iteration. Positive = bigger.",
    )

    def composite(self) -> float:
        """Single scalar; higher is better."""
        severity = self.referee_severity_max or 0
        return (
            self.citation_validation_rate
            - self.unsupported_claim_rate
            - 0.1 * severity
            - 0.001 * self.simplicity_delta
        )


# Type aliases for the user-supplied callables.
PlatoFactory = Callable[[], "Plato"]
ScoreFn = Callable[["Plato"], "AcceptanceScore | Awaitable[AcceptanceScore]"]


_TSV_HEADER = "iter\ttimestamp\tcomposite\tstatus\tdescription\n"


class ResearchLoop:
    """Autonomous overnight research loop.

    Maintains a tracking git branch (``<branch_prefix>/<timestamp>``) under
    ``project_dir`` (or cwd if project_dir isn't itself a git repo) and a
    TSV log of every iteration's composite score and accept/discard
    decision. Hard caps stop the loop on iteration count, wall-clock time,
    or cumulative cost.
    """

    def __init__(
        self,
        *,
        project_dir: str | Path,
        max_iters: int | None = None,
        time_budget_hours: float = 8.0,
        max_cost_usd: float = 50.0,
        branch_prefix: str = "plato-runs",
    ) -> None:
        self.project_dir = Path(project_dir)
        self.max_iters = max_iters
        self.time_budget_hours = time_budget_hours
        self.max_cost_usd = max_cost_usd
        self.branch_prefix = branch_prefix

        self.tsv_path: Path = self.project_dir / "runs.tsv"
        self._iter: int = 0
        self._kept: int = 0
        self._discarded: int = 0
        self._best_composite: float = float("-inf")
        self._last_accepted_composite: float | None = None
        self._git_available: bool = False
        self._git_root: Path | None = None
        self._branch_name: str | None = None
        self._git_warned: bool = False
        self._tsv_handle: Any = None
        self._prev_sigint_handler: Any = None

    # ---------------------------------------------------------------- git

    def _git_repo_root(self) -> Path | None:
        """Pick the git repo root: project_dir if it has its own .git, else cwd."""
        candidate_dirs = [self.project_dir, Path.cwd()]
        for d in candidate_dirs:
            try:
                out = subprocess.check_output(
                    ["git", "-C", str(d), "rev-parse", "--show-toplevel"],
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                )
                return Path(out.decode().strip())
            except (subprocess.SubprocessError, FileNotFoundError, OSError):
                continue
        return None

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a git command anchored at ``self._git_root``. Raises on failure."""
        assert self._git_root is not None
        return subprocess.run(
            ["git", "-C", str(self._git_root), *args],
            check=check,
            capture_output=True,
            text=True,
        )

    def _ensure_branch(self) -> None:
        """Try to create the tracking branch. On failure, log once and degrade."""
        if shutil.which("git") is None:
            self._warn_git_unavailable("git executable not found")
            return
        root = self._git_repo_root()
        if root is None:
            self._warn_git_unavailable(
                f"no git repo found at {self.project_dir} or cwd"
            )
            return
        self._git_root = root
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._branch_name = f"{self.branch_prefix}/{timestamp}"
        try:
            self._git("checkout", "-b", self._branch_name)
            self._git_available = True
        except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
            self._warn_git_unavailable(f"git checkout failed: {exc!r}")

    def _warn_git_unavailable(self, reason: str) -> None:
        if not self._git_warned:
            logger.warning(
                "ResearchLoop: git checkpoint disabled (%s). The loop will continue "
                "but iterations cannot be reverted via `git reset --hard`.",
                reason,
            )
            self._git_warned = True

    def _git_commit_keep(self, description: str) -> None:
        if not self._git_available:
            return
        try:
            self._git("add", "-A")
            self._git("commit", "-m", f"loop: keep — {description}", check=False)
        except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
            logger.warning("ResearchLoop: git commit failed: %s", exc)

    def _git_reset_discard(self) -> None:
        if not self._git_available:
            return
        try:
            self._git("reset", "--hard", "HEAD")
        except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
            logger.warning("ResearchLoop: git reset failed: %s", exc)

    # ---------------------------------------------------------------- TSV

    def _open_tsv(self) -> None:
        """Open the TSV log, writing the header iff the file is new/empty."""
        self.project_dir.mkdir(parents=True, exist_ok=True)
        is_new = not self.tsv_path.exists() or self.tsv_path.stat().st_size == 0
        # Line-buffered so a hard kill still leaves rows on disk.
        self._tsv_handle = self.tsv_path.open("a", buffering=1)
        if is_new:
            self._tsv_handle.write(_TSV_HEADER)

    def _write_row(self, *, composite: float, status: str, description: str) -> None:
        if self._tsv_handle is None:
            return
        # Sanitize tabs/newlines out of the description so the TSV stays parseable.
        desc = description.replace("\t", " ").replace("\n", " ")
        ts = datetime.now(timezone.utc).isoformat()
        self._tsv_handle.write(
            f"{self._iter}\t{ts}\t{composite:.6f}\t{status}\t{desc}\n"
        )

    def _close_tsv(self) -> None:
        if self._tsv_handle is not None:
            try:
                self._tsv_handle.flush()
                self._tsv_handle.close()
            except Exception:  # noqa: BLE001 — never mask the original exception
                pass
            self._tsv_handle = None

    # ---------------------------------------------------------------- caps

    def _cumulative_cost(self) -> float:
        """Sum cost_usd across every manifest in project_dir/runs/."""
        runs = self.project_dir / "runs"
        if not runs.exists():
            return 0.0
        total = 0.0
        for manifest in runs.rglob("manifest.json"):
            try:
                import json as _json

                payload = _json.loads(manifest.read_text())
                total += float(payload.get("cost_usd", 0.0))
            except (OSError, ValueError):
                continue
        return total

    def _should_stop(self, *, started_at: float) -> str | None:
        if self.max_iters is not None and self._iter >= self.max_iters:
            return f"max_iters reached ({self.max_iters})"
        elapsed_h = (time.monotonic() - started_at) / 3600.0
        if elapsed_h >= self.time_budget_hours:
            return f"time budget exceeded ({elapsed_h:.2f}h >= {self.time_budget_hours}h)"
        cost = self._cumulative_cost()
        if cost >= self.max_cost_usd:
            return f"cost cap reached ({cost:.2f} >= {self.max_cost_usd})"
        return None

    # ---------------------------------------------------------------- SIGINT

    def _handle_interrupt(self, *_: Any) -> None:
        """SIGINT handler: write an ``interrupted`` row, close the TSV, then re-raise."""
        try:
            self._write_row(
                composite=float("nan"),
                status="interrupted",
                description="SIGINT received",
            )
        finally:
            self._close_tsv()
        raise KeyboardInterrupt

    # ---------------------------------------------------------------- run

    async def run(
        self,
        plato_factory: PlatoFactory,
        score_fn: ScoreFn,
    ) -> dict:
        """Execute the loop until a hard cap fires.

        Returns a summary dict::

            {"iterations": int, "kept": int, "discarded": int,
             "best_composite": float, "tsv_path": str}
        """
        self._open_tsv()
        self._ensure_branch()

        try:
            self._prev_sigint_handler = signal.signal(signal.SIGINT, self._handle_interrupt)
        except (ValueError, OSError):
            # signal() raises ValueError if not in main thread; that's fine for tests.
            self._prev_sigint_handler = None

        started_at = time.monotonic()
        try:
            while True:
                stop_reason = self._should_stop(started_at=started_at)
                if stop_reason is not None:
                    logger.info("ResearchLoop: stopping — %s", stop_reason)
                    break

                self._iter += 1
                try:
                    plato = plato_factory()
                    raw = score_fn(plato)
                    score = await raw if inspect.isawaitable(raw) else raw
                    composite = score.composite()
                except Exception as exc:  # noqa: BLE001 — record + continue
                    logger.exception("ResearchLoop: iter %d errored", self._iter)
                    self._write_row(
                        composite=float("nan"),
                        status="error",
                        description=f"{type(exc).__name__}: {exc}",
                    )
                    continue

                if (
                    self._last_accepted_composite is None
                    or composite > self._last_accepted_composite
                ):
                    self._kept += 1
                    self._last_accepted_composite = composite
                    description = (
                        f"composite={composite:.4f} (improved from "
                        f"{self._best_composite if self._best_composite != float('-inf') else 'baseline'})"
                    )
                    self._write_row(
                        composite=composite,
                        status="keep",
                        description=description,
                    )
                    self._git_commit_keep(description)
                else:
                    self._discarded += 1
                    self._write_row(
                        composite=composite,
                        status="discard",
                        description=(
                            f"composite={composite:.4f} <= last accepted "
                            f"{self._last_accepted_composite:.4f}"
                        ),
                    )
                    self._git_reset_discard()

                if composite > self._best_composite:
                    self._best_composite = composite
        finally:
            # Restore the prior SIGINT handler so we don't leak it into the parent process.
            if self._prev_sigint_handler is not None:
                try:
                    signal.signal(signal.SIGINT, self._prev_sigint_handler)
                except (ValueError, OSError):
                    pass
            self._close_tsv()

        return {
            "iterations": self._iter,
            "kept": self._kept,
            "discarded": self._discarded,
            "best_composite": (
                self._best_composite if self._best_composite != float("-inf") else 0.0
            ),
            "tsv_path": str(self.tsv_path),
        }


# ----------------------------------------------------------------- helpers


def latest_manifest_score(project_dir: str | Path) -> AcceptanceScore:
    """Default :class:`ScoreFn` for the CLI.

    Picks the most recently modified ``manifest.json`` under
    ``project_dir/runs/`` and synthesizes an :class:`AcceptanceScore` from
    whatever fields it carries. This is intentionally permissive — the CLI
    just needs *something* to run; richer scoring lives in the eval harness.
    """
    import json

    project_dir = Path(project_dir)
    runs = project_dir / "runs"
    manifests = sorted(runs.rglob("manifest.json"), key=lambda p: p.stat().st_mtime)
    if not manifests:
        # No history → trivially poor score; keeps the loop moving but flags it.
        return AcceptanceScore(
            citation_validation_rate=0.0,
            unsupported_claim_rate=1.0,
            referee_severity_max=None,
            simplicity_delta=0.0,
        )
    payload: dict[str, Any] = json.loads(manifests[-1].read_text())
    extra = payload.get("extra") or {}
    return AcceptanceScore(
        citation_validation_rate=float(extra.get("citation_validation_rate", 0.0)),
        unsupported_claim_rate=float(extra.get("unsupported_claim_rate", 0.0)),
        referee_severity_max=extra.get("referee_severity_max"),
        simplicity_delta=float(extra.get("simplicity_delta", 0.0)),
    )


__all__ = [
    "AcceptanceScore",
    "ResearchLoop",
    "latest_manifest_score",
]
