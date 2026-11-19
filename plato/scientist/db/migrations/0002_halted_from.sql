-- Record the phase a campaign was in when it halted, so the UI and operators can tell
-- "halted while writing" from "halted while investigating" without guessing from the graph.
ALTER TABLE plato.research_campaigns ADD COLUMN IF NOT EXISTS halted_from TEXT;
