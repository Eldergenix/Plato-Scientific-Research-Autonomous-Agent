-- Per-role models: the project agent (orchestrator) runs on a different model from the
-- research-thread sub-agents, so each agent call records which model it used.
--
-- agent_usage.tokens stays the column the monthly allowance sums
-- (plato.account_committed_tokens), and is now in allowance tokens: the call's tokens times
-- its model's price weight relative to Claude Haiku 5.5 (plato/scientist/models.py). Rows
-- written before this migration are Haiku 5.5 calls, whose weight is 1, so they are already
-- in allowance tokens. raw_tokens keeps the model's own token count.
ALTER TABLE plato.agent_usage
    ADD COLUMN IF NOT EXISTS model      TEXT   CHECK (length(model) BETWEEN 1 AND 100),
    ADD COLUMN IF NOT EXISTS raw_tokens BIGINT CHECK (raw_tokens >= 0);
