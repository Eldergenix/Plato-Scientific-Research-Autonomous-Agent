"""Run lifecycle: spawn Plato in a subprocess, stream events back.

Each ``start_run`` forks a ``multiprocessing.get_context('spawn').Process``
(spawn, NOT fork — fork is incompatible with Python 3.13 + cmbagent's
threadpools on macOS). The child puts itself in a fresh process group via
``os.setsid()`` so ``os.killpg`` can reap cmbagent's grandchildren on cancel.

Communication is one-way: the child writes JSONL events to
``project_dir/runs/<run_id>/events.jsonl``; the parent tails that file
(250 ms polling) and republishes lines to the in-memory ``EventBus``.
The child also redirects stdout/stderr through the same JSONL pipe so
Plato's ``print`` calls become structured ``log.line`` events.

The public API mirrors the previous in-process simulator so the FastAPI
server is unchanged: ``start_run``, ``cancel_run``, ``get_run``,
``list_active_runs``, ``count_active_runs``.
"""

from __future__ import annotations

import asyncio
import io
import json
import multiprocessing as mp
import os
import signal
import sys
import time
import traceback
import warnings
from datetime import datetime, timezone
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import Any, Optional

from ..domain.models import ActiveRun, Project, Run, StageId, utcnow
from ..events.bus import EventBus
from ..settings import get_settings
from ..storage.key_store import ENV_KEYS, KeyStore
from ..tooling import disabled_tool_names_for_project_dir

# In-memory state. Promoted to Redis in Phase 2.
_active_runs: dict[str, Run] = {}
_run_tasks: dict[str, asyncio.Task[None]] = {}
_subprocesses: dict[str, BaseProcess] = {}

# Iter-25 defense-in-depth: per-run project_dir override.
#
# The legacy resolution is ``get_settings().project_root / project_id``,
# which lands in the un-namespaced single-user tree. After iter-24's
# ``X-Plato-User`` multi-tenancy work the API server resolves
# project_dir via ``store.project_dir(pid)`` (which honors the per-user
# ``<root>/users/<uid>/<pid>`` namespace), but ``start_run`` ignored
# that and re-derived from settings.project_root. The iter-24 entry-point
# guard blocks the obvious tenant bypass, but the worker still wrote
# events / status into the wrong tree.
#
# This map lets ``start_run`` accept the API-resolved project_dir and
# stash it for downstream callbacks (``_supervise``, ``_write_status``,
# ``cancel_run``). Lookups fall back to the legacy resolution when no
# entry exists — preserving every pre-iter-25 caller (e.g. CLI loop,
# tests) and recovery after a worker restart.
_run_dirs: dict[str, Path] = {}

_SPAWN_CTX = mp.get_context("spawn")
_TAIL_INTERVAL_S = 0.25
_SIGTERM_GRACE_S = 5.0

_STAGE_ARTIFACTS: dict[StageId, tuple[str, ...]] = {
    "data": ("input_files/data_description.md",),
    "idea": ("input_files/idea.md",),
    "literature": ("input_files/literature.md",),
    "method": ("input_files/methods.md",),
    "results": ("input_files/results.md",),
    "paper": ("paper/main.pdf", "paper/main.tex"),
    "referee": ("input_files/referee.md",),
}


# --------------------------------------------------------------------------- #
# Public read API
# --------------------------------------------------------------------------- #
def get_run(run_id: str) -> Optional[Run]:
    """Return the in-memory Run, or None."""
    return _active_runs.get(run_id)


def list_active_runs(project_id: Optional[str] = None) -> list[Run]:
    """List runs, optionally filtered by project."""
    runs = list(_active_runs.values())
    if project_id:
        runs = [r for r in runs if r.project_id == project_id]
    return runs


def count_active_runs() -> int:
    """Count runs in queued or running state."""
    return sum(1 for r in _active_runs.values() if r.status in ("queued", "running"))


# --------------------------------------------------------------------------- #
# Filesystem helpers
# --------------------------------------------------------------------------- #
def _resolve_project_dir(project_id: str) -> Path:
    """Resolve the project directory for ``project_id``.

    Iter-25: consults ``_run_dirs`` first (set by the API server when
    it knows the per-user namespaced path), falling back to the legacy
    ``settings.project_root / project_id`` for callers that don't
    register an override (CLI loop, tests, recovery-after-restart).

    The lookup is keyed by run_id where possible — but several helpers
    only have ``project_id`` in scope, so we also iterate the registry
    looking for any entry whose path ends in ``/<project_id>``. That's
    O(active_runs) which is small enough for the current single-process
    deployment; Phase-2 Redis migration will get a proper index.
    """
    for run_id, project_dir in _run_dirs.items():
        run = _active_runs.get(run_id)
        if run is not None and run.project_id == project_id:
            return project_dir
        # Fallback: match on path basename for runs where the in-memory
        # Run has been GC'd but the override is still live.
        if project_dir.name == project_id:
            return project_dir
    return get_settings().project_root / project_id


def _read_project_user_id(project_dir: Path) -> Optional[str]:
    """Best-effort lookup of ``Project.user_id`` from ``meta.json``.

    Returns ``None`` (single-user / unknown) on any I/O or parse error
    so the budget meter degrades to the ``__local__`` bucket rather
    than blowing up the run finalizer.
    """
    meta_path = project_dir / "meta.json"
    try:
        with meta_path.open() as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    uid = data.get("user_id")
    if isinstance(uid, str) and uid:
        return uid
    return None


def _run_dir(
    project_id: str, run_id: str, project_dir: Optional[Path] = None
) -> Path:
    """Return ``<project_dir>/runs/<run_id>``.

    ``project_dir`` overrides the registry lookup; pass it explicitly
    when the caller already has the per-user-resolved path on hand
    (avoids the registry scan).
    """
    base = project_dir if project_dir is not None else _run_dirs.get(run_id)
    if base is None:
        base = _resolve_project_dir(project_id)
    p = base / "runs" / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _events_path(
    project_id: str, run_id: str, project_dir: Optional[Path] = None
) -> Path:
    return _run_dir(project_id, run_id, project_dir) / "events.jsonl"


def _status_path(
    project_id: str, run_id: str, project_dir: Optional[Path] = None
) -> Path:
    return _run_dir(project_id, run_id, project_dir) / "status.json"


def _write_status(run: Run) -> None:
    """Persist a run's current state to ``status.json``."""
    path = _status_path(run.project_id, run.id)
    payload = {
        "run_id": run.id,
        "project_id": run.project_id,
        "stage": run.stage,
        "status": run.status,
        "pid": run.pid,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "error": run.error,
        "token_input": run.token_input,
        "token_output": run.token_output,
    }
    try:
        path.write_text(json.dumps(payload, indent=2))
    except OSError:
        pass


def _read_project(project_dir: Path) -> Project | None:
    try:
        with (project_dir / "meta.json").open() as f:
            return Project.model_validate(json.load(f))
    except (OSError, ValueError):
        return None


def _write_project(project_dir: Path, project: Project) -> None:
    project.updated_at = utcnow()
    payload = json.dumps(project.model_dump(mode="json"), indent=2, default=str)
    path = project_dir / "meta.json"
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(payload)
        os.replace(tmp, path)
    except OSError:
        pass


def _stage_artifact_exists(project_dir: Path, stage: StageId) -> bool:
    return any((project_dir / rel).is_file() for rel in _STAGE_ARTIFACTS.get(stage, ()))


def _read_input_file(project_dir: Path, name: str) -> str:
    try:
        return (project_dir / "input_files" / name).read_text(encoding="utf-8")
    except OSError:
        return ""


def _select_results_executor(
    project_dir: Path,
    config: dict[str, Any],
    extra: dict[str, Any],
) -> str | None:
    explicit = config.get("executor") or extra.get("executor")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    data_description = _read_input_file(project_dir, "data_description.md")
    combined = "\n".join(
        [
            data_description,
            _read_input_file(project_dir, "idea.md"),
            _read_input_file(project_dir, "methods.md"),
        ]
    ).lower()
    if "synthetic" not in combined:
        return None

    tabular_terms = (
        "tabular",
        "classification",
        "logistic regression",
        "random forest",
        "roc-auc",
        "roc auc",
        "calibration",
    )
    if not any(term in combined for term in tabular_terms):
        return None

    try:
        from plato.utils import extract_file_paths

        existing_paths, missing_paths = extract_file_paths(data_description)
    except Exception:  # noqa: BLE001 - heuristic should never fail a run
        existing_paths = []
        missing_paths = []
    if existing_paths or missing_paths:
        return None

    return "sklearn_synthetic"


def _config_or_extra(
    config: dict[str, Any],
    extra: dict[str, Any],
    key: str,
    default: Any = None,
) -> Any:
    if key in config:
        return config[key]
    if key in extra:
        return extra[key]
    return default


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        return default
    return bool(value)


def _set_project_run_started(run: Run, project_dir: Path) -> None:
    project = _read_project(project_dir)
    if project is None:
        return
    project.active_run = ActiveRun(
        run_id=run.id,
        stage=run.stage,
        started_at=run.started_at or utcnow(),
    )
    stage = project.stages.get(run.stage)
    if stage is not None:
        stage.status = "running"
        stage.progress_label = "Running"
    _write_project(project_dir, project)


def _set_project_run_finished(run: Run, project_dir: Path) -> None:
    project = _read_project(project_dir)
    if project is None:
        return

    if project.active_run and project.active_run.run_id == run.id:
        project.active_run = None

    stage = project.stages.get(run.stage)
    if stage is not None:
        stage.progress_label = None
        if run.status == "succeeded":
            if _stage_artifact_exists(project_dir, run.stage):
                stage.status = "done"
                stage.origin = "ai"
                stage.last_run_at = run.finished_at or utcnow()
                models = run.config.get("models") if isinstance(run.config, dict) else None
                if isinstance(models, dict):
                    selected = models.get(run.stage) or models.get("llm")
                    if isinstance(selected, str) and selected:
                        stage.model = selected
            else:
                run.status = "failed"
                run.error = run.error or (
                    f"{run.stage} run finished without writing the expected artifact"
                )
                stage.status = "failed"
        elif run.status == "cancelled":
            stage.status = "failed"
        elif run.status == "failed":
            stage.status = "failed"

    try:
        from .token_tracker import aggregate_project_usage

        usage = aggregate_project_usage(project_dir)
        project.total_tokens = usage.total_input + usage.total_output
        project.total_cost_cents = usage.total_cost_cents
    except Exception:  # noqa: BLE001
        pass

    _write_project(project_dir, project)
    _write_status(run)


def _resolve_keys() -> dict[str, str]:
    """Pull API keys from KeyStore + env, mapped to env-var names Plato reads."""
    settings = get_settings()
    store = KeyStore(settings.keys_path)
    out: dict[str, str] = {}
    for provider, env_var in ENV_KEYS.items():
        val = store.resolve(provider)
        if val:
            out[env_var] = val
    return out


def _normalize_model_config_for_keys(config: dict, env_keys: dict[str, str]) -> dict:
    """Choose an available default LLM when the request omits one.

    Plato's idea workflow defaults its base ``llm`` to Gemini. Hosted
    deployments often have multiple provider keys, and the free Gemini quota
    is easy to exhaust, so prefer OpenAI when available. Keep caller-supplied
    models untouched; only fill the missing base model.
    """
    models = dict(config.get("models") or {})
    if "llm" not in models and env_keys.get("OPENAI_API_KEY"):
        models["llm"] = "gpt-4.1-mini"
    if models == (config.get("models") or {}):
        return config
    normalized = dict(config)
    normalized["models"] = models
    return normalized


# --------------------------------------------------------------------------- #
# Child-side: event emitter and stdout shim
# --------------------------------------------------------------------------- #
class _EventWriter:
    """JSONL writer used inside the child subprocess."""

    def __init__(self, path: Path):
        self.path = path
        self._fh = path.open("a", buffering=1, encoding="utf-8")

    def emit(self, kind: str, **fields: Any) -> None:
        line = {
            "kind": kind,
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            **fields,
        }
        try:
            self._fh.write(json.dumps(line, default=str) + "\n")
            self._fh.flush()
        except (OSError, ValueError):
            pass

    def close(self) -> None:
        try:
            self._fh.close()
        except OSError:
            pass


class _LogStream(io.TextIOBase):
    """File-like that converts writes into ``log.line`` events."""

    def __init__(self, writer: _EventWriter, source: str, level: str):
        self._writer = writer
        self._source = source
        self._level = level
        self._buf = ""

    def writable(self) -> bool:  # noqa: D401
        return True

    def write(self, s: str) -> int:
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip() and not _should_drop_log_line(line):
                self._writer.emit(
                    "log.line",
                    source=self._source,
                    agent=None,
                    level=self._level,
                    text=line.rstrip(),
                )
        return len(s)

    def flush(self) -> None:  # noqa: D401
        if self._buf.strip() and not _should_drop_log_line(self._buf):
            self._writer.emit(
                "log.line",
                source=self._source,
                agent=None,
                level=self._level,
                text=self._buf.rstrip(),
            )
        self._buf = ""


def _should_drop_log_line(line: str) -> bool:
    """Hide noisy third-party warnings that do not require user action."""
    return (
        "LangChainPendingDeprecationWarning" in line
        and "allowed_objects" in line
    ) or "from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer" in line


# --------------------------------------------------------------------------- #
# Child entry point (must be top-level for spawn pickling)
# --------------------------------------------------------------------------- #
def _child_main(
    project_id: str,
    run_id: str,
    stage: StageId,
    config: dict,
    project_dir: str,
    events_file: str,
    env_keys: dict[str, str],
) -> None:
    """Subprocess entry point. Imports Plato, dispatches on stage, emits events."""
    warnings.filterwarnings(
        "ignore",
        message=r"The default value of `allowed_objects` will change in a future version\..*",
        category=Warning,
    )

    # Detach: own session/process group so killpg reaps cmbagent grandchildren.
    try:
        os.setsid()
    except OSError:
        pass

    # Apply API keys before importing Plato (KeyManager.get_keys_from_env reads them).
    for env_var, value in env_keys.items():
        if value:
            os.environ[env_var] = value
    python_bin = str(Path(sys.executable).parent)
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    if python_bin and python_bin not in path_parts:
        os.environ["PATH"] = os.pathsep.join([python_bin, *path_parts])
    os.environ.setdefault("PYTHON", sys.executable)

    writer = _EventWriter(Path(events_file))
    sys.stdout = _LogStream(writer, source=stage, level="info")
    sys.stderr = _LogStream(writer, source=stage, level="warn")

    writer.emit("stage.started", run_id=run_id, project_id=project_id, stage=stage, config=config)

    try:
        try:
            from plato.plato import Plato
            from plato.paper_agents.journal import Journal
        except ImportError as exc:
            writer.emit(
                "error",
                run_id=run_id,
                project_id=project_id,
                stage=stage,
                message=(
                    "Plato is not installed in this environment "
                    f"(import failed: {exc}). Run `pip install plato` "
                    "in the same venv as the worker."
                ),
            )
            writer.emit("stage.finished", run_id=run_id, project_id=project_id, stage=stage, status="failed")
            writer.close()
            return

        plato = Plato(project_dir=project_dir, clear_project_dir=False)

        models_cfg: dict[str, str] = config.get("models") or {}
        mode: str = config.get("mode", "fast")
        extra: dict = config.get("extra") or {}

        def _kw(*allowed: str) -> dict[str, str]:
            return {k: v for k, v in models_cfg.items() if k in allowed and v}

        if stage == "data":
            if config.get("enhance") or extra.get("enhance"):
                summarizer = models_cfg.get("summarizer") or "gpt-4o"
                formatter = models_cfg.get("formatter") or "o3-mini"
                plato.enhance_data_description(
                    summarizer_model=summarizer,
                    summarizer_response_formatter_model=formatter,
                )
            else:
                print("data stage: no-op (description already saved by frontend)")

        elif stage == "idea":
            extra["skip_clarification"] = extra.get("skip_clarification", True)
            kwargs = _kw(
                "llm",
                "idea_maker_model",
                "idea_hater_model",
                "planner_model",
                "plan_reviewer_model",
                "orchestration_model",
                "formatter_model",
            )
            plato.get_idea(
                mode=mode,
                skip_clarification=bool(extra.get("skip_clarification")),
                **kwargs,
            )

        elif stage == "method":
            kwargs = _kw(
                "llm",
                "method_generator_model",
                "planner_model",
                "plan_reviewer_model",
                "orchestration_model",
                "formatter_model",
            )
            plato.get_method(mode=mode, **kwargs)

        elif stage == "results":
            planning_data_dir = Path(project_dir) / "experiment_generation_output" / "planning" / "data"
            planning_data_dir.mkdir(parents=True, exist_ok=True)
            (planning_data_dir / ".keep").touch(exist_ok=True)
            kwargs = _kw(
                "engineer_model",
                "researcher_model",
                "planner_model",
                "plan_reviewer_model",
                "orchestration_model",
                "formatter_model",
            )
            agents = config.get("agents") or extra.get("agents") or ["engineer", "researcher"]
            max_steps = int(config.get("max_steps") or extra.get("max_steps") or 6)
            max_attempts = int(config.get("max_attempts") or extra.get("max_attempts") or 10)
            restart_at = int(config.get("restart_at_step") or extra.get("restart_at_step") or -1)
            hardware = config.get("hardware_constraints") or extra.get("hardware_constraints")
            executor_name = _select_results_executor(Path(project_dir), config, extra)
            if executor_name:
                print(f"results stage: using executor {executor_name}")
            plato.get_results(
                involved_agents=list(agents),
                max_n_steps=max_steps,
                max_n_attempts=max_attempts,
                restart_at_step=restart_at,
                hardware_constraints=hardware,
                executor=executor_name,
                **kwargs,
            )
            # Iter-30: fan executor cell records out as code.execute
            # events so the frontend CodePane can render the actual
            # per-cell source / stdout / error. Plato.get_results
            # stashes the executor's ``cells`` artifacts list on the
            # instance for exactly this purpose. Synthesised after the
            # executor returns rather than during execution because the
            # executor.run protocol doesn't currently take an
            # event-emitter callback (and adding one would be a much
            # heavier refactor across cmbagent/local_jupyter/modal/e2b).
            artifacts = getattr(plato, "executor_artifacts", None) or {}
            cells = artifacts.get("cells") if isinstance(artifacts, dict) else None
            if isinstance(cells, list):
                for cell in cells:
                    if not isinstance(cell, dict):
                        continue
                    payload: dict[str, Any] = {
                        "run_id": run_id,
                        "project_id": project_id,
                        "stage": stage,
                        "index": cell.get("index"),
                        "source": cell.get("source"),
                        "stdout": cell.get("stdout"),
                        "stderr": cell.get("stderr"),
                        "executor": artifacts.get("executor"),
                    }
                    err = cell.get("error")
                    if isinstance(err, dict):
                        payload["error"] = {
                            "ename": err.get("ename"),
                            "evalue": err.get("evalue"),
                        }
                    writer.emit("code.execute", **payload)

        elif stage == "paper":
            journal_name = _config_or_extra(config, extra, "journal", "NONE") or "NONE"
            try:
                journal = Journal[journal_name] if isinstance(journal_name, str) else Journal(journal_name)
            except (KeyError, ValueError):
                journal = Journal.NONE
            paper_kwargs: dict[str, Any] = {}
            if models_cfg.get("llm"):
                paper_kwargs["llm"] = models_cfg["llm"]
            max_revision_iters = int(
                _config_or_extra(
                    config,
                    extra,
                    "max_revision_iters",
                    _config_or_extra(config, extra, "iterations", 2),
                )
                or 0
            )
            plato.get_paper(
                journal=journal,
                writer=_config_or_extra(config, extra, "writer", "scientist"),
                add_citations=_coerce_bool(
                    _config_or_extra(config, extra, "add_citations", True),
                    default=True,
                ),
                cmbagent_keywords=_coerce_bool(
                    _config_or_extra(config, extra, "cmbagent_keywords", False),
                    default=False,
                ),
                max_revision_iters=max_revision_iters,
                **paper_kwargs,
            )

        elif stage == "referee":
            referee_kwargs: dict[str, Any] = {}
            if models_cfg.get("referee"):
                referee_kwargs["llm"] = models_cfg["referee"]
            elif models_cfg.get("llm"):
                referee_kwargs["llm"] = models_cfg["llm"]
            plato.referee(**referee_kwargs)

        elif stage == "literature":
            lit_provider = config.get("lit_provider") or extra.get("lit_provider") or "semantic_scholar"
            literature_kwargs: dict[str, Any] = {"mode": lit_provider}
            if models_cfg.get("llm"):
                literature_kwargs["llm"] = models_cfg["llm"]
            max_iterations = _config_or_extra(
                config,
                extra,
                "max_iterations",
                _config_or_extra(config, extra, "iterations", None),
            )
            if max_iterations is not None:
                literature_kwargs["max_iterations"] = int(max_iterations)
            plato.check_idea(**literature_kwargs)

        else:
            raise ValueError(f"Unknown stage: {stage}")

        writer.emit("stage.finished", run_id=run_id, project_id=project_id, stage=stage, status="succeeded")

    except KeyboardInterrupt:
        writer.emit("stage.finished", run_id=run_id, project_id=project_id, stage=stage, status="cancelled")
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        writer.emit(
            "error",
            run_id=run_id,
            project_id=project_id,
            stage=stage,
            message=str(exc),
            traceback=tb,
        )
        writer.emit("stage.finished", run_id=run_id, project_id=project_id, stage=stage, status="failed")
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:  # noqa: BLE001
            pass
        writer.close()


# --------------------------------------------------------------------------- #
# Parent-side: tail events.jsonl and republish to bus
# --------------------------------------------------------------------------- #
async def _tail_events(run: Run, bus: EventBus, events_file: Path) -> None:
    """Poll the JSONL pipe and republish each line to the bus."""
    last_size = 0
    buf = ""
    finished_seen = False

    while not finished_seen:
        try:
            if events_file.exists():
                size = events_file.stat().st_size
                if size > last_size:
                    with events_file.open("r", encoding="utf-8") as fh:
                        fh.seek(last_size)
                        chunk = fh.read()
                        last_size = fh.tell()
                    buf += chunk
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            evt = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        evt.setdefault("run_id", run.id)
                        evt.setdefault("project_id", run.project_id)
                        evt.setdefault("stage", run.stage)
                        await bus.publish(f"run:{run.id}", evt)

                        kind = evt.get("kind")
                        if kind == "stage.started" and run.status == "queued":
                            run.status = "running"
                            _write_status(run)
                        elif kind == "tokens.delta":
                            prompt_tok = int(evt.get("prompt", 0) or 0)
                            completion_tok = int(evt.get("completion", 0) or 0)
                            run.token_input += prompt_tok
                            run.token_output += completion_tok
                            # Lazy import to avoid circular-import risk.
                            from .token_tracker import record_tokens_delta
                            record_tokens_delta(
                                run_id=run.id,
                                model=str(evt.get("model", "")),
                                prompt_tok=prompt_tok,
                                completion_tok=completion_tok,
                            )
                        elif kind == "error":
                            run.error = evt.get("message")
                        elif kind == "stage.finished":
                            run.status = evt.get("status", "failed")
                            run.finished_at = utcnow()
                            # Reconcile the live ledger with the canonical
                            # on-disk LLM_calls.txt for this stage.
                            try:
                                from .token_tracker import reconcile_run
                                # Iter-25: prefer the per-user override
                                # if the API server registered one; fall
                                # back to legacy resolution otherwise.
                                project_dir = _run_dirs.get(
                                    run.id
                                ) or (get_settings().project_root / run.project_id)
                                reconciled = reconcile_run(
                                    run.id, project_dir, run.stage
                                )
                                # Feed the per-user budget meter so
                                # ``require_under_budget`` actually
                                # bites in demo mode. user_id lives in
                                # the project's meta.json next to the
                                # run dir; missing/unreadable meta
                                # falls back to the single-user
                                # ``__local__`` bucket.
                                try:
                                    from .session_costs import add_session_cost
                                    user_id = _read_project_user_id(project_dir)
                                    add_session_cost(
                                        user_id, reconciled.cost_cents
                                    )
                                except Exception:  # noqa: BLE001
                                    pass
                            except Exception:  # noqa: BLE001
                                pass
                            project_dir = _run_dirs.get(
                                run.id
                            ) or (get_settings().project_root / run.project_id)
                            _set_project_run_finished(run, project_dir)
                            finished_seen = True
                            break
        except OSError:
            pass

        proc = _subprocesses.get(run.id)
        if proc is not None and not proc.is_alive() and not finished_seen:
            # Drain anything left, then synthesize a finish event.
            await asyncio.sleep(_TAIL_INTERVAL_S)
            if events_file.exists() and events_file.stat().st_size > last_size:
                continue
            exit_code = proc.exitcode
            if run.status not in ("succeeded", "failed", "cancelled"):
                if exit_code == 0:
                    run.status = "succeeded"
                elif exit_code is not None and exit_code < 0:
                    run.status = "cancelled"
                else:
                    run.status = "failed"
                    run.error = run.error or f"subprocess exited with code {exit_code}"
                run.finished_at = utcnow()
                project_dir = _run_dirs.get(run.id) or (
                    get_settings().project_root / run.project_id
                )
                _set_project_run_finished(run, project_dir)
                await bus.publish(
                    f"run:{run.id}",
                    {
                        "kind": "stage.finished",
                        "run_id": run.id,
                        "project_id": run.project_id,
                        "stage": run.stage,
                        "status": run.status,
                        "ts": utcnow().isoformat(),
                    },
                )
            finished_seen = True
            break

        await asyncio.sleep(_TAIL_INTERVAL_S)


# --------------------------------------------------------------------------- #
# Supervisor coroutine (one per run)
# --------------------------------------------------------------------------- #
async def _supervise(run: Run, bus: EventBus, events_file: Path) -> None:
    proc = _subprocesses[run.id]
    try:
        await _tail_events(run, bus, events_file)
        # Make sure the process has fully exited before we drop our handle.
        await asyncio.to_thread(proc.join)
        await asyncio.to_thread(proc.close)
    except asyncio.CancelledError:
        await _terminate_process(run.id, proc)
        run.status = "cancelled"
        run.finished_at = utcnow()
        _write_status(run)
        await bus.publish(
            f"run:{run.id}",
            {
                "kind": "stage.finished",
                "run_id": run.id,
                "project_id": run.project_id,
                "stage": run.stage,
                "status": "cancelled",
                "ts": utcnow().isoformat(),
            },
        )
        raise
    finally:
        _subprocesses.pop(run.id, None)
        _run_tasks.pop(run.id, None)
        _run_dirs.pop(run.id, None)


async def _terminate_process(run_id: str, proc: BaseProcess) -> None:
    """SIGTERM the child's process group, escalate to SIGKILL after grace."""
    pid = proc.pid
    if pid is None:
        return
    try:
        pgid = os.getpgid(pid)
    except (ProcessLookupError, OSError):
        pgid = pid

    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.terminate()
        except (ProcessLookupError, OSError):
            return

    deadline = time.monotonic() + _SIGTERM_GRACE_S
    while proc.is_alive() and time.monotonic() < deadline:
        await asyncio.sleep(0.1)

    if proc.is_alive():
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except (ProcessLookupError, OSError):
                pass

    await asyncio.to_thread(proc.join, 2.0)


# --------------------------------------------------------------------------- #
# Public lifecycle API
# --------------------------------------------------------------------------- #
async def start_run(
    project_id: str,
    stage: StageId,
    config: dict,
    bus: EventBus,
    project_dir: Optional[Path] = None,
) -> Run:
    """Spawn a Plato subprocess for the given stage and start streaming events.

    Iter-25: ``project_dir`` is the new (optional) parameter. When the
    API server has resolved the per-user-namespaced path via
    ``store.project_dir(pid)``, it MUST pass that here so the worker
    writes events / status / artifacts into the right tree. When None
    (e.g. CLI callers, tests), fall back to the legacy
    ``settings.project_root / project_id`` resolution to preserve every
    pre-iter-25 entry point.
    """
    run = Run(
        project_id=project_id,
        stage=stage,
        mode=config.get("mode", "fast"),
        config=config,
        status="queued",
        started_at=utcnow(),
    )

    resolved_project_dir = (
        project_dir
        if project_dir is not None
        else get_settings().project_root / project_id
    )
    # Stash the resolved path before any helper call so downstream
    # ``_run_dir`` / ``_events_path`` / ``_status_path`` consultations
    # see the override (they look up by run_id).
    _run_dirs[run.id] = resolved_project_dir
    events_file = _events_path(project_id, run.id, resolved_project_dir)
    # Truncate any stale pipe from an earlier identically-named run.
    events_file.write_text("")

    env_keys = _resolve_keys()
    disabled_tools = disabled_tool_names_for_project_dir(
        resolved_project_dir,
        get_settings().project_root,
    )
    if disabled_tools:
        env_keys["PLATO_DISABLED_TOOLS"] = ",".join(disabled_tools)
    config = _normalize_model_config_for_keys(config, env_keys)
    run.config = config

    proc = _SPAWN_CTX.Process(
        target=_child_main,
        name=f"plato-{stage}-{run.id}",
        args=(
            project_id,
            run.id,
            stage,
            config,
            str(resolved_project_dir),
            str(events_file),
            env_keys,
        ),
        daemon=False,
    )
    proc.start()
    run.pid = proc.pid
    run.status = "running"

    _active_runs[run.id] = run
    _subprocesses[run.id] = proc
    _set_project_run_started(run, resolved_project_dir)
    _write_status(run)

    task = asyncio.create_task(_supervise(run, bus, events_file))
    _run_tasks[run.id] = task
    return run


async def cancel_run(run_id: str) -> bool:
    """Terminate the subprocess and mark the run as cancelled."""
    proc = _subprocesses.get(run_id)
    task = _run_tasks.get(run_id)
    run = _active_runs.get(run_id)
    if run is None:
        return False
    if run.status not in ("queued", "running"):
        return False

    if proc is not None and proc.is_alive():
        await _terminate_process(run_id, proc)

    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    if run.status not in ("succeeded", "failed", "cancelled"):
        run.status = "cancelled"
        run.finished_at = utcnow()
        _write_status(run)
    # Iter-25: drop the project_dir override now that the run has
    # ended. The Run + subprocess + task entries in their respective
    # registries are already cleaned by the supervise task on exit;
    # the override map needs the same lifecycle.
    _run_dirs.pop(run_id, None)
    return True
