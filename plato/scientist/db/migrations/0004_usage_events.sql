-- What each model call and sandbox run actually consumed, and when. research_campaigns
-- keeps only the running totals; this append-only ledger lets the UI chart token and
-- compute burn over the life of a campaign. One row per settled call, written in the
-- same statement that settles the budget, so the ledger and the totals never diverge.
CREATE TABLE IF NOT EXISTS plato.usage_events (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    campaign_id  UUID NOT NULL REFERENCES plato.research_campaigns(id) ON DELETE CASCADE,
    tokens       BIGINT NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    gpu_seconds  INTEGER NOT NULL DEFAULT 0 CHECK (gpu_seconds >= 0),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (tokens > 0 OR gpu_seconds > 0)
);
CREATE INDEX IF NOT EXISTS idx_usage_events_campaign ON plato.usage_events(campaign_id, created_at, id);

-- Defence in depth, as for every other table: RLS on, no policies.
ALTER TABLE plato.usage_events      ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.manuscript_drafts ENABLE ROW LEVEL SECURITY;
