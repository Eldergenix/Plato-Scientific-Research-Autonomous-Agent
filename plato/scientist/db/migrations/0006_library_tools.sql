-- Evidence receipts for the library tools wired into the live scientist:
--   citation_report  per-paper DOI/arXiv resolution and retraction checks (JSON)
--   evidence_matrix  each cited manuscript claim judged against the cited abstract (JSON)
--   review_panel     methodology, statistics, novelty and writing reviews (JSON)
-- Every CHECK constraint that restricts artifact_type is dropped whatever its name, then the
-- widened one is added, all inside the migration transaction. Existing rows satisfy it.
DO $$
DECLARE c record;
BEGIN
    FOR c IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'plato.evidence_artifacts'::regclass AND contype = 'c'
           AND pg_get_constraintdef(oid) LIKE '%artifact_type%'
    LOOP
        EXECUTE format('ALTER TABLE plato.evidence_artifacts DROP CONSTRAINT %I', c.conname);
    END LOOP;
END $$;
ALTER TABLE plato.evidence_artifacts
    ADD CONSTRAINT evidence_artifacts_artifact_type_check CHECK (artifact_type IN (
        'stdout_log', 'git_patch', 'plot_png', 'vlm_critique',
        'sealed_eval_json', 'latex_section', 'bibtex', 'peer_review',
        'citation_report', 'evidence_matrix', 'review_panel'));
