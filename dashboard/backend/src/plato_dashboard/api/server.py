from __future__ import annotations
import asyncio
import json
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
    KeysPayload,
    Project,
    Run,
    StageContent,
    StageId,
    StageRunRequest,
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
    return ProjectStore(root)


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
    settings = get_settings()
    print(f"Plato Dashboard starting on http://{settings.host}:{settings.port}")
    print(f"  project root: {settings.project_root}")
    print(f"  demo mode: {settings.demo_mode} · auth: {settings.auth}")
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

    app.include_router(manifests_router, prefix="/api/v1", tags=["manifests"])

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
        body: dict, store: ProjectStore = Depends(_get_store)
    ) -> Project:
        name = body.get("name", "Untitled project")
        return store.create(name=name, initial_data_description=body.get("data_description"))

    @app.get("/api/v1/projects/{pid}", response_model=Project)
    def get_project(pid: str, store: ProjectStore = Depends(_get_store)) -> Project:
        try:
            return store.load(pid)
        except FileNotFoundError as exc:
            raise HTTPException(404, detail={"code": "project_not_found"}) from exc

    @app.delete("/api/v1/projects/{pid}", status_code=204)
    def delete_project(pid: str, store: ProjectStore = Depends(_get_store)) -> None:
        store.delete(pid)

    # ------------------------------------------------------------ stages
    @app.get("/api/v1/projects/{pid}/state/{stage}", response_model=StageContent | None)
    async def read_stage(
        pid: str, stage: StageId, store: ProjectStore = Depends(_get_store)
    ) -> StageContent | None:
        return await store.read_stage(pid, stage)

    @app.put("/api/v1/projects/{pid}/state/{stage}", response_model=StageContent)
    async def write_stage(
        pid: str,
        stage: StageId,
        body: dict,
        store: ProjectStore = Depends(_get_store),
        caps: Capabilities = Depends(get_capabilities),
    ) -> StageContent:
        require_stage_allowed(stage, caps)
        return await store.write_stage(pid, stage, body.get("markdown", ""), origin="edited")

    # ------------------------------------------------------------ runs
    @app.post("/api/v1/projects/{pid}/stages/{stage}/run", response_model=Run, status_code=202)
    async def run_stage(
        pid: str,
        stage: StageId,
        request: StageRunRequest,
        bus: EventBus = Depends(get_bus),
        caps: Capabilities = Depends(get_capabilities),
    ) -> Run:
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
        return await start_run(pid, stage, request.model_dump(), bus)

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
    def list_runs(pid: str) -> list[Run]:
        return list_active_runs(pid)

    # ------------------------------------------------------------ files
    @app.get("/api/v1/projects/{pid}/plots", response_model=list[dict])
    def list_plots(pid: str, store: ProjectStore = Depends(_get_store)) -> list[dict]:
        return [
            {"name": p.name, "url": f"/api/v1/projects/{pid}/files/input_files/plots/{p.name}"}
            for p in store.list_plots(pid)
        ]

    @app.get("/api/v1/projects/{pid}/files/{relpath:path}")
    def get_file(
        pid: str, relpath: str, store: ProjectStore = Depends(_get_store)
    ) -> FileResponse:
        root = store.project_dir(pid).resolve()
        target = (root / relpath).resolve()
        if not str(target).startswith(str(root)):
            raise HTTPException(403, detail={"code": "path_traversal_blocked"})
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
