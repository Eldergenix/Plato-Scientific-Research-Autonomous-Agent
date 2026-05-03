# ADR 0006 — AutoResearchClaw 23-stage pipeline: mapping to Plato's two-tier LangGraph

- **Status**: Accepted (informational)
- **Date**: 2026-05-03
- **Deciders**: Plato maintainers
- **Phase**: skill-integration (research skills bundle)

## Context

The `autoresearchclaw-autonomous-research` skill (under
`.claude/skills/autoresearchclaw-autonomous-research/`) bundles a
23-stage autonomous research pipeline as a reference architecture for
turning a topic into a conference-ready paper. Plato implements an
overlapping but differently-shaped flow: a 10-node *ideation* graph in
`plato/langgraph_agents/` plus an ~18-node *paper authoring* graph in
`plato/paper_agents/`. Sliding the ARC stage list over Plato's graphs
makes the gaps and the things Plato already exceeds explicit, so future
work knows what to port and what to leave alone.

This ADR is an **investigation, not a refactor**. It does not change
any code. Plato's two-tier model stays. Any decision to fill a gap is a
separate ADR.

## Stage-to-node mapping

ARC phases are A–H. The "Plato equivalent" column points at the file
that implements the closest existing behaviour, or "missing" when no
direct equivalent ships today.

| ARC Phase | # | ARC Stage | Plato equivalent | Status |
|-----------|---|-----------|------------------|--------|
| A | 1  | TOPIC_INIT          | `langgraph_agents/reader.preprocess_node`                                                | covered |
| A | 2  | PROBLEM_DECOMPOSE   | `langgraph_agents/clarifier.research_question_clarifier`                                 | partial — clarifier asks ≤3 disambiguation questions; no formal sub-problem decomposition |
| B | 3  | SEARCH_STRATEGY     | inline in `langgraph_agents/literature.novelty_decider` (`Query` field)                 | partial — single query loop, no multi-query plan |
| B | 4  | LITERATURE_COLLECT  | `langgraph_agents/literature.semantic_scholar` over `retrieval/SourceAdapter` registry  | covered (and richer — six adapters: arXiv, S2, OpenAlex, ADS, Crossref, PubMed) |
| B | 5  | LITERATURE_SCREEN   | `langgraph_agents/slr_node.slr_node` (added by skill-integration)                       | covered (PRISMA screening behind `state['literature']['run_slr']`) |
| B | 6  | KNOWLEDGE_EXTRACT   | `paper_agents/claim_extractor` + `paper_agents/evidence_matrix_node`                    | covered (R3/R5) |
| C | 7  | SYNTHESIS           | `langgraph_agents/literature.literature_summary`                                         | covered |
| C | 8  | HYPOTHESIS_GEN      | `langgraph_agents/idea.idea_maker` ↔ `idea_hater` debate                                 | covered |
| D | 9  | EXPERIMENT_DESIGN   | `langgraph_agents/methods.methods_fast`                                                  | covered |
| D | 10 | CODE_GENERATION     | `executor` backends (`cmbagent` / `modal_backend` / `e2b_backend` / `local_jupyter`)    | covered |
| D | 11 | RESOURCE_PLANNING   | `DomainProfile.executor` selection                                                       | covered (implicit — domain profile picks the backend) |
| E | 12 | EXPERIMENT_RUN      | `executor` backends                                                                       | covered |
| E | 13 | ITERATIVE_REFINE    | **missing**                                                                               | gap — no self-healing experiment retry on failure |
| F | 14 | RESULT_ANALYSIS     | `paper_agents/results_node` (+ optional `_ml_addendum_for("results")` overlay)          | covered |
| F | 15 | RESEARCH_DECISION   | **missing**                                                                               | gap — no automated PROCEED / REFINE / PIVOT decision |
| G | 16 | PAPER_OUTLINE       | implicit in linear `paper_agents` graph                                                  | partial — no explicit outline node; sections are emitted in fixed order |
| G | 17 | PAPER_DRAFT         | `paper_agents/{abstract,introduction_node,methods_node,results_node,conclusions_node}`  | covered |
| G | 18 | PEER_REVIEW         | `paper_agents/{methodology,statistics,novelty,writing}_reviewer` + `critique_aggregator` | covered (and richer — four orthogonal axes vs ARC's single review stage) |
| G | 19 | PAPER_REVISION      | `paper_agents/redraft_node`                                                              | covered |
| H | 20 | QUALITY_GATE        | **missing**                                                                               | gap — no submission-readiness gate before export |
| H | 21 | KNOWLEDGE_ARCHIVE   | `plato.state` manifest (`manifest.json` per run)                                         | partial — manifest persists but no cross-run knowledge base |
| H | 22 | EXPORT_PUBLISH      | `paper_agents/latex.latex_node` + `latex_presets.journal_dict`                          | covered |
| H | 23 | CITATION_VERIFY     | `paper_agents/citation_validator_node` + `quality/retraction_db`                         | covered (and richer — also checks Retraction Watch) |

## Capabilities Plato has that ARC does not

These are not ARC stages, but they are real differentiators worth
preserving when future work happens:

- **Counter-evidence search** (`langgraph_agents/counter_evidence`,
  Workflow #11) — actively searches for studies that contradict the
  proposed idea, not just supportive literature.
- **Research-gap detection** (`langgraph_agents/gap_detector`,
  Workflow #12) — clusters contradictions, surfaces coverage holes,
  flags methodological homogeneity.
- **Visual referee** (`langgraph_agents/referee`) — renders the PDF
  pages and runs a vision-model review on the rasterised artefacts.
- **Multi-axis reviewer panel** — methodology / statistics / novelty /
  writing fired in parallel, severity-gated redraft loop. ARC's
  Stage 18 is a single peer-review pass.

## Gaps worth a follow-up ADR

The four "missing" rows above (Stages 13, 15, 16, 20). None are
load-bearing for the skill-integration work; flag them as candidates
for separate Plato ADRs:

1. **Self-healing experiment retry** (Stage 13). Today an executor
   failure surfaces as a node exception and ends the run. ARC retries
   with a refined prompt up to N times. A `executor_retry_node` would
   slot between the executor and the writing graph.
2. **PROCEED / REFINE / PIVOT decision** (Stage 15). Plato has no
   explicit "is this hypothesis still worth pursuing after seeing
   results?" branch. Could be a router after `results_node`.
3. **Outline-then-draft** (Stage 16). The current paper graph drafts
   each section against the same idea/methods state. An explicit
   outline node would let the abstract / intro / methods stay
   internally consistent against a single contribution skeleton.
4. **Submission-readiness gate** (Stage 20). Useful when a domain
   profile pins a venue (e.g. NeurIPS) and we want a mechanical check
   for page count, anonymisation, broader-impact statement, etc.
   before `EXPORT_PUBLISH`.

## Decision

Adopt the mapping above as the canonical reference when comparing the
two pipelines. Do **not** restructure Plato's graphs to match ARC's 23
stages: the tier split (ideation vs. authoring) is intentional and the
extra Plato-only nodes (counter-evidence, gap detector, multi-axis
reviewers) are net gains. Use this ADR as the entry point when triaging
proposals to "port stage X from ARC".

## Consequences

**Positive**

- Future "should we add stage X?" discussions start from a shared
  artefact instead of re-reading the ARC SKILL.md each time.
- The four gap stages are explicitly labelled, so they are easier to
  pick up as discrete pieces of work.

**Negative**

- This ADR will drift. ARC's stage list and Plato's graphs both evolve.
  Keep this file in the same PR as any node addition / removal that
  changes the mapping.
