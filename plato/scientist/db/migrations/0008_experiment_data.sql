-- Experiment output files beyond figures, kept so readers can explore them in the app:
--   data_file  a table (CSV/TSV/JSON), molecular structure (PDB/mmCIF/SDF/MOL/MOL2/XYZ),
--              network or pathway (SIF/GraphML) or document (PDF/text) an experiment wrote
-- file_name is the name the experiment gave the file (no directories); figures carry it too.
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
        'citation_report', 'evidence_matrix', 'review_panel', 'data_file'));

ALTER TABLE plato.evidence_artifacts ADD COLUMN IF NOT EXISTS file_name TEXT;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'plato.evidence_artifacts'::regclass
                      AND conname = 'evidence_artifacts_file_name_check') THEN
        ALTER TABLE plato.evidence_artifacts ADD CONSTRAINT evidence_artifacts_file_name_check
            CHECK (file_name IS NULL OR (length(file_name) BETWEEN 1 AND 255
                   AND file_name !~ '[/\\[:cntrl:]]' AND left(file_name, 1) <> '.'));
    END IF;
END $$;
