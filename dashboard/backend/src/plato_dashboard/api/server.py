from __future__ import annotations
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..auth import auth_required, extract_user_id
from ..domain.models import (
    Capabilities,
    CreateProjectRequest,
    KeysPayload,
    Project,
    Run,
    StageContent,
    StageId,
    StageRunRequest,
    WriteStageRequest,
)
from ..events.bus import EventBus, get_bus
from ..settings import Settings, get_settings
from ..storage.key_store import KeyStore
from ..storage.project_store import ProjectStore
from ..worker.run_manager import (
    cancel_run,
    count_active_runs,
    get_run,
    list_active_runs,
    start_run,
)
from .capabilities import (
    get_capabilities,
    require_stage_allowed,
    require_under_budget,
)
from .manifests import router as manifests_router

# Frontend pass routers — see streams F1, F2, F4, F6, F7, F8, F9, F10, F11+F12.
# (F5's citation_graph_view router is auto-mounted by api/__init__.py.)
from .auth_endpoints import router as auth_router
from .citation_graph_view import router as citation_graph_router
from .evals_view import router as evals_router
from .clarifications import router as clarifications_router
from .critiques import router as critiques_router
from .domains import router as domains_router
from .executor_preferences import router as executor_preferences_router
from .executors import router as executors_router
from .license_audit_view import router as license_audit_router
from .loop_control import router as loop_router
from .novelty import router as novelty_router
from .research_signals import router as research_signals_router
from .retrieval_summary import router as retrieval_summary_router
from .user_preferences import router as user_preferences_router
from .idea_history import router as idea_history_router
from .cost_caps import router as cost_caps_router
from .approvals import router as approvals_router, compute_blocking_approval


def _resolve_project_root(settings: Settings, user_id: str | None) -> Path:
    """Per-user namespace under ``~/.plato/users/<user_id>/`` when authed.

    Falls back to ``settings.project_root`` (the legacy single-user path)
    when ``user_id`` is None so single-user installs keep their existing
    on-disk layout untouched.
    """
    if user_id is None:
        return settings.project_root
    base = settings.project_root.parent  # ~/.plato/
    return base / "users" / user_id


def _get_user_id(request: Request) -> str | None:
    """Resolve the requester's user id (None in legacy single-user mode)."""
    return extract_user_id(request)


def _get_store(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> ProjectStore:
    user_id = _get_user_id(request)
    if auth_required() and user_id is None:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "auth_required",
                "message": "Missing required header 'X-Plato-User'.",
            },
        )
    root = _resolve_project_root(settings, user_id)
    # Bind the store to the resolved tenant so ProjectStore._check_tenant
    # actually fires inside load/delete/read_stage/_write_stage_async.
    # Without this, the iter-2 tenant guard short-circuits at the
    # ``self.user_id is None`` early-return and routers stay solely
    # responsible for cross-tenant isolation. See storage/project_store.py.
    return ProjectStore(root, user_id=user_id)


def _get_keys(settings: Settings = Depends(get_settings)) -> KeyStore:
    return KeyStore(settings.keys_path)


def _load_run_manifest_user(project_dir: Path, run_id: str) -> str | None:
    """Read ``user_id`` from a run's manifest.json. Returns None on miss."""
    manifest_path = project_dir / "runs" / run_id / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        with manifest_path.open() as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    user = payload.get("user_id")
    return user if isinstance(user, str) else None


def _enforce_project_tenant(
    store: ProjectStore, pid: str, requester_user_id: str | None
) -> None:
    """Refuse cross-tenant project access at the API entry point.

    The directory layout (``<base>/users/<uid>/<pid>``) already isolates
    tenants for code paths that go through ``_get_store`` — but several
    endpoints (``run_stage``, ``list_runs``, ``list_plots``,
    ``get_file``) don't, and ``run_manager.start_run`` resolves
    ``project_dir`` from ``settings.project_root / pid`` directly,
    landing in the legacy un-namespaced tree. This guard short-circuits
    the request before it reaches the worker, so iter-24 closes the
    cross-tenant launch bypass without a deeper run_manager refactor.

    Behaviour matrix (mirrors ``_enforce_run_tenant``):

    - Legacy single-user mode (requester=None, ``auth_required()`` is
      False): no-op. Existing un-namespaced installs keep working.
    - Required-mode (``auth_required()`` is True): the project's
      ``meta.json`` must exist under the requester's namespace AND
      its ``user_id`` must match. Anything else → 403.
    - Not-required-mode + header present: best-effort match. A project
      missing user_id (pre-iter-24 legacy) is allowed (backwards
      compat). A project whose user_id disagrees → 404 (avoid leaking
      existence).
    """
    from ..auth import auth_required as _auth_required

    if requester_user_id is None and not _auth_required():
        return

    required = _auth_required()

    try:
        proj = store.load(pid)
    except FileNotFoundError:
        # Project doesn't exist in the requester's namespace. In
        # required-mode this is a tenant violation (or the project
        # doesn't exist at all — same response either way). In
        # not-required-mode return 404 so we don't leak existence.
        raise HTTPException(
            status_code=403 if required else 404,
            detail={
                "code": "project_forbidden" if required else "project_not_found",
                "pid": pid,
            },
        )

    owner = proj.user_id
    if owner is None:
        # Legacy project (no user_id field). In required-mode this is
        # a tenant violation (we can't prove ownership, fail closed).
        # In not-required-mode this is a pre-iter-24 project visible to
        # any authed user — same as the existing _enforce_run_tenant
        # contract for legacy runs.
        if required:
            raise HTTPException(
                status_code=403,
                detail={"code": "project_forbidden", "pid": pid},
            )
        return

    if owner != requester_user_id:
        raise HTTPException(
            status_code=403 if required else 404,
            detail={
                "code": "project_forbidden" if required else "project_not_found",
                "pid": pid,
            },
        )


def _enforce_run_tenant(
    project_dir: Path, run_id: str, requester_user_id: str | None
) -> None:
    """Refuse cross-tenant run access when the requester has an authed id.

    Behaviour matrix:

    - Legacy single-user mode (``requester_user_id`` is None and
      ``auth_required()`` is False): no-op. Existing un-namespaced
      installs keep working.
    - Required-mode (``auth_required()`` is True): the manifest under
      the requester's ``project_dir`` must exist and its ``user_id``
      must match. Anything else is a tenant boundary violation and we
      raise 403 — the in-memory run registry is shared across tenants,
      so we cannot let a user fetch a run whose manifest doesn't live
      under their own namespace.
    - Not-required-mode but header present: best-effort match. If no
      manifest is on disk yet (very early in a run's life) we fall
      through; if it exists and disagrees, 404 to avoid leaking the
      run's existence to an unauthenticated probe.
    """
    from ..auth import auth_required as _auth_required

    if requester_user_id is None and not _auth_required():
        return

    manifest_user = _load_run_manifest_user(project_dir, run_id)
    required = _auth_required()

    if manifest_user is None:
        if required:
            # No manifest under the requester's project_dir means either
            # the run doesn't belong to them, or it was started before
            # multi-tenant mode landed. Either way, fail closed.
            raise HTTPException(
                status_code=403,
                detail={"code": "run_forbidden"},
            )
        return

    if manifest_user != requester_user_id:
        status_code = 403 if required else 404
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": "run_forbidden" if status_code == 403 else "run_not_found"
            },
        )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
    # Single source of truth for the dashboard's logging stack. This
    # also caps LangChain / httpx / openai / langfuse loggers at
    # WARNING so the worker process doesn't drown the operator in
    # framework chatter, and exposes the run_id contextvar so a
    # future per-request middleware can set it for log correlation.
    from plato.logging_config import configure_logging

    configure_logging()

    settings = get_settings()
    logger = logging.getLogger(__name__)
    logger.info(
        "Plato Dashboard starting on http://%s:%s", settings.host, settings.port
    )
    logger.info("  project root: %s", settings.project_root)
    logger.info(
        "  demo mode: %s · auth: %s", settings.demo_mode, settings.auth
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Plato Dashboard API", version="0.1.0", lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Per-request run_id correlation. Reads ``X-Plato-Run-Id`` (set by
    # the frontend on every fetch via use-project / loop-api) and binds
    # it to the run_id contextvar so every log record emitted under
    # this request — including from worker threads spawned via
    # ``asyncio.to_thread`` — carries the same correlation key.
    @app.middleware("http")
    async def _bind_run_id(request: Request, call_next):  # noqa: ANN001
        from plato.logging_config import run_id_var

        rid = request.headers.get("X-Plato-Run-Id") or ""
        token = run_id_var.set(rid or None)
        try:
            return await call_next(request)
        finally:
            run_id_var.reset(token)

    app.include_router(manifests_router, prefix="/api/v1", tags=["manifests"])

    # Frontend-pass routers. ``loop_router`` already declares its own
    # ``/api/v1/loop`` prefix so we mount it at root; the others are
    # prefix-less and get ``/api/v1`` here.
    app.include_router(auth_router, prefix="/api/v1", tags=["auth"])
    app.include_router(citation_graph_router, prefix="/api/v1", tags=["citations"])
    app.include_router(evals_router, prefix="/api/v1", tags=["evals"])
    app.include_router(clarifications_router, prefix="/api/v1", tags=["clarifications"])
    app.include_router(critiques_router, prefix="/api/v1", tags=["critiques"])
    app.include_router(domains_router, prefix="/api/v1", tags=["domains"])
    app.include_router(executors_router, prefix="/api/v1", tags=["executors"])
    app.include_router(executor_preferences_router, prefix="/api/v1", tags=["preferences"])
    app.include_router(license_audit_router, prefix="/api/v1", tags=["licenses"])
    app.include_router(loop_router)  # already prefixed with /api/v1/loop
    app.include_router(novelty_router, prefix="/api/v1", tags=["novelty"])
    app.include_router(research_signals_router, prefix="/api/v1", tags=["research_signals"])
    app.include_router(retrieval_summary_router, prefix="/api/v1", tags=["retrieval"])
    app.include_router(user_preferences_router, prefix="/api/v1", tags=["preferences"])
    app.include_router(idea_history_router, prefix="/api/v1", tags=["idea_history"])
    app.include_router(cost_caps_router, prefix="/api/v1", tags=["cost_caps"])
    app.include_router(approvals_router, prefix="/api/v1", tags=["approvals"])

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"ok": True, "demo_mode": settings.is_demo}

    @app.get("/api/v1/capabilities", response_model=Capabilities)
    def capabilities(caps: Capabilities = Depends(get_capabilities)) -> Capabilities:
        return caps

    # ------------------------------------------------------------ projects
    @app.get("/api/v1/projects", response_model=list[Project])
    def list_projects(store: ProjectStore = Depends(_get_store)) -> list[Project]:
        return store.list_projects()

    @app.post("/api/v1/projects", response_model=Project, status_code=201)
    def create_project(
        body: CreateProjectRequest,
        request: Request,
        store: ProjectStore = Depends(_get_store),
    ) -> Project:
        # Iter-24: bind the new project to the requester. Required-mode
        # forces a non-None user_id (``_get_store`` already 401s on
        # missing header, so by the time we land here ``user_id`` is
        # set). In not-required-mode the project gets ``user_id=None``
        # which keeps the legacy single-user shape on disk.
        return store.create(
            name=body.name,
            initial_data_description=body.data_description,
            user_id=_get_user_id(request),
            journal=body.journal,
        )

    @app.get("/api/v1/projects/{pid}", response_model=Project)
    def get_project(
        pid: str,
        request: Request,
        store: ProjectStore = Depends(_get_store),
    ) -> Project:
        _enforce_project_tenant(store, pid, _get_user_id(request))
        try:
            return store.load(pid)
        except FileNotFoundError as exc:
            raise HTTPException(404, detail={"code": "project_not_found"}) from exc

    @app.delete("/api/v1/projects/{pid}", status_code=204)
    def delete_project(
        pid: str,
        request: Request,
        store: ProjectStore = Depends(_get_store),
    ) -> None:
        _enforce_project_tenant(store, pid, _get_user_id(request))
        store.delete(pid)

    # ------------------------------------------------------------ stages
    @app.get("/api/v1/projects/{pid}/state/{stage}", response_model=StageContent | None)
    async def read_stage(
        pid: str,
        stage: StageId,
        request: Request,
        store: ProjectStore = Depends(_get_store),
    ) -> StageContent | None:
        _enforce_project_tenant(store, pid, _get_user_id(request))
        return await store.read_stage(pid, stage)

    @app.put("/api/v1/projects/{pid}/state/{stage}", response_model=StageContent)
    async def write_stage(
        pid: str,
        stage: StageId,
        body: WriteStageRequest,
        request: Request,
        store: ProjectStore = Depends(_get_store),
        caps: Capabilities = Depends(get_capabilities),
    ) -> StageContent:
        _enforce_project_tenant(store, pid, _get_user_id(request))
        require_stage_allowed(stage, caps)
        return await store.write_stage(pid, stage, body.markdown, origin="edited")

    # ------------------------------------------------------------ runs
    @app.post("/api/v1/projects/{pid}/stages/{stage}/run", response_model=Run, status_code=202)
    async def run_stage(
        pid: str,
        stage: StageId,
        run_request: StageRunRequest,
        request: Request,
        bus: EventBus = Depends(get_bus),
        store: ProjectStore = Depends(_get_store),
        caps: Capabilities = Depends(get_capabilities),
    ) -> Run:
        # Iter-24 SECURITY: enforce tenant ownership BEFORE consulting
        # ``count_active_runs`` or invoking ``start_run`` so a
        # cross-tenant pid never lands a queued/running entry in the
        # in-memory registry (which is shared across all tenants).
        _enforce_project_tenant(store, pid, _get_user_id(request))
        # Iter-26: per-project cost cap gate. The cost-meter-panel UI
        # used to enforce this client-side via a localStorage flag,
        # which a malicious client could trivially bypass by editing
        # localStorage. Now the backend reads ``project.cost_caps``
        # (persisted on meta.json by the ``/cost_caps`` endpoint) and
        # refuses to launch new runs when the project's accumulated
        # spend has reached the configured ceiling.
        try:
            proj = store.load(pid)
        except FileNotFoundError as exc:
            raise HTTPException(
                404, detail={"code": "project_not_found"}
            ) from exc
        cap = proj.cost_caps
        if (
            cap is not None
            and cap.stop_on_exceed
            and cap.budget_cents is not None
            and proj.total_cost_cents >= cap.budget_cents
        ):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "budget_exceeded",
                    "message": (
                        "Project budget exceeded — increase the cap or "
                        "disable the hard-stop in /cost_caps before "
                        "launching new runs."
                    ),
                    "spent_cents": proj.total_cost_cents,
                    "budget_cents": cap.budget_cents,
                },
            )
        # Iter-27: server-side approval gate. The frontend's blocker
        # chain (idea → literature → method) used to live entirely in
        # localStorage; a stale or malicious client could launch a
        # downstream stage without going through the upstream
        # checkpoint by editing localStorage. Now the backend reads
        # ``project.approvals`` (persisted by the /approvals endpoint)
        # and refuses any launch that would skip an unapproved gate.
        # ``approvals.auto_skip=True`` is the explicit escape hatch.
        blocking_gate = compute_blocking_approval(proj, stage)
        if blocking_gate is not None:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "approval_required",
                    "message": (
                        f"Cannot launch '{stage}' stage — upstream "
                        f"'{blocking_gate}' stage hasn't been approved. "
                        "Approve it via PUT /approvals (set per_stage."
                        f"{blocking_gate}=approved) or set auto_skip=true."
                    ),
                    "blocking_gate": blocking_gate,
                    "target_stage": stage,
                },
            )
        require_stage_allowed(stage, caps)
        require_under_budget(caps)
        if count_active_runs() >= caps.max_concurrent_runs:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "too_many_concurrent_runs",
                    "max": caps.max_concurrent_runs,
                    "message": "Wait for an active run to finish, or cancel one.",
                },
            )
        # Iter-25 defense-in-depth: pass the per-user-namespaced
        # project_dir so ``run_manager.start_run`` writes events /
        # status / artifacts under ``<root>/users/<uid>/<pid>/`` rather
        # than the legacy un-namespaced ``<root>/<pid>/``. The iter-24
        # entry-point guard already blocks cross-tenant launches; this
        # closes the worker-side gap so a missed guard at a future
        # call site can't silently leak into the wrong tree.
        return await start_run(
            pid,
            stage,
            run_request.model_dump(),
            bus,
            project_dir=store.project_dir(pid),
        )

    @app.get("/api/v1/projects/{pid}/runs/{run_id}", response_model=Run)
    def get_run_status(
        pid: str,
        run_id: str,
        request: Request,
        store: ProjectStore = Depends(_get_store),
    ) -> Run:
        _enforce_run_tenant(store.project_dir(pid), run_id, _get_user_id(request))
        run = get_run(run_id)
        if run is None:
            raise HTTPException(404, detail={"code": "run_not_found"})
        return run

    @app.post("/api/v1/projects/{pid}/runs/{run_id}/cancel")
    async def cancel(
        pid: str,
        run_id: str,
        request: Request,
        store: ProjectStore = Depends(_get_store),
    ) -> dict:
        _enforce_run_tenant(store.project_dir(pid), run_id, _get_user_id(request))
        ok = await cancel_run(run_id)
        return {"cancelled": ok}

    @app.get("/api/v1/projects/{pid}/runs/{run_id}/events")
    async def run_events(
        pid: str,
        run_id: str,
        request: Request,
        bus: EventBus = Depends(get_bus),
        store: ProjectStore = Depends(_get_store),
    ) -> StreamingResponse:
        _enforce_run_tenant(store.project_dir(pid), run_id, _get_user_id(request))

        async def generator() -> AsyncIterator[bytes]:
            yield b": connected\n\n"
            async for evt in bus.subscribe(f"run:{run_id}"):
                yield f"data: {json.dumps(evt)}\n\n".encode()
                if evt.get("kind") == "stage.finished":
                    return
        return StreamingResponse(
            generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/v1/projects/{pid}/runs", response_model=list[Run])
    def list_runs(
        pid: str,
        request: Request,
        store: ProjectStore = Depends(_get_store),
    ) -> list[Run]:
        _enforce_project_tenant(store, pid, _get_user_id(request))
        return list_active_runs(pid)

    # ------------------------------------------------------------ files
    @app.get("/api/v1/projects/{pid}/plots", response_model=list[dict])
    def list_plots(
        pid: str,
        request: Request,
        store: ProjectStore = Depends(_get_store),
    ) -> list[dict]:
        _enforce_project_tenant(store, pid, _get_user_id(request))
        return [
            {"name": p.name, "url": f"/api/v1/projects/{pid}/files/input_files/plots/{p.name}"}
            for p in store.list_plots(pid)
        ]

    @app.get("/api/v1/projects/{pid}/files/{relpath:path}")
    def get_file(
        pid: str,
        relpath: str,
        request: Request,
        store: ProjectStore = Depends(_get_store),
    ) -> FileResponse:
        # Iter-24 security: tenant check + path-traversal hardening.
        _enforce_project_tenant(store, pid, _get_user_id(request))

        root = store.project_dir(pid).resolve()
        target = (root / relpath).resolve()

        # ``str.startswith`` is path-prefix-collision vulnerable: if
        # ``root`` is ``/foo/bar/12`` and ``target`` is
        # ``/foo/bar/123/x.txt``, the legacy check would erroneously
        # pass. ``Path.is_relative_to`` (Python 3.9+) compares path
        # *components*, so it correctly distinguishes ``12`` from ``123``.
        # Also handles symlink escapes correctly because we already
        # ``.resolve()`` both root and target to their canonical forms.
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise HTTPException(
                403, detail={"code": "path_traversal_blocked"}
            ) from exc

        if not target.is_file():
            raise HTTPException(404)
        return FileResponse(target)

    # ------------------------------------------------------------ keys
    @app.get("/api/v1/keys/status")
    def keys_status(keys: KeyStore = Depends(_get_keys)) -> dict:
        return keys.status().model_dump()

    @app.put("/api/v1/keys")
    def update_keys(payload: KeysPayload, keys: KeyStore = Depends(_get_keys)) -> dict:
        keys.save(payload)
        return keys.status().model_dump()

    @app.get("/api/v1/projects/{pid}/usage")
    def project_usage(
        pid: str, store: ProjectStore = Depends(_get_store)
    ) -> dict:
        from ..worker.token_tracker import aggregate_project_usage
        project_dir = store.project_dir(pid)
        if not project_dir.exists():
            raise HTTPException(404, detail={"code": "project_not_found"})
        usage = aggregate_project_usage(project_dir)
        return usage.model_dump() if hasattr(usage, "model_dump") else {
            "total_input": usage.total_input,
            "total_output": usage.total_output,
            "total_cost_cents": usage.total_cost_cents,
            "by_stage": {k: v.__dict__ for k, v in usage.by_stage.items()},
            "by_model": {k: v.__dict__ for k, v in usage.by_model.items()},
            "by_run": list(usage.by_run),
        }

    @app.get("/api/v1/runs/{run_id}/usage")
    def run_usage(run_id: str) -> dict:
        from ..worker.token_tracker import _ledger_lock, _run_ledger, get_run_usage
        # Distinguish "no entry yet" from "tracked with zero tokens" by
        # checking ledger membership directly — get_run_usage always
        # returns a StageTokens, never None.
        with _ledger_lock:
            tracked = run_id in _run_ledger
        if not tracked:
            raise HTTPException(404, detail={"code": "run_not_tracked"})
        u = get_run_usage(run_id)
        return {
            "model": u.model,
            "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens,
            "cost_cents": u.cost_cents,
        }

    @app.post("/api/v1/keys/test/{provider}")
    async def test_key(
        provider: str,
        keys: KeyStore = Depends(_get_keys),
        caps: Capabilities = Depends(get_capabilities),
    ) -> dict:
        """Ping the provider's API with a tiny request to verify the stored key.

        Returns ``{ok, latency_ms, error}``. Never burns more than a single
        token of provider quota (Anthropic uses ``max_tokens=1``; the others
        hit lightweight list endpoints).
        """
        provider = provider.upper()
        if provider not in _PROVIDER_PROBES:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "unknown_provider",
                    "message": f"Unknown provider '{provider}'. "
                    f"Expected one of: {sorted(_PROVIDER_PROBES)}",
                },
            )
        if caps.is_demo:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "test_blocked_in_demo",
                    "message": (
                        "Key testing is disabled in demo mode to avoid "
                        "burning the shared credentials. Run the dashboard "
                        "locally to test your own keys."
                    ),
                },
            )
        key = keys.resolve(provider)
        if not key:
            return {"ok": False, "latency_ms": 0, "error": "no key configured"}
        return await _probe_provider(provider, key)

    # ------------------------------------------------------------ static (frontend) — only when built
    # server.py lives at dashboard/backend/src/plato_dashboard/api/server.py;
    # the Next.js static export lands at dashboard/frontend/out/. So we walk
    # up to the dashboard/ root and into frontend/out from there. parents[4]
    # is the monorepo layout; parents[3] was the original (incorrect) guess
    # — keep both as candidates so a future package layout change doesn't
    # silently re-break the root route.
    here = Path(__file__).resolve()
    static_dir = next(
        (p for p in (here.parents[4] / "frontend" / "out", here.parents[3] / "frontend" / "out") if p.exists()),
        None,
    )
    if static_dir is not None:
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

    return app


# ---------------------------------------------------------------- key tester
# Provider probes — tiny GET/POST that exercises authentication without
# spending real tokens. ``method``/``url``/``headers``/``json`` are passed
# through to ``httpx.AsyncClient.request``.
_PROVIDER_PROBES: dict[str, dict] = {
    "OPENAI": {
        "method": "GET",
        "url": "https://api.openai.com/v1/models",
        "headers_fn": lambda key: {"Authorization": f"Bearer {key}"},
    },
    "GEMINI": {
        "method": "GET",
        "url_fn": lambda key: (
            f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
        ),
        "headers_fn": lambda key: {},
    },
    "ANTHROPIC": {
        "method": "POST",
        "url": "https://api.anthropic.com/v1/messages",
        "headers_fn": lambda key: {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        "json": {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "hi"}],
        },
    },
    "PERPLEXITY": {
        # Perplexity exposes /models on some accounts; if it 404s we fall back
        # to a 1-token chat completion so we still get an auth signal.
        "method": "GET",
        "url": "https://api.perplexity.ai/models",
        "headers_fn": lambda key: {"Authorization": f"Bearer {key}"},
        "fallback": {
            "method": "POST",
            "url": "https://api.perplexity.ai/chat/completions",
            "headers_fn": lambda key: {
                "Authorization": f"Bearer {key}",
                "content-type": "application/json",
            },
            "json": {
                "model": "sonar",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            },
        },
    },
    "SEMANTIC_SCHOLAR": {
        "method": "GET",
        "url": (
            "https://api.semanticscholar.org/graph/v1/paper/search"
            "?query=test&limit=1"
        ),
        "headers_fn": lambda key: {"x-api-key": key},
    },
}


def _extract_provider_error(resp: httpx.Response) -> str:
    """Pull a human-readable error message out of a non-2xx provider response."""
    try:
        body = resp.json()
    except Exception:
        text = resp.text.strip()
        return text[:200] if text else f"HTTP {resp.status_code}"
    # Most SDKs nest under {"error": {"message": "..."}} or {"error": "..."}.
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or err.get("type") or err.get("code")
            if msg:
                return f"HTTP {resp.status_code}: {msg}"
        if isinstance(err, str) and err:
            return f"HTTP {resp.status_code}: {err}"
        msg = body.get("message") or body.get("detail")
        if isinstance(msg, str) and msg:
            return f"HTTP {resp.status_code}: {msg}"
    return f"HTTP {resp.status_code}"


async def _send_probe(client: httpx.AsyncClient, probe: dict, key: str) -> httpx.Response:
    method = probe["method"]
    url = probe["url_fn"](key) if "url_fn" in probe else probe["url"]
    headers = probe["headers_fn"](key)
    json_body = probe.get("json")
    return await client.request(method, url, headers=headers, json=json_body)


async def _probe_provider(provider: str, key: str) -> dict:
    """Run the configured probe and shape the result for the API."""
    probe = _PROVIDER_PROBES[provider]
    started = time.perf_counter()
    timeout = httpx.Timeout(8.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await _send_probe(client, probe, key)
            # Perplexity may 404 on /models for some accounts; retry with
            # the fallback chat-completion probe.
            if resp.status_code == 404 and "fallback" in probe:
                resp = await _send_probe(client, probe["fallback"], key)
    except httpx.TimeoutException:
        latency = int((time.perf_counter() - started) * 1000)
        return {"ok": False, "latency_ms": latency, "error": "timeout"}
    except httpx.HTTPError as exc:
        latency = int((time.perf_counter() - started) * 1000)
        return {
            "ok": False,
            "latency_ms": latency,
            "error": f"network error: {exc.__class__.__name__}: {exc}"[:200],
        }

    latency = int((time.perf_counter() - started) * 1000)
    if 200 <= resp.status_code < 300:
        return {"ok": True, "latency_ms": latency, "error": None}
    return {
        "ok": False,
        "latency_ms": latency,
        "error": _extract_provider_error(resp),
    }


app = create_app()


def cli() -> None:
    """Entry point for ``plato-dashboard-api`` console script."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "plato_dashboard.api.server:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    cli()
