-- Accounts, sessions, projects and the project agent.
--
-- * accounts: open sign-up with email and password. Password hashes are computed by the
--   Worker (PBKDF2-SHA256 with a per-account salt and a server-side pepper); the database
--   never sees a password.
-- * sessions: the browser holds a random token in an HttpOnly cookie; only its SHA-256 is
--   stored, so a database leak does not leak live sessions.
-- * account_keys: a person's own Anthropic API key, AES-256-GCM encrypted by the Worker
--   with a key the database never holds. Only the last four characters are readable.
-- * projects / project_messages: a chat with the orchestrator agent, stored as the exact
--   Messages API content so every turn replays the conversation unchanged. The model,
--   system prompt and tools are frozen per project (agent_config) for the same reason:
--   editing any of them mid-conversation would invalidate the replayed thinking blocks.
-- * agent_actions: one row per executed tool call, so a retried agent turn never repeats a
--   side effect (for example starting the same research thread twice).
-- * agent_usage: what each agent call consumed, for the monthly allowance on the default key.
CREATE TABLE IF NOT EXISTS plato.accounts (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email              TEXT NOT NULL CHECK (email = lower(email) AND length(email) BETWEEN 3 AND 254
                                            AND position('@' IN email) > 1),
    name               TEXT NOT NULL DEFAULT '' CHECK (length(name) <= 80),
    password_hash      TEXT NOT NULL CHECK (length(password_hash) BETWEEN 32 AND 512),
    is_admin           BOOLEAN NOT NULL DEFAULT false,
    preferences        JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(preferences) = 'object'),
    monthly_token_cap  BIGINT CHECK (monthly_token_cap >= 0),  -- NULL: the workspace default
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_accounts_email ON plato.accounts(email);

CREATE TABLE IF NOT EXISTS plato.sessions (
    token_hash    BYTEA PRIMARY KEY CHECK (length(token_hash) = 32),
    account_id    UUID NOT NULL REFERENCES plato.accounts(id) ON DELETE CASCADE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    user_agent    TEXT CHECK (length(user_agent) <= 300)
);
CREATE INDEX IF NOT EXISTS idx_sessions_account ON plato.sessions(account_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON plato.sessions(expires_at);

CREATE TABLE IF NOT EXISTS plato.account_keys (
    account_id    UUID PRIMARY KEY REFERENCES plato.accounts(id) ON DELETE CASCADE,
    ciphertext    BYTEA NOT NULL CHECK (length(ciphertext) BETWEEN 17 AND 1024),
    iv            BYTEA NOT NULL CHECK (length(iv) = 12),
    key_version   SMALLINT NOT NULL CHECK (key_version > 0),
    last4         TEXT NOT NULL CHECK (length(last4) = 4),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sign-up and sign-in throttling (subject = SHA-256 of the client IP or the email).
CREATE TABLE IF NOT EXISTS plato.auth_attempts (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('signup', 'login_ip', 'login_email')),
    subject     BYTEA NOT NULL CHECK (length(subject) = 32),
    ok          BOOLEAN NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_auth_attempts ON plato.auth_attempts(kind, subject, created_at);

CREATE TABLE IF NOT EXISTS plato.projects (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id    UUID NOT NULL REFERENCES plato.accounts(id) ON DELETE CASCADE,
    title         TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    agent_status  TEXT NOT NULL DEFAULT 'idle' CHECK (agent_status IN ('idle', 'working', 'error')),
    agent_error   TEXT CHECK (length(agent_error) <= 1000),
    agent_config  JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(agent_config) = 'object'),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_projects_account ON plato.projects(account_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS plato.project_messages (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id  UUID NOT NULL REFERENCES plato.projects(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     JSONB NOT NULL CHECK (jsonb_typeof(content) = 'array'),
    -- Assistant turns: why the model stopped (a cut-off tool call is never executed).
    stop_reason TEXT CHECK (length(stop_reason) <= 40),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_project_messages ON plato.project_messages(project_id, id);

CREATE TABLE IF NOT EXISTS plato.agent_actions (
    tool_use_id  TEXT PRIMARY KEY CHECK (length(tool_use_id) BETWEEN 1 AND 200),
    project_id   UUID NOT NULL REFERENCES plato.projects(id) ON DELETE CASCADE,
    result       JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS plato.agent_usage (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id  UUID NOT NULL REFERENCES plato.accounts(id) ON DELETE CASCADE,
    project_id  UUID REFERENCES plato.projects(id) ON DELETE SET NULL,
    tokens      BIGINT NOT NULL CHECK (tokens > 0),
    own_key     BOOLEAN NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agent_usage_account ON plato.agent_usage(account_id, created_at);

-- Who owns a campaign, which project thread it belongs to, and whose key pays for it.
-- Campaigns created before accounts existed keep NULL owners and are visible to admins.
ALTER TABLE plato.research_campaigns
    ADD COLUMN IF NOT EXISTS account_id UUID REFERENCES plato.accounts(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES plato.projects(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS own_key    BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS idx_research_campaigns_account ON plato.research_campaigns(account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_campaigns_project ON plato.research_campaigns(project_id);

-- Tokens an account has spent or committed on the default key this calendar month (UTC):
-- what its default-key campaigns were charged this month, the unspent budget its unfinished
-- default-key campaigns still hold (unless p_include_reserved is false), and its agent's
-- default-key usage. One definition, used by the container (atomic cap check on create),
-- the Worker (settings) and the agent (which checks spend only, so a person whose running
-- threads hold the rest of the allowance can still talk to it).
CREATE OR REPLACE FUNCTION plato.account_committed_tokens(p_account UUID,
                                                          p_include_reserved BOOLEAN DEFAULT true)
RETURNS BIGINT LANGUAGE sql STABLE AS $$
    WITH since AS (SELECT date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AS t)
    SELECT (
        COALESCE((SELECT sum(u.tokens) FROM plato.usage_events u
                    JOIN plato.research_campaigns c ON c.id = u.campaign_id
                   WHERE c.account_id = p_account AND NOT c.own_key
                     AND u.created_at >= (SELECT t FROM since)), 0)
      + COALESCE((SELECT sum(GREATEST(c.token_budget_max - c.tokens_used, 0))
                    FROM plato.research_campaigns c
                   WHERE p_include_reserved AND c.account_id = p_account AND NOT c.own_key
                     AND c.status NOT IN ('completed', 'halted')), 0)
      + COALESCE((SELECT sum(a.tokens) FROM plato.agent_usage a
                   WHERE a.account_id = p_account AND NOT a.own_key
                     AND a.created_at >= (SELECT t FROM since)), 0)
    )::bigint
$$;

DROP TRIGGER IF EXISTS trg_accounts_touch ON plato.accounts;
CREATE TRIGGER trg_accounts_touch BEFORE UPDATE ON plato.accounts
    FOR EACH ROW EXECUTE FUNCTION plato.touch_updated_at();
DROP TRIGGER IF EXISTS trg_projects_touch ON plato.projects;
CREATE TRIGGER trg_projects_touch BEFORE UPDATE ON plato.projects
    FOR EACH ROW EXECUTE FUNCTION plato.touch_updated_at();

-- Defence in depth, as for every other table: RLS on, no policies.
ALTER TABLE plato.accounts          ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.sessions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.account_keys      ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.auth_attempts     ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.projects          ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.project_messages  ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.agent_actions     ENABLE ROW LEVEL SECURITY;
ALTER TABLE plato.agent_usage       ENABLE ROW LEVEL SECURITY;
