-- Publication packages, the file library and connected services (Composio).
--
-- * publication_adaptations: the journal front matter the model wrote for a campaign
--   (structured abstract, key points, highlights, ...), cached so rebuilding a package
--   is free and identical.
-- * publication_exports: every built package. The zip lives in R2 (r2_key); the row keeps
--   its checksum, size and the journal checks shown in the app.
-- * library_files: a person's research files (uploads, imports from Google Drive,
--   Dropbox, OneDrive and email attachments, and exported packages). Bytes live in R2.
--   Imports are idempotent per external file (source, source_ref).
-- * composio_auth_configs: the Composio auth config used for each toolkit (created once,
--   with Composio-managed OAuth).
-- * integration_triggers: watched Drive folders and mailboxes, per account.
-- * integration_events: verified Composio webhook deliveries, deduplicated by their
--   webhook-id and processed by the Worker (immediately, then by cron if that failed).
CREATE TABLE IF NOT EXISTS plato.publication_adaptations (
    campaign_id  UUID NOT NULL REFERENCES plato.research_campaigns(id) ON DELETE CASCADE,
    journal      TEXT NOT NULL CHECK (journal ~ '^[a-z0-9-]{2,40}$'),
    adaptation   JSONB NOT NULL CHECK (jsonb_typeof(adaptation) = 'object'),
    model        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (campaign_id, journal)
);

CREATE TABLE IF NOT EXISTS plato.publication_exports (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id  UUID NOT NULL REFERENCES plato.research_campaigns(id) ON DELETE CASCADE,
    account_id   UUID REFERENCES plato.accounts(id) ON DELETE SET NULL,
    journal      TEXT NOT NULL CHECK (journal ~ '^[a-z0-9-]{2,40}$'),
    status       TEXT NOT NULL DEFAULT 'building' CHECK (status IN ('building', 'ready', 'failed')),
    name         TEXT CHECK (length(name) <= 200),
    r2_key       TEXT UNIQUE CHECK (length(r2_key) <= 300),
    bytes        BIGINT CHECK (bytes >= 0),
    sha256       TEXT CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    summary      JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(summary) = 'object'),
    error        TEXT CHECK (length(error) <= 2000),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_publication_exports_campaign
    ON plato.publication_exports(campaign_id, created_at DESC);

CREATE TABLE IF NOT EXISTS plato.library_files (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id   UUID NOT NULL REFERENCES plato.accounts(id) ON DELETE CASCADE,
    name         TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 255),
    media_type   TEXT NOT NULL CHECK (length(media_type) <= 255),
    kind         TEXT NOT NULL CHECK (kind IN ('data', 'reference', 'document', 'image', 'archive', 'other')),
    bytes        BIGINT NOT NULL CHECK (bytes >= 0),
    sha256       TEXT NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    source       TEXT NOT NULL CHECK (source IN ('upload', 'googledrive', 'dropbox', 'one_drive',
                                                 'gmail', 'outlook', 'export')),
    source_ref   TEXT CHECK (length(source_ref) <= 1000),
    r2_key       TEXT NOT NULL UNIQUE CHECK (length(r2_key) <= 300),
    meta         JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(meta) = 'object'),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_library_files_account ON plato.library_files(account_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_library_files_source
    ON plato.library_files(account_id, source, source_ref) WHERE source_ref IS NOT NULL;

CREATE TABLE IF NOT EXISTS plato.composio_auth_configs (
    toolkit         TEXT PRIMARY KEY CHECK (toolkit ~ '^[a-z0-9_]{2,40}$'),
    auth_config_id  TEXT NOT NULL CHECK (length(auth_config_id) <= 100),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plato.integration_triggers (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id    UUID NOT NULL REFERENCES plato.accounts(id) ON DELETE CASCADE,
    toolkit       TEXT NOT NULL CHECK (toolkit ~ '^[a-z0-9_]{2,40}$'),
    trigger_slug  TEXT NOT NULL CHECK (length(trigger_slug) <= 100),
    trigger_id    TEXT NOT NULL UNIQUE CHECK (length(trigger_id) <= 100),
    label         TEXT NOT NULL DEFAULT '' CHECK (length(label) <= 200),
    config        JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(config) = 'object'),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_integration_triggers_account ON plato.integration_triggers(account_id);

CREATE TABLE IF NOT EXISTS plato.integration_events (
    webhook_id    TEXT PRIMARY KEY CHECK (length(webhook_id) <= 200),
    account_id    UUID REFERENCES plato.accounts(id) ON DELETE CASCADE,
    type          TEXT NOT NULL CHECK (length(type) <= 100),
    payload       JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'failed', 'ignored')),
    attempts      INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    error         TEXT CHECK (length(error) <= 2000),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_integration_events_pending
    ON plato.integration_events(created_at) WHERE status = 'pending';

ALTER TABLE plato.publication_adaptations ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.publication_exports     ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.library_files           ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.composio_auth_configs   ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.integration_triggers    ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.integration_events      ENABLE ROW LEVEL SECURITY;
