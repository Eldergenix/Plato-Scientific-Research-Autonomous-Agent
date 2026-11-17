"""Integration tests for migrations and DualGraphStore against real PostgreSQL."""

from __future__ import annotations

import asyncio
import uuid

import asyncpg
import pytest

from plato.scientist.db.migrate import MigrationDriftError, load_migrations, migrate
from plato.scientist.db.store import (
    BudgetExceeded,
    DualGraphStore,
    LeaseLost,
    paper_dedup_key,
    spec_dedup_key,
)

# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------


async def test_migrations_are_idempotent_and_concurrency_safe(pg_dsn):
    conns = [await asyncpg.connect(pg_dsn) for _ in range(6)]
    try:
        results = await asyncio.gather(*(migrate(c) for c in conns))
        # Exactly one migrator applied each file; the rest saw it recorded.
        applied = [v for r in results for v in r]
        assert sorted(applied) == sorted(m.version for m in load_migrations())
        assert await migrate(conns[0]) == []  # restart == migrate == no-op
        rows = await conns[0].fetch("SELECT version FROM plato.schema_migrations")
        assert len(rows) == len(load_migrations())
        # The raw SQL itself is re-runnable (for manual application in Supabase).
        for m in load_migrations():
            await conns[0].execute(m.sql)
    finally:
        for c in conns:
            await c.close()


async def test_migration_drift_is_detected(pg_dsn):
    conn = await asyncpg.connect(pg_dsn)
    try:
        await migrate(conn)
        await conn.execute("UPDATE plato.schema_migrations SET sha256 = 'tampered'")
        with pytest.raises(MigrationDriftError):
            await migrate(conn)
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Deterministic dedup
# ---------------------------------------------------------------------------


def test_paper_dedup_keys_are_canonical():
    assert paper_dedup_key(arxiv_id="arXiv:2504.08066v3") == "arxiv:2504.08066"
    assert (
        paper_dedup_key(arxiv_id="https://arxiv.org/abs/2504.08066")
        == "arxiv:2504.08066"
    )
    assert paper_dedup_key(doi="https://doi.org/10.1000/ABC.1") == "doi:10.1000/abc.1"
    assert (
        paper_dedup_key(doi="10.1000/abc.1", arxiv_id="2504.08066")
        == "doi:10.1000/abc.1"
    )
    assert (
        paper_dedup_key(doi="10.1000/abc.1.") == "doi:10.1000/abc.1"
    )  # trailing punctuation
    assert (
        paper_dedup_key(arxiv_id="cond-mat/0211143v2") == "arxiv:cond-mat/0211143"
    )  # pre-2007 id
    assert paper_dedup_key(
        title="Attention Is All You Need!", year=2017
    ) == paper_dedup_key(title="  attention is all  you need ", year=2017)
    assert spec_dedup_key("Scale features.", "kNN") == spec_dedup_key(
        "scale   features", "KNN"
    )


async def test_parallel_asset_ingestion_creates_one_row(store, campaign):
    program, _ = campaign
    results = await asyncio.gather(
        *(
            store.upsert_asset(
                program, "paper", "arxiv:2504.08066", "Paper", metadata={f"w{i}": i}
            )
            for i in range(25)
        )
    )
    assert len({r.id for r in results}) == 1
    assert sum(r.created for r in results) == 1
    meta = await store.pool.fetchval(
        "SELECT metadata FROM plato.knowledge_assets WHERE id = $1", results[0].id
    )
    assert len(meta) == 25  # every worker's metadata merged, none lost


async def test_sealed_flag_is_sticky(store, campaign):
    program, _ = campaign
    a = await store.upsert_asset(
        program, "dataset", "sha256:" + "a" * 64, "holdout", is_sealed_eval=True
    )
    b = await store.upsert_asset(
        program, "dataset", "sha256:" + "a" * 64, "holdout", is_sealed_eval=False
    )
    assert a.id == b.id
    assert await store.pool.fetchval(
        "SELECT is_sealed_eval FROM plato.knowledge_assets WHERE id=$1", a.id
    )


async def test_parallel_planners_never_duplicate_intents(store, campaign):
    _, cid = campaign
    key = spec_dedup_key("hypothesis", "protocol")
    results = await asyncio.gather(
        *(
            store.create_node(cid, "intent", f"title {i}", "spec", dedup_key=key)
            for i in range(20)
        )
    )
    assert len({r.id for r in results}) == 1
    assert sum(r.created for r in results) == 1


async def test_edges_cannot_cross_campaigns(store, campaign):
    program, cid = campaign
    other = await store.create_campaign(program, "Another question")
    a = await store.create_node(cid, "goal", "a", "a")
    b = await store.create_node(other, "goal", "b", "b")
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await store.add_edge(cid, a.id, b.id, "spawns")


# ---------------------------------------------------------------------------
# Concurrent claiming (FOR UPDATE SKIP LOCKED) and leases
# ---------------------------------------------------------------------------


async def test_concurrent_workers_claim_each_intent_exactly_once(store, campaign):
    _, cid = campaign
    for i in range(60):
        await store.create_node(cid, "intent", f"intent {i}", "spec", priority=i % 7)

    claims: dict[str, list[uuid.UUID]] = {}

    async def worker(name: str):
        mine = claims.setdefault(name, [])
        while (row := await store.claim_next_intent(cid, name)) is not None:
            mine.append(row["id"])
            await asyncio.sleep(0)  # interleave workers

    await asyncio.gather(*(worker(f"w{i}") for i in range(12)))
    all_claims = [c for v in claims.values() for c in v]
    assert len(all_claims) == 60
    assert len(set(all_claims)) == 60
    assert sum(1 for v in claims.values() if v) > 1  # work really was spread out


async def test_claims_follow_priority(store, campaign):
    _, cid = campaign
    low = await store.create_node(cid, "intent", "low", "s", priority=0.1)
    high = await store.create_node(cid, "intent", "high", "s", priority=0.9)
    assert (await store.claim_next_intent(cid, "w"))["id"] == high.id
    assert (await store.claim_next_intent(cid, "w"))["id"] == low.id


async def test_expired_lease_is_reclaimed_and_old_worker_is_fenced(store, campaign):
    _, cid = campaign
    node = await store.create_node(cid, "intent", "i", "s")
    first = await store.claim_next_intent(cid, "crashed-worker", lease_seconds=1)
    assert first["id"] == node.id
    assert await store.claim_next_intent(cid, "other") is None  # lease still valid
    await store.pool.execute(
        "UPDATE plato.exploration_nodes SET lease_expires_at = now() - interval '1 second' WHERE id = $1",
        node.id,
    )
    second = await store.claim_next_intent(cid, "new-worker")
    assert second["id"] == node.id and second["attempt_count"] == 2
    with pytest.raises(LeaseLost):
        await store.complete_intent(node.id, "crashed-worker", "verified")
    with pytest.raises(LeaseLost):
        await store.record_fact(
            cid, node.id, "crashed-worker", title="t", observation="o"
        )
    await store.complete_intent(node.id, "new-worker", "verified")


async def test_intents_exhaust_after_max_attempts(store, campaign):
    _, cid = campaign
    node = await store.create_node(cid, "intent", "flaky", "s")
    for attempt in range(3):
        assert (
            await store.claim_next_intent(cid, f"w{attempt}", max_attempts=3)
            is not None
        )
        await store.pool.execute(
            "UPDATE plato.exploration_nodes SET lease_expires_at = now() - interval '1 second' WHERE id=$1",
            node.id,
        )
    assert await store.claim_next_intent(cid, "w4", max_attempts=3) is None
    assert await store.exhaust_dead_intents(cid, max_attempts=3) == 1
    assert (await store.get_node(node.id))["status"] == "exhausted"


async def test_turn_budget_is_enforced(store, campaign):
    _, cid = campaign
    node = await store.create_node(cid, "intent", "i", "s", turn_budget_max=2)
    await store.claim_next_intent(cid, "w")
    assert await store.use_turn(node.id, "w") == 1
    assert await store.use_turn(node.id, "w") == 2
    with pytest.raises(BudgetExceeded):
        await store.use_turn(node.id, "w")


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------


async def test_concurrent_token_reservations_never_overshoot(store, campaign):
    program, _ = campaign
    cid = await store.create_campaign(program, "budgeted", token_budget_max=10_000)

    async def reserve():
        try:
            await store.reserve_tokens(cid, 700)
            return True
        except BudgetExceeded:
            return False

    ok = await asyncio.gather(*(reserve() for _ in range(40)))
    assert sum(ok) == 14  # floor(10000 / 700)
    assert (await store.get_campaign(cid))["tokens_used"] == 9_800
    await store.settle_tokens(cid, 700, 100)
    assert (await store.get_campaign(cid))["tokens_used"] == 9_200
    with pytest.raises(BudgetExceeded):
        await store.reserve_tokens(cid, 500, keep_free=400)  # would leave only 300 free
    with pytest.raises(
        asyncpg.CheckViolationError
    ):  # the cap holds even outside the store
        await store.pool.execute(
            "UPDATE plato.research_campaigns SET tokens_used = 20000 WHERE id = $1", cid
        )


async def test_settled_usage_is_ledgered_with_the_totals(store, campaign):
    """Each settle writes what it charged to plato.usage_events in the same statement, so
    the burn chart sums to the campaign totals; refunds write nothing, and an overrun the
    cap clips is ledgered at the clipped amount."""
    program, _ = campaign
    cid = await store.create_campaign(program, "ledgered", token_budget_max=1_000)
    await store.reserve_tokens(cid, 700)
    await store.settle_tokens(cid, 700, 250)
    await store.reserve_tokens(cid, 700)
    await store.settle_tokens(cid, 700, 0)  # failed call: refunded, nothing consumed
    await store.reserve_tokens(cid, 700)
    await store.settle_tokens(cid, 700, 900)  # overran: only 750 fits under the cap
    await store.reserve_gpu_seconds(cid, 60)
    await store.settle_gpu_seconds(cid, 60, 12)
    rows = await store.pool.fetch(
        "SELECT tokens, gpu_seconds FROM plato.usage_events WHERE campaign_id = $1 ORDER BY id",
        cid,
    )
    assert [(r["tokens"], r["gpu_seconds"]) for r in rows] == [
        (250, 0),
        (750, 0),
        (0, 12),
    ]
    c = await store.get_campaign(cid)
    assert (c["tokens_used"], c["gpu_seconds_used"]) == (
        sum(r["tokens"] for r in rows),
        sum(r["gpu_seconds"] for r in rows),
    )


# ---------------------------------------------------------------------------
# Sealed-dataset isolation
# ---------------------------------------------------------------------------


async def test_sealed_datasets_are_invisible_until_sealed_phase(store, campaign):
    program, cid = campaign
    train = await store.put_dataset(program, "train.csv", b"x,y\n1,2\n")
    holdout = await store.put_dataset(
        program, "holdout.csv", b"x,y\n3,4\n", is_sealed_eval=True
    )
    await store.set_scope(cid, train.id, "train_val")
    await store.set_scope(cid, holdout.id, "sealed_eval_only")
    node = await store.create_node(cid, "intent", "i", "s")

    assert set(await store.dataset_files(cid)) == {"train.csv"}
    assert {a["id"] for a in await store.visible_assets(cid)} == {train.id}
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await store.link_anchor(node.id, holdout.id, "dataset_input")

    await store.transition_campaign(cid, "investigating")
    assert set(await store.dataset_files(cid)) == {"train.csv"}
    await store.transition_campaign(cid, "sealed_eval")
    assert set(await store.dataset_files(cid)) == {"train.csv", "holdout.csv"}
    await store.link_anchor(node.id, holdout.id, "target_benchmark")


async def test_scope_only_sealing_also_hides_asset(store, campaign):
    program, cid = campaign
    ds = await store.put_dataset(program, "maybe.csv", b"a\n1\n")
    await store.set_scope(cid, ds.id, "sealed_eval_only")
    assert await store.dataset_files(cid) == {}


async def test_anchors_cannot_cross_programs(store, campaign):
    _, cid = campaign
    other_program = await store.ensure_program("other", "Other", "bio")
    foreign = await store.upsert_asset(
        other_program, "paper", "arxiv:1234.56789", "foreign"
    )
    node = await store.create_node(cid, "fact", "f", "o")
    with pytest.raises(asyncpg.CheckViolationError):
        await store.link_anchor(node.id, foreign.id, "cited_prior_work")


async def test_campaign_transitions_are_compare_and_set(store, campaign):
    _, cid = campaign
    assert await store.transition_campaign(
        cid, "investigating", from_statuses=["ideation"]
    )
    assert not await store.transition_campaign(
        cid, "investigating", from_statuses=["ideation"]
    )
    assert await store.transition_campaign(cid, "completed")
    assert not await store.transition_campaign(
        cid, "investigating"
    )  # terminal stays terminal


# ---------------------------------------------------------------------------
# Evidence and provenance
# ---------------------------------------------------------------------------


async def test_evidence_is_checksummed_idempotent_and_immutable(store, campaign):
    _, cid = campaign
    node = await store.create_node(cid, "fact", "f", "o")
    a = await store.add_evidence(node.id, "stdout_log", "same bytes")
    b = await store.add_evidence(node.id, "stdout_log", "same bytes")
    assert a == b
    assert await store.evidence_content(a) == b"same bytes"
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await store.pool.execute(
            "UPDATE plato.evidence_artifacts SET approval_actor = 'human' WHERE id = $1",
            a,
        )
    with pytest.raises(
        asyncpg.CheckViolationError
    ):  # checksum must match inline content
        await store.pool.execute(
            """INSERT INTO plato.evidence_artifacts(node_id, artifact_type, storage_uri, sha256_checksum,
                   content, approval_actor) VALUES ($1, 'stdout_log', 'x', $2, 'other', 'system')""",
            node.id,
            "0" * 64,
        )


async def test_provenance_traces_finding_back_to_receipts(store, campaign):
    program, cid = campaign
    paper = await store.upsert_asset(program, "paper", "arxiv:2504.08066", "Prior work")
    data = await store.put_dataset(program, "d.csv", b"a\n1\n")
    await store.set_scope(cid, data.id, "train_val")
    goal = await store.create_node(cid, "goal", "g", "objective")
    hint = await store.create_node(cid, "hint", "h", "gap")
    await store.link_anchor(hint.id, paper.id, "cited_prior_work")
    intent = await store.create_node(cid, "intent", "i", "spec")
    await store.add_edge(cid, goal.id, intent.id, "spawns")
    await store.add_edge(cid, hint.id, intent.id, "derived_from")
    await store.claim_next_intent(cid, "w")
    fact = await store.record_fact(
        cid,
        intent.id,
        "w",
        title="f",
        observation="o",
        metrics={"acc": 0.9},
        anchors=[(data.id, "dataset_input")],
    )
    log_id = await store.add_evidence(fact, "stdout_log", 'PLATO_METRICS {"acc": 0.9}')
    finding = await store.create_node(cid, "finding", "F", "claim", status="verified")
    await store.add_edge(cid, fact, finding.id, "proves")

    trace = await store.trace_provenance(finding.id)
    types = {n["node_type"] for n in trace["nodes"]}
    assert types == {"finding", "fact", "intent", "goal", "hint"}
    assert {a["asset_id"] for a in trace["anchors"]} == {paper.id, data.id}
    assert log_id in {e["id"] for e in trace["evidence"]}
    assert {(e["edge_type"]) for e in trace["edges"]} == {
        "proves",
        "yields",
        "spawns",
        "derived_from",
    }


async def test_store_is_compatible_with_statement_cache_disabled(pg_dsn):
    # Supabase transaction-mode poolers cannot use prepared statements across transactions;
    # the default connect() disables the cache, and the store must still work.
    s = await DualGraphStore.connect(pg_dsn, statement_cache_size=0)
    try:
        p = await s.ensure_program("p", "P", "d")
        assert await s.ensure_program("p", "P", "d") == p
    finally:
        await s.close()
