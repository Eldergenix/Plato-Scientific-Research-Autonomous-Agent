"""DualGraphStore: asyncpg access layer for the dual-graph schema.

Concurrency contract
--------------------
* **Intent claiming** uses ``SELECT ... FOR UPDATE SKIP LOCKED`` inside a single
  ``UPDATE ... FROM (subquery)`` statement, so N workers polling the same campaign
  each get a different intent and never block on each other.
* **Leases** make claims crash-safe. A claim sets ``lease_expires_at``; a worker
  extends it with :meth:`heartbeat`. An intent whose lease expired is claimable
  again (``attempt_count`` caps retries). Every write by a worker is *fenced* on
  ``claimed_by_worker = worker_id`` so a worker that lost its lease cannot
  overwrite the new owner's results.
* **Deduplication** is enforced by unique constraints (assets per
  ``(program, type, dedup_key)``; nodes per ``(campaign, type, dedup_key)``), never
  by read-then-write checks, so parallel agents racing on the same key converge on
  one row.
* **Budgets** use reserve/settle: a conditional ``UPDATE`` reserves an estimate
  only if it fits, and settlement refunds the unused part. The schema's CHECK
  constraint keeps ``used <= max`` true even for writers that bypass this class.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

import asyncpg

from plato.retrieval.doi import parse_arxiv_id, parse_doi

from .migrate import advisory_key, migrate

AssetType = Literal[
    "corpus_domain",
    "paper",
    "dataset",
    "baseline_repo",
    "model_checkpoint",
    "benchmark_metric",
    "verified_axiom",
]
NodeType = Literal["goal", "intent", "fact", "finding", "hint"]
NodeStatus = Literal["open", "claimed", "running", "verified", "refuted", "exhausted"]
EdgeType = Literal["spawns", "derived_from", "yields", "proves", "refutes"]
AnchorRole = Literal[
    "baseline", "dataset_input", "code_diff", "cited_prior_work", "target_benchmark"
]
ArtifactType = Literal[
    "stdout_log",
    "git_patch",
    "plot_png",
    "vlm_critique",
    "sealed_eval_json",
    "latex_section",
    "bibtex",
    "peer_review",
]
CampaignStatus = Literal[
    "ideation",
    "investigating",
    "ablating",
    "sealed_eval",
    "writing",
    "completed",
    "halted",
]

TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "halted"})

_INLINE_LIMIT = 1_048_576

# Fence for every write by a worker on an intent it claimed ($1 = node id, $2 = worker id).
_HELD = "id = $1 AND claimed_by_worker = $2 AND status IN ('claimed', 'running')"


def _lease_lost(worker_id: str, node_id: uuid.UUID) -> LeaseLost:
    return LeaseLost(f"worker {worker_id} no longer holds intent {node_id}")


class BudgetExceeded(RuntimeError):
    """A reservation would push a campaign past its token or GPU budget."""


class AllowanceExceeded(RuntimeError):
    """Creating the campaign would take its owner past the monthly default-key allowance."""


class LeaseLost(RuntimeError):
    """The worker no longer holds the intent it tried to update."""


@dataclass(frozen=True)
class Upserted:
    id: uuid.UUID
    created: bool


# ---------------------------------------------------------------------------
# Deterministic dedup keys (computed by the backend, never by the model).
# ---------------------------------------------------------------------------


def _normalise_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def paper_dedup_key(
    *,
    doi: str | None = None,
    arxiv_id: str | None = None,
    title: str | None = None,
    year: int | None = None,
) -> str:
    """Stable key for a paper: DOI, else arXiv id (version stripped), else title hash."""
    if parsed := parse_doi(doi):
        return f"doi:{parsed}"
    if parsed := parse_arxiv_id(arxiv_id):
        return f"arxiv:{parsed}"
    if title:
        digest = hashlib.sha256(
            f"{_normalise_text(title)}|{year or ''}".encode()
        ).hexdigest()
        return f"title:{digest[:32]}"
    raise ValueError("paper_dedup_key needs a doi, arxiv_id, or title")


def sha256_hex(content: bytes | str) -> str:
    data = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(data).hexdigest()


def content_dedup_key(content: bytes | str) -> str:
    """Key for a dataset or artifact: sha256 of its bytes."""
    return f"sha256:{sha256_hex(content)}"


def spec_dedup_key(*parts: str) -> str:
    """Key for an intent/finding spec: hash of normalised text, so rephrasings with only
    whitespace/punctuation/case changes collapse to one node."""
    joined = "\x1f".join(_normalise_text(p) for p in parts)
    return f"spec:{hashlib.sha256(joined.encode()).hexdigest()[:40]}"


def _jsonb(value: dict[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _encode_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


async def _init_connection(conn: asyncpg.Connection) -> None:
    # JSON(B) parameters are passed as Python objects and encoded once, here.
    for typ in ("json", "jsonb"):
        await conn.set_type_codec(
            typ, encoder=_encode_json, decoder=json.loads, schema="pg_catalog"
        )


class DualGraphStore:
    """Async store over a connection pool. Create with :meth:`connect`."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ------------------------------------------------------------------ lifecycle
    @classmethod
    async def connect(
        cls,
        dsn: str,
        *,
        min_size: int = 1,
        max_size: int = 10,
        run_migrations: bool = True,
        statement_cache_size: int = 0,
    ) -> DualGraphStore:
        """Open a pool and (by default) migrate.

        ``statement_cache_size=0`` keeps the store compatible with Supabase's
        transaction-mode pooler (PgBouncer/Supavisor), which cannot hold prepared
        statements across transactions. Raise it for direct connections.
        """
        pool = await asyncpg.create_pool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            init=_init_connection,
            statement_cache_size=statement_cache_size,
            command_timeout=60,
        )
        if run_migrations:
            async with pool.acquire() as conn:
                await migrate(conn)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        return self._pool

    # ------------------------------------------------------------------ programs & campaigns
    async def ensure_program(self, slug: str, title: str, domain: str) -> uuid.UUID:
        row = await self._pool.fetchrow(
            """
            INSERT INTO plato.research_programs(slug, title, domain) VALUES ($1, $2, $3)
            ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug
            RETURNING id
            """,
            slug,
            title,
            domain,
        )
        return row["id"]

    async def create_campaign(
        self,
        program_id: uuid.UUID,
        research_question: str,
        *,
        token_budget_max: int = 5_000_000,
        gpu_seconds_max: int = 86_400,
        config: dict[str, Any] | None = None,
        campaign_id: uuid.UUID | None = None,
        account_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        own_key: bool = False,
        monthly_cap: int | None = None,
    ) -> uuid.UUID:
        """Create a campaign. A caller-chosen ``campaign_id`` makes the call idempotent:
        a retry with the same id returns it without creating a duplicate. ``account_id``
        and ``project_id`` record its owner and project thread; ``own_key`` marks a
        campaign paid for with the owner's own API key.

        ``monthly_cap`` (default-key campaigns of an account) admits the campaign only if
        its whole token budget fits in what the account has left this month. The check and
        the insert run under a per-account transaction lock, so concurrent creates cannot
        both spend the same allowance."""
        campaign_id = campaign_id or uuid.uuid4()
        if monthly_cap is not None and account_id is None:
            raise ValueError("monthly_cap needs an account_id")
        async with self._pool.acquire() as conn, conn.transaction():
            if monthly_cap is not None:
                await conn.execute(
                    "SELECT pg_advisory_xact_lock($1)",
                    advisory_key(b"plato.account:" + account_id.bytes),
                )
                exists = await conn.fetchval(
                    "SELECT 1 FROM plato.research_campaigns WHERE id = $1", campaign_id
                )
                committed = await conn.fetchval(
                    "SELECT plato.account_committed_tokens($1)", account_id
                )
                if not exists and committed + token_budget_max > monthly_cap:
                    raise AllowanceExceeded(
                        f"this campaign's budget of {token_budget_max:,} tokens exceeds the "
                        f"{max(monthly_cap - committed, 0):,} tokens left this month"
                    )
            await conn.execute(
                """
                INSERT INTO plato.research_campaigns
                    (id, program_id, research_question, status, token_budget_max,
                     gpu_seconds_max, config, account_id, project_id, own_key)
                VALUES ($1, $2, $3, 'ideation', $4, $5, $6::jsonb, $7, $8, $9)
                ON CONFLICT (id) DO NOTHING
                """,
                campaign_id,
                program_id,
                research_question,
                token_budget_max,
                gpu_seconds_max,
                _jsonb(config),
                account_id,
                project_id,
                own_key,
            )
        return campaign_id

    async def get_campaign(self, campaign_id: uuid.UUID) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            """
            SELECT c.*, p.slug AS program_slug, p.domain AS program_domain
              FROM plato.research_campaigns c JOIN plato.research_programs p ON p.id = c.program_id
             WHERE c.id = $1
            """,
            campaign_id,
        )
        return dict(row) if row else None

    async def transition_campaign(
        self,
        campaign_id: uuid.UUID,
        to_status: CampaignStatus,
        *,
        from_statuses: Iterable[str] | None = None,
        reason: str | None = None,
    ) -> bool:
        """Compare-and-set status change. Returns False if the campaign was not in an
        allowed source status (another worker already moved it, or it is terminal)."""
        allowed = list(from_statuses) if from_statuses is not None else None
        row = await self._pool.fetchrow(
            """
            UPDATE plato.research_campaigns
               SET status = $2, halted_reason = COALESCE($4, halted_reason),
                   -- On the right-hand side "status" is the pre-update value.
                   halted_from = CASE WHEN $2 = 'halted' THEN status ELSE halted_from END
             WHERE id = $1
               AND NOT status = ANY($5::text[])
               AND ($3::text[] IS NULL OR status = ANY($3::text[]))
            RETURNING id
            """,
            campaign_id,
            to_status,
            allowed,
            reason,
            sorted(TERMINAL_STATUSES),
        )
        return row is not None

    # ------------------------------------------------------------------ budgets
    async def reserve_tokens(
        self, campaign_id: uuid.UUID, tokens: int, *, keep_free: int = 0
    ) -> None:
        """Reserve ``tokens`` only if at least ``keep_free`` tokens remain afterwards (used
        to hold back budget for the manuscript phase)."""
        if tokens < 0 or keep_free < 0:
            raise ValueError("tokens and keep_free must be >= 0")
        row = await self._pool.fetchrow(
            """
            UPDATE plato.research_campaigns SET tokens_used = tokens_used + $2
             WHERE id = $1 AND tokens_used + $2 + $3 <= token_budget_max
            RETURNING tokens_used
            """,
            campaign_id,
            tokens,
            keep_free,
        )
        if row is None:
            raise BudgetExceeded(f"token budget exhausted for campaign {campaign_id}")

    async def settle_tokens(
        self, campaign_id: uuid.UUID, reserved: int, actual: int
    ) -> None:
        """Replace a reservation with the actual usage. Overuse beyond the reservation is
        charged only up to the cap (the request already happened; the cap still holds)."""
        # The ledger row rides in the same statement and records what was actually charged
        # (the cap can clip an overrun), so once every reservation settles the ledger sums
        # to the campaign totals exactly.
        await self._pool.execute(
            """
            WITH cur AS (
                SELECT id, tokens_used AS old,
                       LEAST(token_budget_max, GREATEST(0, tokens_used - $2 + $3)) AS new
                  FROM plato.research_campaigns WHERE id = $1 FOR UPDATE
            ), settled AS (
                UPDATE plato.research_campaigns c SET tokens_used = cur.new
                  FROM cur WHERE c.id = cur.id
                RETURNING cur.id, cur.new - cur.old + $2 AS charged
            )
            INSERT INTO plato.usage_events (campaign_id, tokens)
            SELECT id, charged FROM settled WHERE charged > 0
            """,
            campaign_id,
            reserved,
            max(0, actual),
        )

    async def reserve_gpu_seconds(self, campaign_id: uuid.UUID, seconds: int) -> None:
        row = await self._pool.fetchrow(
            """
            UPDATE plato.research_campaigns SET gpu_seconds_used = gpu_seconds_used + $2
             WHERE id = $1 AND gpu_seconds_used + $2 <= gpu_seconds_max
            RETURNING gpu_seconds_used
            """,
            campaign_id,
            seconds,
        )
        if row is None:
            raise BudgetExceeded(f"compute budget exhausted for campaign {campaign_id}")

    async def settle_gpu_seconds(
        self, campaign_id: uuid.UUID, reserved: int, actual: int
    ) -> None:
        await self._pool.execute(
            """
            WITH cur AS (
                SELECT id, gpu_seconds_used AS old,
                       LEAST(gpu_seconds_max, GREATEST(0, gpu_seconds_used - $2 + $3)) AS new
                  FROM plato.research_campaigns WHERE id = $1 FOR UPDATE
            ), settled AS (
                UPDATE plato.research_campaigns c SET gpu_seconds_used = cur.new
                  FROM cur WHERE c.id = cur.id
                RETURNING cur.id, cur.new - cur.old + $2 AS charged
            )
            INSERT INTO plato.usage_events (campaign_id, gpu_seconds)
            SELECT id, charged FROM settled WHERE charged > 0
            """,
            campaign_id,
            reserved,
            max(0, actual),
        )

    # ------------------------------------------------------------------ knowledge assets
    async def upsert_asset(
        self,
        program_id: uuid.UUID,
        asset_type: AssetType,
        dedup_key: str,
        canonical_name: str,
        *,
        uri_or_commit: str | None = None,
        metadata: dict[str, Any] | None = None,
        parent_id: uuid.UUID | None = None,
        is_sealed_eval: bool = False,
        conn: asyncpg.Connection | None = None,
    ) -> Upserted:
        """Insert or merge an asset by its dedup key. Metadata is merged (existing keys win
        is *not* assumed: new keys are added, existing keys are overwritten). The sealed flag
        is sticky: once an asset is sealed, an upsert can never unseal it."""
        row = await (conn or self._pool).fetchrow(
            """
            INSERT INTO plato.knowledge_assets
                (program_id, asset_type, dedup_key, canonical_name, uri_or_commit, metadata, parent_id, is_sealed_eval)
            VALUES ($1, $2::plato.knowledge_asset_type, $3, $4, $5, $6::jsonb, $7, $8)
            ON CONFLICT (program_id, asset_type, dedup_key) DO UPDATE SET
                metadata       = plato.knowledge_assets.metadata || EXCLUDED.metadata,
                uri_or_commit  = COALESCE(plato.knowledge_assets.uri_or_commit, EXCLUDED.uri_or_commit),
                parent_id      = COALESCE(plato.knowledge_assets.parent_id, EXCLUDED.parent_id),
                is_sealed_eval = plato.knowledge_assets.is_sealed_eval OR EXCLUDED.is_sealed_eval
            RETURNING id, (xmax = 0) AS inserted
            """,
            program_id,
            asset_type,
            dedup_key,
            canonical_name,
            uri_or_commit,
            _jsonb(metadata),
            parent_id,
            is_sealed_eval,
        )
        return Upserted(row["id"], row["inserted"])

    async def put_dataset(
        self,
        program_id: uuid.UUID,
        file_name: str,
        content: bytes,
        *,
        description: str = "",
        is_sealed_eval: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> Upserted:
        """Register a dataset by content hash and store its bytes. Identical bytes uploaded
        twice (by any campaign of the program) map to one asset."""
        checksum = sha256_hex(content)
        meta = {
            "file_name": file_name,
            "size_bytes": len(content),
            "description": description,
            **(metadata or {}),
        }
        async with self._pool.acquire() as conn, conn.transaction():
            asset = await self.upsert_asset(
                program_id,
                "dataset",
                f"sha256:{checksum}",
                file_name,
                metadata=meta,
                is_sealed_eval=is_sealed_eval,
                conn=conn,
            )
            await conn.execute(
                """
                INSERT INTO plato.asset_blobs(asset_id, file_name, sha256_checksum, content)
                VALUES ($1, $2, $3, $4) ON CONFLICT (asset_id) DO NOTHING
                """,
                asset.id,
                file_name,
                checksum,
                content,
            )
        return asset

    async def dataset_inputs(
        self, campaign_id: uuid.UUID
    ) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
        """Visible dataset assets and their bytes, for the campaign's *current* phase. This is
        the only path by which data reaches the sandbox, so sealed data stays out until the
        sealed phase by construction."""
        visible = await self.visible_assets(campaign_id, asset_types=["dataset"])
        if not visible:
            return [], {}
        rows = await self._pool.fetch(
            "SELECT file_name, content FROM plato.asset_blobs WHERE asset_id = ANY($1::uuid[])",
            [a["id"] for a in visible],
        )
        return visible, {r["file_name"]: bytes(r["content"]) for r in rows}

    async def dataset_files(self, campaign_id: uuid.UUID) -> dict[str, bytes]:
        return (await self.dataset_inputs(campaign_id))[1]

    async def set_scope(
        self,
        campaign_id: uuid.UUID,
        asset_id: uuid.UUID,
        access_mode: Literal["read_only", "train_val", "sealed_eval_only", "excluded"],
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO plato.campaign_scope(campaign_id, asset_id, access_mode) VALUES ($1, $2, $3)
            ON CONFLICT (campaign_id, asset_id) DO UPDATE SET access_mode = EXCLUDED.access_mode
            """,
            campaign_id,
            asset_id,
            access_mode,
        )

    async def visible_assets(
        self, campaign_id: uuid.UUID, *, asset_types: Iterable[str] | None = None
    ) -> list[dict[str, Any]]:
        """Assets a worker may read in the campaign's *current* phase. Sealed assets and
        scope rows marked ``sealed_eval_only`` are hidden until the sealed phase;
        ``excluded`` assets are never visible."""
        types = list(asset_types) if asset_types is not None else None
        rows = await self._pool.fetch(
            """
            SELECT a.id, a.asset_type::text AS asset_type, a.dedup_key, a.canonical_name,
                   a.uri_or_commit, a.metadata, a.is_sealed_eval, s.access_mode
              FROM plato.campaign_scope s
              JOIN plato.knowledge_assets a ON a.id = s.asset_id
              JOIN plato.research_campaigns c ON c.id = s.campaign_id
             WHERE s.campaign_id = $1
               AND s.access_mode <> 'excluded'
               AND ($2::text[] IS NULL OR a.asset_type::text = ANY($2::text[]))
               AND (
                    plato.sealed_phase(c.status)
                    OR (NOT a.is_sealed_eval AND s.access_mode <> 'sealed_eval_only')
               )
             ORDER BY a.created_at
            """,
            campaign_id,
            types,
        )
        return [dict(r) for r in rows]

    async def query_uncovered_scope(
        self, campaign_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Visible in-scope assets that no node of this campaign is anchored to yet.
        This is the coverage frontier the planner expands."""
        rows = await self._pool.fetch(
            """
            SELECT a.id, a.asset_type::text AS asset_type, a.canonical_name, a.dedup_key, a.metadata
              FROM plato.campaign_scope s
              JOIN plato.knowledge_assets a ON a.id = s.asset_id
             WHERE s.campaign_id = $1
               AND s.access_mode IN ('read_only', 'train_val')
               AND NOT a.is_sealed_eval
               AND NOT EXISTS (
                    SELECT 1 FROM plato.exploration_anchors x
                      JOIN plato.exploration_nodes n ON n.id = x.node_id
                     WHERE x.asset_id = a.id AND n.campaign_id = $1)
             ORDER BY a.created_at
            """,
            campaign_id,
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ exploration graph
    async def create_node(
        self,
        campaign_id: uuid.UUID,
        node_type: NodeType,
        title: str,
        hypothesis_or_spec: str,
        *,
        dedup_key: str | None = None,
        priority: float = 0.0,
        metrics: dict[str, Any] | None = None,
        confidence_score: float | None = None,
        status: NodeStatus = "open",
        turn_budget_max: int = 30,
        conn: asyncpg.Connection | None = None,
    ) -> Upserted:
        """Create a node; with a ``dedup_key`` the call is idempotent across workers."""
        executor = conn or self._pool
        row = await executor.fetchrow(
            """
            INSERT INTO plato.exploration_nodes
                (campaign_id, node_type, title, hypothesis_or_spec, dedup_key, priority,
                 metrics, confidence_score, status, turn_budget_max)
            VALUES ($1, $2::plato.exploration_node_type, $3, $4, $5, $6, $7::jsonb, $8,
                    $9::plato.node_status, $10)
            ON CONFLICT (campaign_id, node_type, dedup_key) WHERE dedup_key IS NOT NULL DO NOTHING
            RETURNING id
            """,
            campaign_id,
            node_type,
            title,
            hypothesis_or_spec,
            dedup_key,
            priority,
            _jsonb(metrics),
            confidence_score,
            status,
            turn_budget_max,
        )
        if row is not None:
            return Upserted(row["id"], True)
        existing = await executor.fetchrow(
            """
            SELECT id FROM plato.exploration_nodes
             WHERE campaign_id = $1 AND node_type = $2::plato.exploration_node_type AND dedup_key = $3
            """,
            campaign_id,
            node_type,
            dedup_key,
        )
        return Upserted(existing["id"], False)

    async def add_edge(
        self,
        campaign_id: uuid.UUID,
        source: uuid.UUID,
        target: uuid.UUID,
        edge_type: EdgeType,
        rationale: str | None = None,
        *,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        executor = conn or self._pool
        await executor.execute(
            """
            INSERT INTO plato.exploration_edges(campaign_id, source_node_id, target_node_id, edge_type, rationale)
            VALUES ($1, $2, $3, $4::plato.exploration_edge_type, $5)
            ON CONFLICT (source_node_id, target_node_id, edge_type) DO NOTHING
            """,
            campaign_id,
            source,
            target,
            edge_type,
            rationale,
        )

    async def link_anchor(
        self,
        node_id: uuid.UUID,
        asset_id: uuid.UUID,
        role: AnchorRole,
        *,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        """Bind a node to an asset. The database rejects sealed assets before the sealed
        phase (``asyncpg.InsufficientPrivilegeError``) and cross-program anchors."""
        executor = conn or self._pool
        await executor.execute(
            """
            INSERT INTO plato.exploration_anchors(node_id, asset_id, anchor_role) VALUES ($1, $2, $3)
            ON CONFLICT DO NOTHING
            """,
            node_id,
            asset_id,
            role,
        )

    async def get_node(self, node_id: uuid.UUID) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM plato.exploration_nodes WHERE id = $1",
            node_id,
        )
        return dict(row) if row else None

    async def nodes(
        self,
        campaign_id: uuid.UUID,
        *,
        node_type: NodeType | None = None,
        status: NodeStatus | None = None,
    ) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            """
            SELECT id, node_type::text AS node_type, status::text AS status, title, hypothesis_or_spec,
                   metrics, confidence_score, priority, claimed_by_worker, attempt_count, dedup_key,
                   created_at, updated_at
              FROM plato.exploration_nodes
             WHERE campaign_id = $1
               AND ($2::text IS NULL OR node_type::text = $2)
               AND ($3::text IS NULL OR status::text = $3)
             ORDER BY created_at
            """,
            campaign_id,
            node_type,
            status,
        )
        return [dict(r) for r in rows]

    async def has_pending_intents(self, campaign_id: uuid.UUID) -> bool:
        return await self._pool.fetchval(
            """
            SELECT EXISTS (SELECT 1 FROM plato.exploration_nodes
                            WHERE campaign_id = $1 AND node_type = 'intent'
                              AND status IN ('open', 'claimed', 'running'))
            """,
            campaign_id,
        )

    # ------------------------------------------------------------------ claiming (the swarm queue)
    async def claim_next_intent(
        self,
        campaign_id: uuid.UUID,
        worker_id: str,
        *,
        lease_seconds: int = 300,
        max_attempts: int = 3,
    ) -> dict[str, Any] | None:
        """Atomically claim the highest-priority open intent (or one whose lease expired).

        Exactly one worker wins each row: the inner ``FOR UPDATE SKIP LOCKED`` makes
        competing workers skip rows another transaction is claiming instead of waiting.
        """
        row = await self._pool.fetchrow(
            """
            UPDATE plato.exploration_nodes n
               SET status = 'claimed', claimed_by_worker = $2, claimed_at = now(),
                   lease_expires_at = now() + make_interval(secs => $3),
                   attempt_count = n.attempt_count + 1
              FROM (
                    SELECT id FROM plato.exploration_nodes
                     WHERE campaign_id = $1 AND node_type = 'intent'
                       AND attempt_count < $4
                       AND (status = 'open'
                            OR (status IN ('claimed', 'running') AND lease_expires_at < now()))
                     ORDER BY priority DESC, created_at
                     LIMIT 1
                     FOR UPDATE SKIP LOCKED
                   ) pick
             WHERE n.id = pick.id
            RETURNING n.id, n.title, n.hypothesis_or_spec, n.metrics, n.attempt_count,
                      n.turn_budget_max, n.priority, n.lease_expires_at
            """,
            campaign_id,
            worker_id,
            lease_seconds,
            max_attempts,
        )
        return dict(row) if row else None

    async def heartbeat(
        self,
        node_id: uuid.UUID,
        worker_id: str,
        *,
        lease_seconds: int = 300,
        status: Literal["claimed", "running"] = "running",
    ) -> None:
        row = await self._pool.fetchrow(
            f"""
            UPDATE plato.exploration_nodes
               SET lease_expires_at = now() + make_interval(secs => $3), status = $4::plato.node_status
             WHERE {_HELD}
            RETURNING id
            """,
            node_id,
            worker_id,
            lease_seconds,
            status,
        )
        if row is None:
            raise _lease_lost(worker_id, node_id)

    async def use_turn(self, node_id: uuid.UUID, worker_id: str) -> int:
        """Consume one agent turn on a held intent; raises BudgetExceeded past the cap."""
        row = await self._pool.fetchrow(
            f"""
            UPDATE plato.exploration_nodes SET turns_used = turns_used + 1
             WHERE {_HELD} AND turns_used < turn_budget_max
            RETURNING turns_used
            """,
            node_id,
            worker_id,
        )
        if row is None:
            if await self._pool.fetchval(
                f"SELECT 1 FROM plato.exploration_nodes WHERE {_HELD}",
                node_id,
                worker_id,
            ):
                raise BudgetExceeded(f"turn budget exhausted for intent {node_id}")
            raise _lease_lost(worker_id, node_id)
        return row["turns_used"]

    async def complete_intent(
        self,
        node_id: uuid.UUID,
        worker_id: str,
        status: Literal["verified", "refuted", "exhausted", "open"],
        *,
        metrics: dict[str, Any] | None = None,
        confidence_score: float | None = None,
    ) -> None:
        """Release an intent with a terminal status (or ``open`` to hand it back).
        Fenced on the worker id: a worker whose lease was reclaimed gets ``LeaseLost``."""
        row = await self._pool.fetchrow(
            f"""
            UPDATE plato.exploration_nodes
               SET status = $3::plato.node_status,
                   lease_expires_at = NULL,
                   metrics = metrics || $4::jsonb,
                   confidence_score = COALESCE($5, confidence_score)
             WHERE {_HELD}
            RETURNING id
            """,
            node_id,
            worker_id,
            status,
            _jsonb(metrics),
            confidence_score,
        )
        if row is None:
            raise _lease_lost(worker_id, node_id)

    async def exhaust_dead_intents(
        self, campaign_id: uuid.UUID, *, max_attempts: int = 3
    ) -> int:
        """Mark intents that used every attempt and whose last lease expired as exhausted."""
        result = await self._pool.execute(
            """
            UPDATE plato.exploration_nodes SET status = 'exhausted', lease_expires_at = NULL
             WHERE campaign_id = $1 AND node_type = 'intent' AND attempt_count >= $2
               AND (status = 'open' OR (status IN ('claimed', 'running') AND lease_expires_at < now()))
            """,
            campaign_id,
            max_attempts,
        )
        return int(result.split()[-1])

    async def record_fact(
        self,
        campaign_id: uuid.UUID,
        intent_id: uuid.UUID,
        worker_id: str,
        *,
        title: str,
        observation: str,
        metrics: dict[str, Any] | None = None,
        confidence_score: float | None = None,
        anchors: Iterable[tuple[uuid.UUID, AnchorRole]] = (),
    ) -> uuid.UUID:
        """Write a fact + ``yields`` edge + anchors in one transaction, fenced on the lease."""
        async with self._pool.acquire() as conn, conn.transaction():
            held = await conn.fetchval(
                f"SELECT 1 FROM plato.exploration_nodes WHERE {_HELD} FOR UPDATE",
                intent_id,
                worker_id,
            )
            if not held:
                raise _lease_lost(worker_id, intent_id)
            fact = await self.create_node(
                campaign_id,
                "fact",
                title,
                observation,
                metrics=metrics,
                confidence_score=confidence_score,
                status="open",
                conn=conn,
            )
            await self.add_edge(campaign_id, intent_id, fact.id, "yields", conn=conn)
            for asset_id, role in anchors:
                await self.link_anchor(fact.id, asset_id, role, conn=conn)
        return fact.id

    async def set_node_status(
        self,
        node_id: uuid.UUID,
        status: NodeStatus,
        *,
        confidence_score: float | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        """Status change for non-claimable nodes (facts, findings, hints, goals)."""
        await self._pool.execute(
            """
            UPDATE plato.exploration_nodes
               SET status = $2::plato.node_status, confidence_score = COALESCE($3, confidence_score),
                   metrics = metrics || $4::jsonb
             WHERE id = $1 AND node_type <> 'intent'
            """,
            node_id,
            status,
            confidence_score,
            _jsonb(metrics),
        )

    # ------------------------------------------------------------------ drafts
    async def save_draft(self, campaign_id: uuid.UUID, stage: str, body: str) -> None:
        """Upsert the in-progress manuscript shown live in the UI (last write wins)."""
        await self._pool.execute(
            """
            INSERT INTO plato.manuscript_drafts (campaign_id, stage, body, updated_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (campaign_id) DO UPDATE
               SET stage = EXCLUDED.stage, body = EXCLUDED.body, updated_at = now()
            """,
            campaign_id,
            stage,
            body[:400_000],
        )

    async def get_draft(self, campaign_id: uuid.UUID) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT stage, body, updated_at FROM plato.manuscript_drafts WHERE campaign_id = $1",
            campaign_id,
        )
        return dict(row) if row else None

    # ------------------------------------------------------------------ evidence
    async def add_evidence(
        self,
        node_id: uuid.UUID,
        artifact_type: ArtifactType,
        content: bytes | str,
        *,
        approval_actor: Literal["human", "rule", "model", "system"] = "system",
        storage_uri: str | None = None,
        vlm_quality_score: float | None = None,
    ) -> uuid.UUID:
        """Store an immutable receipt. Content up to 1 MiB is kept inline; larger content
        must already live at ``storage_uri`` and only its checksum is recorded."""
        data = content.encode("utf-8") if isinstance(content, str) else content
        checksum = sha256_hex(data)
        inline = data if len(data) <= _INLINE_LIMIT else None
        if inline is None and not storage_uri:
            raise ValueError("content over 1 MiB needs an external storage_uri")
        uri = storage_uri or f"inline:sha256:{checksum}"
        row = await self._pool.fetchrow(
            """
            INSERT INTO plato.evidence_artifacts
                (node_id, artifact_type, storage_uri, sha256_checksum, content, vlm_quality_score, approval_actor)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (node_id, artifact_type, sha256_checksum) DO NOTHING
            RETURNING id
            """,
            node_id,
            artifact_type,
            uri,
            checksum,
            inline,
            vlm_quality_score,
            approval_actor,
        )
        if row is not None:
            return row["id"]
        return await self._pool.fetchval(
            """
            SELECT id FROM plato.evidence_artifacts
             WHERE node_id = $1 AND artifact_type = $2 AND sha256_checksum = $3
            """,
            node_id,
            artifact_type,
            checksum,
        )

    async def evidence_for(self, node_ids: Iterable[uuid.UUID]) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            """
            SELECT id, node_id, artifact_type, storage_uri, sha256_checksum, vlm_quality_score,
                   approval_actor, octet_length(content) AS size_bytes, created_at
              FROM plato.evidence_artifacts WHERE node_id = ANY($1::uuid[]) ORDER BY created_at
            """,
            list(node_ids),
        )
        return [dict(r) for r in rows]

    async def evidence_content(self, artifact_id: uuid.UUID) -> bytes | None:
        return await self._pool.fetchval(
            "SELECT content FROM plato.evidence_artifacts WHERE id = $1", artifact_id
        )

    async def evidence_contents(
        self, node_id: uuid.UUID, artifact_type: ArtifactType
    ) -> list[bytes]:
        """Inline contents of one artifact type for a node, oldest first, in one round trip."""
        rows = await self._pool.fetch(
            """
            SELECT content FROM plato.evidence_artifacts
             WHERE node_id = $1 AND artifact_type = $2 AND content IS NOT NULL ORDER BY created_at
            """,
            node_id,
            artifact_type,
        )
        return [bytes(r["content"]) for r in rows]

    # ------------------------------------------------------------------ guard audit
    async def record_guard_event(
        self,
        campaign_id: uuid.UUID,
        kind: str,
        decision: str,
        detail: dict[str, Any] | None = None,
        node_id: uuid.UUID | None = None,
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO plato.guard_events(campaign_id, node_id, kind, decision, detail)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            """,
            campaign_id,
            node_id,
            kind,
            decision,
            _jsonb(detail),
        )

    async def guard_events(
        self, campaign_id: uuid.UUID, limit: int = 200
    ) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            """
            SELECT node_id, kind, decision, detail, created_at FROM plato.guard_events
             WHERE campaign_id = $1 ORDER BY created_at DESC, id DESC LIMIT $2
            """,
            campaign_id,
            limit,
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ provenance
    async def trace_provenance(
        self, node_id: uuid.UUID, *, max_depth: int = 32
    ) -> dict[str, Any]:
        """Walk lineage edges backwards from ``node_id`` (finding <- proves <- fact <- yields
        <- intent <- derived_from/spawns <- ...) and return every ancestor with its anchors
        and evidence receipts. Cycle-safe and depth-bounded."""
        rows = await self._pool.fetch(
            """
            SELECT n.id, n.node_type::text AS node_type, n.status::text AS status, n.title,
                   n.metrics, n.confidence_score, l.depth
              FROM plato.lineage($1, $2) l JOIN plato.exploration_nodes n ON n.id = l.node_id
             ORDER BY l.depth, n.created_at
            """,
            node_id,
            max_depth,
        )
        nodes = [dict(r) for r in rows]
        ids = [n["id"] for n in nodes]
        anchors = await self._pool.fetch(
            """
            SELECT x.node_id, x.anchor_role, a.id AS asset_id, a.asset_type::text AS asset_type,
                   a.dedup_key, a.canonical_name, a.uri_or_commit
              FROM plato.exploration_anchors x JOIN plato.knowledge_assets a ON a.id = x.asset_id
             WHERE x.node_id = ANY($1::uuid[])
            """,
            ids,
        )
        edges = await self._pool.fetch(
            """
            SELECT source_node_id, target_node_id, edge_type::text AS edge_type
              FROM plato.exploration_edges
             WHERE source_node_id = ANY($1::uuid[]) AND target_node_id = ANY($1::uuid[])
            """,
            ids,
        )
        return {
            "root": node_id,
            "nodes": nodes,
            "edges": [dict(e) for e in edges],
            "anchors": [dict(a) for a in anchors],
            "evidence": await self.evidence_for(ids),
        }

    async def anchored_asset_ids(
        self, node_ids: Iterable[uuid.UUID], *, max_depth: int = 32
    ) -> set[uuid.UUID]:
        """Assets anchored anywhere in the lineage of any of ``node_ids``, in one query."""
        rows = await self._pool.fetch(
            """
            SELECT DISTINCT x.asset_id
              FROM unnest($1::uuid[]) AS r(id)
             CROSS JOIN LATERAL plato.lineage(r.id, $2) l
              JOIN plato.exploration_anchors x ON x.node_id = l.node_id
            """,
            list(node_ids),
            max_depth,
        )
        return {r["asset_id"] for r in rows}

    async def campaign_summary(self, campaign_id: uuid.UUID) -> dict[str, Any]:
        counts = await self._pool.fetch(
            """
            SELECT node_type::text AS node_type, status::text AS status, count(*) AS n
              FROM plato.exploration_nodes WHERE campaign_id = $1 GROUP BY 1, 2
            """,
            campaign_id,
        )
        summary: dict[str, dict[str, int]] = {}
        for r in counts:
            summary.setdefault(r["node_type"], {})[r["status"]] = r["n"]
        return {"campaign": await self.get_campaign(campaign_id), "nodes": summary}
