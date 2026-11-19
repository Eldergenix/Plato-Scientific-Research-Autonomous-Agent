-- A fact that failed a verification gate without contradicting its hypothesis (no
-- replication, p above alpha after the multiplicity correction, a held-out re-test that did
-- not confirm it) is "inconclusive", distinct from "refuted" (replicated, significant and
-- against the hypothesis). Findings demoted by the held-out data or the multiplicity
-- correction take the same status.
ALTER TYPE plato.node_status ADD VALUE IF NOT EXISTS 'inconclusive' AFTER 'refuted';
