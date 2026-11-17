-- Plato dual-graph scientific discovery schema (PostgreSQL 15+, Supabase compatible).
--
-- Two graphs joined by an anchor bridge:
--   * knowledge_assets      : what exists (papers, datasets, baselines, ...), deduplicated per program.
--   * exploration_nodes/edges: how reasoning progresses inside one campaign.
--   * exploration_anchors   : binds exploration nodes to the assets they used or claim about.
--   * evidence_artifacts    : immutable receipts (logs, patches, plots, LaTeX) with checksums.
--
-- Clean-room implementation of the ideas described in the project brief. No code or SQL was
-- copied from AGPL-licensed projects.
--
-- Everything lives in the dedicated ``plato`` schema, which Supabase does not expose through
-- PostgREST, so these tables are reachable only through a direct Postgres connection.
-- RLS is enabled with no policies as defence in depth for any role other than the owner.

CREATE SCHEMA IF NOT EXISTS plato;

-- ---------------------------------------------------------------------------
-- Enums (CREATE TYPE has no IF NOT EXISTS; guard with catalog checks).
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = 'plato' AND t.typname = 'knowledge_asset_type') THEN
        CREATE TYPE plato.knowledge_asset_type AS ENUM (
            'corpus_domain', 'paper', 'dataset', 'baseline_repo',
            'model_checkpoint', 'benchmark_metric', 'verified_axiom');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = 'plato' AND t.typname = 'exploration_node_type') THEN
        CREATE TYPE plato.exploration_node_type AS ENUM ('goal', 'intent', 'fact', 'finding', 'hint');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = 'plato' AND t.typname = 'node_status') THEN
        CREATE TYPE plato.node_status AS ENUM ('open', 'claimed', 'running', 'verified', 'refuted', 'exhausted');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE n.nspname = 'plato' AND t.typname = 'exploration_edge_type') THEN
        CREATE TYPE plato.exploration_edge_type AS ENUM ('spawns', 'derived_from', 'yields', 'proves', 'refutes');
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 1. Programs and campaigns
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plato.research_programs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        TEXT NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9_-]{0,127}$'),
    title       TEXT NOT NULL,
    domain      TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plato.research_campaigns (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id         UUID NOT NULL REFERENCES plato.research_programs(id) ON DELETE CASCADE,
    research_question  TEXT NOT NULL CHECK (length(research_question) BETWEEN 3 AND 4000),
    status             TEXT NOT NULL DEFAULT 'ideation' CHECK (status IN (
                           'ideation', 'investigating', 'ablating', 'sealed_eval',
                           'writing', 'completed', 'halted')),
    halted_reason      TEXT,
    config             JSONB NOT NULL DEFAULT '{}'::jsonb,
    token_budget_max   BIGINT NOT NULL DEFAULT 5000000 CHECK (token_budget_max >= 0),
    tokens_used        BIGINT NOT NULL DEFAULT 0 CHECK (tokens_used >= 0),
    gpu_seconds_max    INTEGER NOT NULL DEFAULT 86400 CHECK (gpu_seconds_max >= 0),
    gpu_seconds_used   INTEGER NOT NULL DEFAULT 0 CHECK (gpu_seconds_used >= 0),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Budgets are hard caps: reservations that would overshoot are rejected by the store,
    -- and this constraint makes the cap hold even for writers that bypass the store.
    CONSTRAINT campaign_tokens_within_budget CHECK (tokens_used <= token_budget_max),
    CONSTRAINT campaign_gpu_within_budget CHECK (gpu_seconds_used <= gpu_seconds_max)
);
CREATE INDEX IF NOT EXISTS idx_research_campaigns_program ON plato.research_campaigns(program_id);
CREATE INDEX IF NOT EXISTS idx_research_campaigns_active ON plato.research_campaigns(status)
    WHERE status NOT IN ('completed', 'halted');

-- ---------------------------------------------------------------------------
-- 2. Knowledge asset graph (deduplicated per program)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plato.knowledge_assets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id      UUID NOT NULL REFERENCES plato.research_programs(id) ON DELETE CASCADE,
    parent_id       UUID REFERENCES plato.knowledge_assets(id) ON DELETE SET NULL,
    asset_type      plato.knowledge_asset_type NOT NULL,
    dedup_key       TEXT NOT NULL CHECK (length(dedup_key) BETWEEN 3 AND 512),
    canonical_name  TEXT NOT NULL,
    uri_or_commit   TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_sealed_eval  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (program_id, asset_type, dedup_key)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_assets_parent ON plato.knowledge_assets(parent_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_assets_metadata ON plato.knowledge_assets USING GIN (metadata);

-- Content of small datasets (<= 50 MiB) so experiments are reproducible from the database alone.
-- The checksum is verified by the database, and the asset's dedup key is that same checksum.
CREATE TABLE IF NOT EXISTS plato.asset_blobs (
    asset_id         UUID PRIMARY KEY REFERENCES plato.knowledge_assets(id) ON DELETE CASCADE,
    file_name        TEXT NOT NULL CHECK (file_name ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'),
    sha256_checksum  TEXT NOT NULL,
    content          BYTEA NOT NULL CHECK (octet_length(content) <= 52428800),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (encode(sha256(content), 'hex') = sha256_checksum)
);

CREATE TABLE IF NOT EXISTS plato.campaign_scope (
    campaign_id  UUID NOT NULL REFERENCES plato.research_campaigns(id) ON DELETE CASCADE,
    asset_id     UUID NOT NULL REFERENCES plato.knowledge_assets(id) ON DELETE CASCADE,
    access_mode  TEXT NOT NULL CHECK (access_mode IN ('read_only', 'train_val', 'sealed_eval_only', 'excluded')),
    PRIMARY KEY (campaign_id, asset_id)
);
CREATE INDEX IF NOT EXISTS idx_campaign_scope_asset ON plato.campaign_scope(asset_id);

-- ---------------------------------------------------------------------------
-- 3. Exploration graph (per campaign)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plato.exploration_nodes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id         UUID NOT NULL REFERENCES plato.research_campaigns(id) ON DELETE CASCADE,
    node_type           plato.exploration_node_type NOT NULL,
    status              plato.node_status NOT NULL DEFAULT 'open',
    -- Deterministic key so parallel planners never create the same intent twice.
    dedup_key           TEXT,
    claimed_by_worker   TEXT,
    claimed_at          TIMESTAMPTZ,
    lease_expires_at    TIMESTAMPTZ,
    attempt_count       INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    priority            NUMERIC(6,3) NOT NULL DEFAULT 0,
    title               TEXT NOT NULL,
    hypothesis_or_spec  TEXT NOT NULL,
    metrics             JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence_score    NUMERIC(4,3) CHECK (confidence_score >= 0 AND confidence_score <= 1),
    turn_budget_max     INTEGER NOT NULL DEFAULT 30 CHECK (turn_budget_max >= 0),
    turns_used          INTEGER NOT NULL DEFAULT 0 CHECK (turns_used >= 0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Target for the composite FKs below: edges may only join nodes of one campaign.
    UNIQUE (id, campaign_id),
    -- A held node always names its worker and lease; the worker id is kept afterwards for provenance.
    CONSTRAINT claim_fields_consistent CHECK (
        status NOT IN ('claimed', 'running')
        OR (claimed_by_worker IS NOT NULL AND lease_expires_at IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS idx_exploration_nodes_campaign_type
    ON plato.exploration_nodes(campaign_id, node_type, status);
-- Claim queue: open intents ordered by priority, and expired leases for reclaim.
CREATE INDEX IF NOT EXISTS idx_exploration_nodes_claimable
    ON plato.exploration_nodes(campaign_id, priority DESC, created_at)
    WHERE node_type = 'intent' AND status = 'open';
CREATE INDEX IF NOT EXISTS idx_exploration_nodes_leases
    ON plato.exploration_nodes(lease_expires_at)
    WHERE status IN ('claimed', 'running');
CREATE UNIQUE INDEX IF NOT EXISTS uq_exploration_nodes_dedup
    ON plato.exploration_nodes(campaign_id, node_type, dedup_key)
    WHERE dedup_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS plato.exploration_edges (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id     UUID NOT NULL REFERENCES plato.research_campaigns(id) ON DELETE CASCADE,
    source_node_id  UUID NOT NULL,
    target_node_id  UUID NOT NULL,
    edge_type       plato.exploration_edge_type NOT NULL,
    rationale       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_node_id, target_node_id, edge_type),
    CHECK (source_node_id <> target_node_id),
    FOREIGN KEY (source_node_id, campaign_id)
        REFERENCES plato.exploration_nodes(id, campaign_id) ON DELETE CASCADE,
    FOREIGN KEY (target_node_id, campaign_id)
        REFERENCES plato.exploration_nodes(id, campaign_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_exploration_edges_target ON plato.exploration_edges(target_node_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_exploration_edges_campaign ON plato.exploration_edges(campaign_id);

-- ---------------------------------------------------------------------------
-- 4. Reproducibility anchors
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plato.exploration_anchors (
    node_id      UUID NOT NULL REFERENCES plato.exploration_nodes(id) ON DELETE CASCADE,
    asset_id     UUID NOT NULL REFERENCES plato.knowledge_assets(id) ON DELETE CASCADE,
    anchor_role  TEXT NOT NULL CHECK (anchor_role IN (
                     'baseline', 'dataset_input', 'code_diff', 'cited_prior_work', 'target_benchmark')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (node_id, asset_id, anchor_role)
);
CREATE INDEX IF NOT EXISTS idx_exploration_anchors_asset ON plato.exploration_anchors(asset_id);

-- ---------------------------------------------------------------------------
-- 5. Evidence receipts (append-only)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plato.evidence_artifacts (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id            UUID NOT NULL REFERENCES plato.exploration_nodes(id) ON DELETE CASCADE,
    artifact_type      TEXT NOT NULL CHECK (artifact_type IN (
                           'stdout_log', 'git_patch', 'plot_png', 'vlm_critique',
                           'sealed_eval_json', 'latex_section', 'bibtex', 'peer_review')),
    storage_uri        TEXT NOT NULL,
    sha256_checksum    TEXT NOT NULL CHECK (sha256_checksum ~ '^[0-9a-f]{64}$'),
    -- Small artifacts are stored inline so a receipt is verifiable without external storage.
    content            BYTEA CHECK (content IS NULL OR octet_length(content) <= 1048576),
    vlm_quality_score  NUMERIC(3,2) CHECK (vlm_quality_score IS NULL OR (vlm_quality_score >= 0 AND vlm_quality_score <= 1)),
    approval_actor     TEXT NOT NULL CHECK (approval_actor IN ('human', 'rule', 'model', 'system')),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (node_id, artifact_type, sha256_checksum),
    CHECK (content IS NULL OR encode(sha256(content), 'hex') = sha256_checksum)
);
-- No separate node_id index: UNIQUE (node_id, artifact_type, sha256_checksum) leads with it.

-- ---------------------------------------------------------------------------
-- 6. Guardrail audit log (every allow/deny decision is recorded)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plato.guard_events (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    campaign_id  UUID NOT NULL REFERENCES plato.research_campaigns(id) ON DELETE CASCADE,
    node_id      UUID REFERENCES plato.exploration_nodes(id) ON DELETE SET NULL,
    kind         TEXT NOT NULL CHECK (kind IN ('command', 'budget', 'scope', 'sealed_eval', 'injection')),
    decision     TEXT NOT NULL CHECK (decision IN ('allow', 'deny')),
    detail       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_guard_events_campaign ON plato.guard_events(campaign_id, created_at);

-- ---------------------------------------------------------------------------
-- Triggers
-- ---------------------------------------------------------------------------
-- Single definition of the phases in which sealed (held-out) assets may be read. Used by
-- the anchor trigger below and by the store's visibility query.
CREATE OR REPLACE FUNCTION plato.sealed_phase(campaign_status TEXT) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path = '' AS $$
    SELECT campaign_status IN ('sealed_eval', 'writing', 'completed')
$$;

-- Lineage walk shared by the Python store and the Cloudflare Worker: every ancestor of
-- root_id along exploration edges (target -> source), cycle-safe, depth-bounded, with the
-- shortest distance to the root.
CREATE OR REPLACE FUNCTION plato.lineage(root_id UUID, max_depth INT DEFAULT 32)
RETURNS TABLE (node_id UUID, depth INT)
LANGUAGE sql STABLE PARALLEL SAFE SET search_path = '' AS $$
    WITH RECURSIVE walk(node_id, depth, path) AS (
        SELECT root_id, 0, ARRAY[root_id]
        UNION ALL
        SELECT e.source_node_id, w.depth + 1, w.path || e.source_node_id
          FROM walk w JOIN plato.exploration_edges e ON e.target_node_id = w.node_id
         WHERE w.depth < max_depth AND NOT e.source_node_id = ANY(w.path)
    )
    SELECT walk.node_id, MIN(walk.depth)::int FROM walk GROUP BY walk.node_id
$$;

CREATE OR REPLACE FUNCTION plato.touch_updated_at() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_exploration_nodes_touch ON plato.exploration_nodes;
CREATE TRIGGER trg_exploration_nodes_touch BEFORE UPDATE ON plato.exploration_nodes
    FOR EACH ROW EXECUTE FUNCTION plato.touch_updated_at();
DROP TRIGGER IF EXISTS trg_research_campaigns_touch ON plato.research_campaigns;
CREATE TRIGGER trg_research_campaigns_touch BEFORE UPDATE ON plato.research_campaigns
    FOR EACH ROW EXECUTE FUNCTION plato.touch_updated_at();

-- Sealed-evaluation isolation, enforced in the database: a held-out asset can be anchored to a
-- node only once its campaign has reached the sealed evaluation phase, and anchors must stay
-- inside the campaign's program.
CREATE OR REPLACE FUNCTION plato.enforce_anchor_rules() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    v_sealed         BOOLEAN;
    v_asset_program  UUID;
    v_status         TEXT;
    v_program        UUID;
BEGIN
    SELECT a.is_sealed_eval, a.program_id INTO v_sealed, v_asset_program
      FROM plato.knowledge_assets a WHERE a.id = NEW.asset_id;
    SELECT c.status, c.program_id INTO v_status, v_program
      FROM plato.exploration_nodes n JOIN plato.research_campaigns c ON c.id = n.campaign_id
     WHERE n.id = NEW.node_id;
    IF v_asset_program IS DISTINCT FROM v_program THEN
        RAISE EXCEPTION 'anchor asset % belongs to a different program', NEW.asset_id
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_sealed AND NOT plato.sealed_phase(v_status) THEN
        RAISE EXCEPTION 'sealed evaluation asset % cannot be used while campaign is %', NEW.asset_id, v_status
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_exploration_anchors_rules ON plato.exploration_anchors;
CREATE TRIGGER trg_exploration_anchors_rules BEFORE INSERT OR UPDATE ON plato.exploration_anchors
    FOR EACH ROW EXECUTE FUNCTION plato.enforce_anchor_rules();

-- Evidence receipts are immutable once written.
CREATE OR REPLACE FUNCTION plato.forbid_mutation() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    RAISE EXCEPTION '% rows are append-only', TG_TABLE_NAME USING ERRCODE = 'insufficient_privilege';
END;
$$;

DROP TRIGGER IF EXISTS trg_evidence_artifacts_immutable ON plato.evidence_artifacts;
CREATE TRIGGER trg_evidence_artifacts_immutable BEFORE UPDATE ON plato.evidence_artifacts
    FOR EACH ROW EXECUTE FUNCTION plato.forbid_mutation();

-- ---------------------------------------------------------------------------
-- Defence in depth: RLS on, no policies. Only the owning role (direct connection) has access.
-- ---------------------------------------------------------------------------
ALTER TABLE plato.research_programs   ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.research_campaigns  ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.knowledge_assets    ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.campaign_scope      ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.asset_blobs         ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.exploration_nodes   ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.exploration_edges   ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.exploration_anchors ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.evidence_artifacts  ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.guard_events        ENABLE ROW LEVEL SECURITY;
