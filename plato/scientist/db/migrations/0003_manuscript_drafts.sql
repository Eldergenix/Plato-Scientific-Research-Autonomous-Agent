-- The paper as it is being written, so the UI can show it live. One row per campaign,
-- overwritten as the writer streams; kept apart from research_campaigns so the summary
-- endpoint (polled every few seconds) never carries a multi-kilobyte body.
CREATE TABLE IF NOT EXISTS plato.manuscript_drafts (
    campaign_id  UUID PRIMARY KEY REFERENCES plato.research_campaigns(id) ON DELETE CASCADE,
    stage        TEXT NOT NULL CHECK (stage IN ('drafting', 'reviewing', 'revising', 'final')),
    body         TEXT NOT NULL DEFAULT '' CHECK (length(body) <= 400000),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
