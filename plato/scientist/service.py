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
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from plato.publish import journals as journal_profiles
from plato.publish.collect import NotPublishable
from plato.publish.materials import Material
from plato.publish.materials import ingest as ingest_materials
from plato.publish.package import PreviewFailed, build_package, preview_pdf

from .db.migrate import advisory_key
from .db.store import TERMINAL_STATUSES, AllowanceExceeded, DualGraphStore
from .graph import run_campaign
from .guard import network_isolation_prefix
from .guard.modal_runner import GPU_TYPES, modal_configured
from .llm import AnthropicScientistModel, resolve_model
from .nodes import ScientistContext

logger = logging.getLogger(__name__)


def _lock_key(campaign_id: uuid.UUID) -> int:
    return advisory_key(b"plato.campaign:" + campaign_id.bytes)


# 10 MiB of data as base64 (4/3 expansion). Datasets are stored in Postgres
# (asset_blobs allows 50 MB); the Worker caps a campaign's materials at 25 MiB in total.
MAX_FILE_BASE64 = 13_981_016


class DatasetIn(BaseModel):
    file_name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    content_base64: str = Field(max_length=MAX_FILE_BASE64)
    description: str = ""
    sealed: bool = False


class MaterialIn(BaseModel):
    """A reference file (.bib, .ris, .nbib, CSL-JSON) or a document (PDF, Word, ...)."""

    file_name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._ ()-]{0,127}$")
    kind: Literal["reference", "document"]
    content_base64: str = Field(max_length=MAX_FILE_BASE64)


class CampaignIn(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    program_slug: str = Field(default="default", pattern=r"^[a-z0-9][a-z0-9_-]{0,127}$")
    domain: str = Field(default="general", max_length=128)
    # Floor: the 80k-token writing reserve plus enough for at least one research round.
    token_budget: int = Field(default=2_000_000, ge=200_000, le=50_000_000)
    compute_seconds_budget: int = Field(default=7200, ge=60, le=864_000)
    workers: int = Field(default=4, ge=1, le=16)
    max_rounds: int = Field(default=2, ge=1, le=10)
    datasets: list[DatasetIn] = Field(default_factory=list, max_length=8)
    materials: list[MaterialIn] = Field(default_factory=list, max_length=16)
    # Where experiments run. "modal" needs MODAL_TOKEN_ID/MODAL_TOKEN_SECRET on the server.
    # Omitted: the deployment default (PLATO_DEFAULT_EXECUTOR; e2b when E2B is configured).
    executor: Literal["local", "modal", "e2b"] | None = None
    # Modal GPU type (e.g. "T4", "A100"); implies executor "modal".
    gpu: str = Field(default="", max_length=16)
    start: bool = True


class Runner:
    def __init__(self, store: DualGraphStore) -> None:
        self.store = store
        self.tasks: dict[uuid.UUID, asyncio.Task] = {}

    def start(self, campaign_id: uuid.UUID, api_key: str | None = None) -> bool:
        """Start the campaign unless it is already running here. ``api_key`` (the owner's
        own key, sent by the Worker per request) lives only in this task's model client."""
        task = self.tasks.get(campaign_id)
        if task and not task.done():
            return False
        self.tasks[campaign_id] = asyncio.create_task(
            self._run(campaign_id, api_key), name=f"campaign-{campaign_id}"
        )
        return True

    async def _run(self, campaign_id: uuid.UUID, api_key: str | None = None) -> None:
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
                    store=self.store,
                    model=AnthropicScientistModel(self.store, api_key=api_key),
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
            "executors": {
                "local": True,
                "modal": modal_configured(),
                "e2b": bool(os.environ.get("E2B_API_KEY")),
            },
            "literature_keys": {
                "ads": bool(
                    os.environ.get("ADS_API_KEY") or os.environ.get("ADS_DEV_KEY")
                ),
                "ncbi": bool(os.environ.get("NCBI_API_KEY")),
                "semantic_scholar": bool(os.environ.get("SEMANTIC_SCHOLAR_KEY")),
            },
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
        account_id: Annotated[uuid.UUID | None, Query(alias="account")] = None,
        project_id: Annotated[uuid.UUID | None, Query(alias="project")] = None,
        own_key: Annotated[bool, Query()] = False,
        # The owner's monthly default-key allowance, in tokens (absent: uncapped).
        cap: Annotated[int | None, Query(ge=0)] = None,
        x_plato_anthropic_key: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        if own_key and not x_plato_anthropic_key:
            raise HTTPException(
                status_code=422, detail="own_key campaigns need the owner's key"
            )
        if cap is not None and (own_key or account_id is None):
            raise HTTPException(
                status_code=422,
                detail="cap applies to an account's default-key campaigns",
            )
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
        materials = []
        for mt in body.materials:
            try:
                content = base64.b64decode(mt.content_base64, validate=True)
            except (binascii.Error, ValueError):
                raise HTTPException(
                    status_code=422, detail=f"file {mt.file_name} is not valid base64"
                )
            materials.append(Material(mt.file_name, content, mt.kind))
        title = re.sub(r"\s+", " ", body.program_slug.replace("-", " ")).title()
        program_id = await store.ensure_program(body.program_slug, title, body.domain)
        executor = "modal" if body.gpu else body.executor
        if body.gpu and body.gpu not in GPU_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"gpu must be one of {sorted(GPU_TYPES)}",
            )
        if executor == "modal" and not modal_configured():
            raise HTTPException(
                status_code=422,
                detail="GPU and Modal runs are not configured on this server yet",
            )
        if executor == "e2b" and not os.environ.get("E2B_API_KEY"):
            raise HTTPException(
                status_code=422,
                detail="E2B sandboxes are not configured on this server yet",
            )
        config = {
            "workers": body.workers,
            "max_rounds": body.max_rounds,
            # Left out when not chosen, so ScientistConfig applies the deployment default.
            **({"executor": executor} if executor else {}),
            "gpu": body.gpu,
            # Per campaign: the program's domain is fixed when the program is first created.
            "domain": body.domain,
        }
        try:
            campaign_id = await store.create_campaign(
                program_id,
                body.question,
                token_budget_max=body.token_budget,
                gpu_seconds_max=body.compute_seconds_budget,
                config=config,
                campaign_id=campaign_id,
                account_id=account_id,
                project_id=project_id,
                own_key=own_key,
                monthly_cap=cap,
            )
        except AllowanceExceeded as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from None
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
        ingested = (
            await ingest_materials(store, program_id, campaign_id, materials)
            if materials
            else None
        )
        started = (
            app.state.runner.start(campaign_id, x_plato_anthropic_key)
            if body.start
            else False
        )
        out: dict[str, Any] = {"id": str(campaign_id), "started": started}
        if ingested is not None:
            out["materials"] = ingested
        return out

    @app.post(
        "/internal/campaigns/{campaign_id}/run",
        status_code=202,
        dependencies=[Depends(require_token)],
    )
    async def run(
        campaign_id: uuid.UUID,
        x_plato_anthropic_key: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        campaign = await app.state.store.get_campaign(campaign_id)
        if campaign is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        if campaign["status"] in TERMINAL_STATUSES:
            return {
                "id": str(campaign_id),
                "started": False,
                "status": campaign["status"],
            }
        # A campaign paid for with its owner's key never falls back to the default key.
        if campaign.get("own_key") and not x_plato_anthropic_key:
            return {
                "id": str(campaign_id),
                "started": False,
                "reason": "owner key missing",
            }
        return {
            "id": str(campaign_id),
            "started": app.state.runner.start(campaign_id, x_plato_anthropic_key),
        }

    # Package builds are CPU-bound (pdfLaTeX, pandoc): two at a time per container.
    export_slots = asyncio.Semaphore(2)

    @app.get("/internal/publish/journals", dependencies=[Depends(require_token)])
    async def journals() -> list[dict[str, Any]]:
        return journal_profiles.catalogue()

    @app.post(
        "/internal/campaigns/{campaign_id}/exports/{journal}",
        dependencies=[Depends(require_token)],
        response_class=Response,
    )
    async def export(
        campaign_id: uuid.UUID,
        journal: str,
        account_id: Annotated[uuid.UUID | None, Query(alias="account")] = None,
        cap: Annotated[int | None, Query(ge=0)] = None,
        style: Annotated[str | None, Query(max_length=40)] = None,
        x_plato_anthropic_key: Annotated[str | None, Header()] = None,
    ) -> Response:
        """Build the journal package. The zip is the response body (the Worker streams it
        to R2); its metadata and checks are recorded in ``plato.publication_exports``."""
        if journal not in journal_profiles.JOURNALS:
            raise HTTPException(status_code=404, detail="unknown journal")
        if style and style != "journal" and style not in journal_profiles.STYLES:
            raise HTTPException(status_code=422, detail="unknown citation style")
        store: DualGraphStore = app.state.store
        campaign = await store.get_campaign(campaign_id)
        if campaign is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        if campaign.get("own_key") and not x_plato_anthropic_key:
            raise HTTPException(
                status_code=422, detail="this campaign is paid with its owner's key"
            )
        model = AnthropicScientistModel(store, api_key=x_plato_anthropic_key)
        # The allowance applies to an account's default-key campaigns only.
        cap = None if campaign.get("own_key") else cap
        async with export_slots:
            try:
                pkg = await build_package(
                    store, model, campaign_id, journal, cap=cap, style=style
                )
            except NotPublishable as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from None
            except ValueError as exc:
                raise HTTPException(status_code=413, detail=str(exc)) from None
        export_id = uuid.uuid4()
        r2_key = f"exports/{campaign_id}/{export_id}.zip"
        await store.pool.execute(
            """
            INSERT INTO plato.publication_exports
                (id, campaign_id, account_id, journal, status, name, r2_key, bytes, sha256, summary)
            VALUES ($1, $2, $3, $4, 'building', $5, $6, $7, $8, $9)
            """,
            export_id,
            campaign_id,
            account_id or campaign.get("account_id"),
            journal,
            pkg.name,
            r2_key,
            len(pkg.zip_bytes),
            pkg.sha256,
            pkg.summary(),
        )
        return Response(
            content=pkg.zip_bytes,
            media_type="application/zip",
            headers={
                "x-plato-export-id": str(export_id),
                "x-plato-export-key": r2_key,
                "x-plato-export-sha256": pkg.sha256,
                "x-plato-export-name": pkg.name,
            },
        )

    @app.get(
        "/internal/campaigns/{campaign_id}/manuscript.pdf",
        dependencies=[Depends(require_token)],
        response_class=Response,
    )
    async def manuscript_pdf(campaign_id: uuid.UUID) -> Response:
        """The finished paper typeset with pdfLaTeX (preprint layout, no model call).
        The Worker caches it in R2 per manuscript version."""
        store: DualGraphStore = app.state.store
        async with export_slots:
            try:
                pdf, pages = await preview_pdf(
                    store, campaign_id, model_name=resolve_model()
                )
            except NotPublishable as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from None
            except PreviewFailed as exc:
                logger.warning("preview did not compile: %s", exc.log[-800:])
                raise HTTPException(
                    status_code=422,
                    detail="The paper's LaTeX did not compile. The LaTeX view and the "
                    "publication packages still work.",
                ) from None
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"x-plato-pdf-pages": str(pages or "")},
        )

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
