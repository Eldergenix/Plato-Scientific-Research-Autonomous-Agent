"""HTTP service that runs inside the Cloudflare Container (or locally).

The public edge is the Cloudflare Worker; this service trusts only requests that carry
the shared ``X-Plato-Internal-Token`` header. The Worker routes each campaign to its own
container instance; the campaign runs there as an asyncio task. A session-level Postgres
advisory lock per campaign guarantees a single runner even if two instances receive the
same campaign, and the Worker's cron trigger calls ``/internal/campaigns/{id}/run`` for every
unfinished campaign so a crashed or evicted run resumes from Postgres.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hmac
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .db.migrate import advisory_key
from .db.store import TERMINAL_STATUSES, DualGraphStore
from .graph import run_campaign
from .guard import network_isolation_prefix
from .llm import AnthropicScientistModel, resolve_model
from .nodes import ScientistContext

logger = logging.getLogger(__name__)


def _lock_key(campaign_id: uuid.UUID) -> int:
    return advisory_key(b"plato.campaign:" + campaign_id.bytes)


class DatasetIn(BaseModel):
    file_name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    # 1 MiB of data as base64 (4/3 expansion): datasets are stored inline in Postgres.
    content_base64: str = Field(max_length=1_398_104)
    description: str = ""
    sealed: bool = False


class CampaignIn(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    program_slug: str = Field(default="default", pattern=r"^[a-z0-9][a-z0-9_-]{0,127}$")
    domain: str = Field(default="general", max_length=128)
    token_budget: int = Field(default=2_000_000, ge=50_000, le=50_000_000)
    compute_seconds_budget: int = Field(default=7200, ge=60, le=864_000)
    workers: int = Field(default=4, ge=1, le=16)
    max_rounds: int = Field(default=2, ge=1, le=10)
    datasets: list[DatasetIn] = Field(default_factory=list, max_length=8)
    start: bool = True


class Runner:
    def __init__(self, store: DualGraphStore) -> None:
        self.store = store
        self.tasks: dict[uuid.UUID, asyncio.Task] = {}

    def start(self, campaign_id: uuid.UUID) -> bool:
        task = self.tasks.get(campaign_id)
        if task and not task.done():
            return False
        self.tasks[campaign_id] = asyncio.create_task(
            self._run(campaign_id), name=f"campaign-{campaign_id}"
        )
        return True

    async def _run(self, campaign_id: uuid.UUID) -> None:
        # Hold a dedicated connection for the session-level advisory lock: it is released
        # automatically if this container dies, so another instance can take over.
        async with self.store.pool.acquire() as lock_conn:
            got = await lock_conn.fetchval(
                "SELECT pg_try_advisory_lock($1)", _lock_key(campaign_id)
            )
            if not got:
                logger.info("campaign %s is running elsewhere", campaign_id)
                return
            try:
                ctx = ScientistContext(
                    store=self.store, model=AnthropicScientistModel(self.store)
                )
                summary = await run_campaign(ctx, campaign_id)
                logger.info(
                    "campaign %s finished: %s",
                    campaign_id,
                    summary["campaign"]["status"],
                )
            except Exception:
                logger.exception(
                    "campaign %s crashed; it will be resumed by the next cron tick",
                    campaign_id,
                )
            finally:
                await lock_conn.execute(
                    "SELECT pg_advisory_unlock($1)", _lock_key(campaign_id)
                )

    async def shutdown(self) -> None:
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)


def create_app(dsn: str | None = None, internal_token: str | None = None) -> FastAPI:
    dsn = dsn or os.environ["PLATO_DATABASE_URL"]
    token = (
        internal_token
        if internal_token is not None
        else os.environ.get("PLATO_INTERNAL_TOKEN", "")
    )
    if not token:
        raise RuntimeError("PLATO_INTERNAL_TOKEN must be set")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = await DualGraphStore.connect(
            dsn, max_size=int(os.environ.get("PLATO_DB_POOL_SIZE", "10"))
        )
        app.state.store = store
        # Probe once off the event loop (it shells out to unshare) before /healthz needs it.
        await asyncio.to_thread(network_isolation_prefix)
        app.state.runner = Runner(store)
        try:
            yield
        finally:
            await app.state.runner.shutdown()
            await store.close()

    app = FastAPI(
        title="Plato scientist", lifespan=lifespan, docs_url=None, redoc_url=None
    )

    def require_token(x_plato_internal_token: str = Header(default="")) -> None:
        if not hmac.compare_digest(x_plato_internal_token.encode(), token.encode()):
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/healthz")
    async def health() -> dict[str, Any]:
        store: DualGraphStore = app.state.store
        await store.pool.fetchval("SELECT 1")
        runner: Runner = app.state.runner
        return {
            "ok": True,
            "network_isolation": bool(network_isolation_prefix()),
            "model": resolve_model(),
            "active_runs": sum(1 for t in runner.tasks.values() if not t.done()),
        }

    @app.post(
        "/internal/campaigns", status_code=202, dependencies=[Depends(require_token)]
    )
    async def create_campaign(
        body: CampaignIn,
        # Chosen by the Worker so it can route the campaign to its container before it
        # exists (passed as a query parameter so the large body streams through untouched);
        # also makes a retried create idempotent.
        campaign_id: Annotated[uuid.UUID | None, Query(alias="id")] = None,
    ) -> dict[str, Any]:
        store: DualGraphStore = app.state.store
        decoded = []
        for ds in body.datasets:
            try:
                decoded.append((ds, base64.b64decode(ds.content_base64, validate=True)))
            except (binascii.Error, ValueError):
                raise HTTPException(
                    status_code=422,
                    detail=f"dataset {ds.file_name} is not valid base64",
                )
        title = re.sub(r"\s+", " ", body.program_slug.replace("-", " ")).title()
        program_id = await store.ensure_program(body.program_slug, title, body.domain)
        config = {"workers": body.workers, "max_rounds": body.max_rounds}
        campaign_id = await store.create_campaign(
            program_id,
            body.question,
            token_budget_max=body.token_budget,
            gpu_seconds_max=body.compute_seconds_budget,
            config=config,
            campaign_id=campaign_id,
        )
        for ds, content in decoded:
            asset = await store.put_dataset(
                program_id,
                ds.file_name,
                content,
                description=ds.description,
                is_sealed_eval=ds.sealed,
            )
            await store.set_scope(
                campaign_id, asset.id, "sealed_eval_only" if ds.sealed else "train_val"
            )
        started = app.state.runner.start(campaign_id) if body.start else False
        return {"id": str(campaign_id), "started": started}

    @app.post(
        "/internal/campaigns/{campaign_id}/run",
        status_code=202,
        dependencies=[Depends(require_token)],
    )
    async def run(campaign_id: uuid.UUID) -> dict[str, Any]:
        campaign = await app.state.store.get_campaign(campaign_id)
        if campaign is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        if campaign["status"] in TERMINAL_STATUSES:
            return {
                "id": str(campaign_id),
                "started": False,
                "status": campaign["status"],
            }
        return {"id": str(campaign_id), "started": app.state.runner.start(campaign_id)}

    @app.get("/internal/campaigns/{campaign_id}", dependencies=[Depends(require_token)])
    async def summary(campaign_id: uuid.UUID) -> dict[str, Any]:
        result = await app.state.store.campaign_summary(campaign_id)
        if result["campaign"] is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        return result

    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    logging.basicConfig(level=os.environ.get("PLATO_LOG_LEVEL", "INFO"))
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        proxy_headers=False,
        access_log=True,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
