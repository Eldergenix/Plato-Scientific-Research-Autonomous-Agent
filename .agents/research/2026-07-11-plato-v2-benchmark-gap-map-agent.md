---
id: research-2026-07-11-plato-v2-benchmark-gap-map-agent
type: research
date: 2026-07-11
backend: codex-sub-agent
---

# Plato-Bio v2 benchmark and biological-novelty gap map

## Scope and conclusion

This report maps the current main branch after the submitted Plato-Bio v1 work. It identifies what the v1 implementation actually repaired, what remains unmeasured, and the smallest defensible v2 slice that can run locally without paid model providers. The pass was read-only with respect to application and experiment code; only this research artifact was added.

The highest-value local slice is a frozen, time-sliced biomedical literature rediscovery benchmark:

1. Build a small, preregistered set of historical biological relationships.
2. Give the scorer only literature published before each relationship's discovery cutoff.
3. Generate and rank candidate A-C relationships through an evidence-bridge (A-B, B-C) graph.
4. Compare deterministic keyword, TF-IDF, bridge-only, and evidence-aware conditions.
5. Score target rank, false-novelty rate, evidence provenance, abstention, counter-evidence, and stability with task-level confidence intervals.

This directly exercises Plato's currently unwired novelty components and can use the installed scikit-learn, NumPy, SciPy, pandas, and statsmodels packages. It does not require a chat model. It would establish temporal rediscovery and novelty-screening validity, not prove that Plato discovered a new biological fact.

A true generative scientific-agent efficacy study is a separate lane. The current repository has no local chat-model backend, no Ollama executable, and no installed transformers or torch stack. The implemented LLM paths require hosted provider credentials, while the only no-key novelty embedding is a deterministic hash stub intended for tests (plato/novelty/embedding_scorer.py:78-99, 137-157). Therefore the immediate local benchmark can validate the novelty detector and evidence pipeline, but an end-to-end agent comparison requires either a local OpenAI-compatible backend plus a pinned open-weight model or paid provider runs.

## Retrieval method

The required three-cycle retrieval procedure was followed.

### Pre-flight and evidence tiers

- No repository-root AGENTS.md exists.
- No docs/code-map directory or similarly named code-map file exists.
- graphify is not installed, so no graph refresh was possible.
- Scoped git history was inspected first. The current head is f763352, after the v1 study commit 8e9d697 and subsequent submission/LaTeX documentation commits.
- Scoped rg/rg --files discovery then identified novelty, evaluation, biology, retrieval, evidence, safety, experiment, and manuscript owners.
- Source and test files were read only after those tiers.
- The prior repository audit at .agents/research/2026-07-11-plato-scientific-manuscript-audit.md was used as the before-state.
- Primary benchmark papers and official project pages were consulted only after local evidence established that the repository lacks a biological efficacy benchmark and a temporal novelty protocol.

### Cycle 1 — broad current-state discovery

Broad terms: novelty, discovery, biological benchmark, evaluation, hypothesis, evidence, reproducibility, baseline, ablation, confidence interval, safety.

Every result group retained from the broad search was scored from 0 to 1:

| Result | Relevance | Reason |
|---|---:|---|
| evals/runner.py, evals/metrics.py, evals/tasks.py, evals/judge.py | 1.00 | Canonical benchmark execution and metric contracts. |
| plato/novelty/embedding_scorer.py and composite_scorer.py | 1.00 | Only implemented quantitative novelty scorers. |
| plato/langgraph_agents/literature.py and prompts.py | 1.00 | Live novelty decision and literature-search loop. |
| plato/langgraph_agents/counter_evidence.py and gap_detector.py | 0.95 | Implemented disconfirmation and research-gap signals. |
| plato/retrieval/orchestrator.py, reranker.py, sources/pubmed.py, sources/europe_pmc.py | 0.95 | Biology literature inputs and no-key retrieval path. |
| evals/golden/*.json | 0.95 | Current task breadth and biological fixture reality. |
| preprint/experiments/run_globin_structure_benchmark.py | 0.95 | Only completed biological computation. |
| preprint/manuscript.md and preprint/results | 0.90 | Current evidence claims, limitations, and recorded results. |
| plato/paper_agents/evidence_matrix_node.py | 0.90 | Claim denominator and support-link evidence contract. |
| plato/domain/__init__.py | 0.85 | Biology routing, executor, and declared novelty corpus. |
| plato/executor/local_jupyter.py | 0.80 | No-provider local execution capability and safety boundary. |
| tests/unit novelty, biology, eval, retrieval, evidence tests | 0.90 | Existing contract coverage and fixture owners. |
| tests/safety and SECURITY.md | 0.85 | Prompt-injection and generated-code risk constraints. |
| dashboard novelty API/UI | 0.45 | Displays novelty outputs but does not compute or validate them. |
| deployment and product UI files | 0.10 | Irrelevant to scientific validity. |

Terms extracted from all results scoring at least 0.5:

CompositeNoveltyScorer, EmbeddingScorer, novelty_decider, novelty_corpus, PubMedAdapter, EuropePMCAdapter, retrieve, rerank, GoldenTask, method_signal_recall, unsupported_claim_rate, evidence_matrix.jsonl, counter_evidence_sources, gaps, LocalJupyterExecutor, globin benchmark, temporal cutoff, baseline, ablation, task-level uncertainty.

### Cycle 2 — exact seam tracing

Refined terms: CompositeNoveltyScorer wiring, novelty state, cutoff/date filters, evidence bridge, counter-evidence, GoldenTask biology, local model, deterministic baseline.

| Result | Relevance | Finding |
|---|---:|---|
| Repository-wide references to CompositeNoveltyScorer | 1.00 | Definitions and unit tests exist, but no research-graph call site exists. |
| plato/novelty/embedding_scorer.py | 1.00 | Score is one minus maximum cosine similarity; no-key backend is a hash pseudo-vector. |
| plato/langgraph_agents/literature.py | 1.00 | Novelty remains an LLM-generated categorical decision with iterative queries. |
| plato/langgraph_agents/prompts.py | 0.95 | Defines novel as absence of overlap after “sufficient searching,” without measurable sufficiency or a temporal holdout. |
| plato/langgraph_agents/agents_graph.py | 0.95 | Counter-evidence and gap detection are wired after summary, but the composite scorer is absent. |
| plato/langgraph_agents/gap_detector.py | 0.90 | Deterministic gaps are lexical coverage, contradiction labels, and fixed method-keyword homogeneity. |
| plato/langgraph_agents/counter_evidence.py | 0.90 | Uses three fixed negative-query suffixes; useful ablation but not a validated counter-evidence metric. |
| Source model and PubMed/Europe PMC/OpenAlex adapters | 0.95 | Preserve year, not exact publication date; no benchmark-level snapshot/cutoff contract exists. |
| evals/golden/protein_structure_alphafold.json | 1.00 | Only biology task; prompt-only and no bundled data. |
| pyproject.toml and local package probe | 0.90 | scikit-learn stack is available; sentence-transformers, torch, transformers, Biopython, and Ollama are not. |
| plato/llm.py, graph readers, evals/judge.py | 0.95 | Hosted OpenAI, Anthropic, Google, or Hugging Face clients only; no local endpoint/provider abstraction. |
| top external benchmark papers | 0.90 | Converge on authentic tasks, executable outputs, temporal or held-out evaluation, baselines, human validation, and error-aware metrics. |

Terms extracted from results scoring at least 0.5:

temporal rediscovery, ABC literature-based discovery, target-rank evaluation, Recall@K, mean reciprocal rank, nDCG, false novelty, non-verifiable hypothesis, executable analysis, task authenticity, human baseline, contamination control, fixed corpus snapshot, local TF-IDF, paired task design.

### Cycle 3 — validity and feasibility checks

Refined terms: leakage, unknown publication date, negative controls, task unit, bootstrap, local dependency proof, fail-open behavior, workflow ownership, safety.

| Result | Relevance | Finding |
|---|---:|---|
| Source.year and adapter query builders | 1.00 | Current live retrieval cannot prove an exact historical cutoff; benchmark fixtures must freeze dates and records. |
| reranker fallback | 0.90 | No rerank package means live retrieval is first-seen-wins; TF-IDF must be explicit in the pilot rather than inferred from current retrieval. |
| eval summary implementation | 0.95 | Means/p50/p95 only; no repeats, paired conditions, CIs, or tests. |
| eval paper fallback | 1.00 | Idea/method text is still labeled as paper text when no paper exists. |
| LLM judge error handling | 0.95 | Provider/model/parse failures become zero scores, which confounds capability and infrastructure failure. |
| reviewer parser | 0.90 | Malformed critique becomes severity zero, a fail-open scientific gate. |
| autonomous loop adapters | 0.95 | Still score existing manifests rather than execute a declared research workflow. |
| local dependency probe | 1.00 | Deterministic novelty pilot is runnable now; generative agent efficacy is not. |
| targeted current tests | 1.00 | 128 relevant tests passed, confirming present contracts but not efficacy. |
| BixBench/BAISBench size and task shape | 0.80 | Strong future external lanes, but multi-gigabyte datasets make them a second phase rather than the smallest slice. |
| BioVerge/BioDSA/ScienceAgentBench methods | 0.95 | Support evidence-aware hypothesis tasks, explicit non-verifiable outcomes, program execution, contamination controls, and expert validation. |

No additional high-relevance local seams emerged. Retrieval stopped after cycle 3.

## What has been fixed since the prior audit

The earlier audit identified three measurement defects that are now repaired.

### 1. Biology-domain leakage is fixed in the default evaluator

The default factory now constructs Plato with domain=task.domain (evals/runner.py:478-490). The regression test captures constructor kwargs and asserts biology is preserved (tests/unit/test_eval_runner.py:322-339). The biology smoke also asserts emitted manifests are tagged biology and that only biology adapters are selected (tests/unit/test_biology_end_to_end.py:176-244).

This fixes routing validity. It does not make the biology test a real end-to-end run: the test still uses _FakeBiologyPlato, explicitly records fake retrieval, and emits synthetic manifests (tests/unit/test_biology_end_to_end.py:62-133).

### 2. Declared method signals are now scored

Metrics includes method_signal_recall (evals/metrics.py:49-55). The runner computes it from methods.md only (evals/runner.py:229-237) and includes it in summaries (evals/runner.py:432-446). Its regression test verifies one of two expected signals yields 0.5 (tests/unit/test_eval_runner.py:299-320).

This fixes an omitted objective metric. It remains case-insensitive substring recall, so it does not establish that a method is correct, executable, or appropriate.

### 3. The evidence-sidecar denominator is now persisted

The evidence node writes drafted Claim rows before EvidenceLink rows (plato/paper_agents/evidence_matrix_node.py:129-135, 227-238). When no source exists, drafted claims are still persisted and the unsupported rate is 1.0 rather than a false zero (plato/paper_agents/evidence_matrix_node.py:164-175). Tests cover the mixed JSONL shape and the no-source denominator (tests/unit/test_evidence_matrix_node.py:95-119, 150-162).

This repairs metric computability. It does not validate the LLM support labels; evidence classification is still a model call over every drafted/source claim pair (plato/paper_agents/evidence_matrix_node.py:181-218).

### 4. A reproducible biological case study now exists

The v1 study added a declared three-target globin panel (preprint/experiments/run_globin_structure_benchmark.py:29-48), sequence-aware residue matching and Kabsch alignment (preprint/experiments/run_globin_structure_benchmark.py:171-223, 226-299), hashes and machine-readable outputs (preprint/experiments/run_globin_structure_benchmark.py:375-405), and a synthetic rigid-transform regression test (tests/unit/test_preprint_globin_benchmark.py:27-48).

The resulting target table reports 0.270, 0.520, and 0.501 Å C-alpha RMSD (preprint/results/globin_benchmark/target_summary.csv:1-4). The manuscript correctly limits this to a compact, high-confidence globin case study and does not call it a broad AlphaFold benchmark (preprint/manuscript.md:125-139).

### 5. Submission artifacts and claim language were aligned

The current manuscript explicitly says the evaluator stops after idea/method generation, reviewer roles are same-model self-critique, the autonomous loop does not establish improvement, and the current evidence supports software-contract and case-study reproducibility only (preprint/manuscript.md:81-85, 131-145). LaTeX and PDF submission artifacts were added after the scientific study. These are publication-readiness improvements, not new efficacy evidence.

## Current behavior and remaining gaps

### A. The quantitative novelty implementation is not in the live graph

CompositeNoveltyScorer blends a caller-supplied LLM score and embedding score with a configurable weight (plato/novelty/composite_scorer.py:37-74). EmbeddingScorer computes one minus the maximum title/abstract cosine similarity and returns the nearest source id (plato/novelty/embedding_scorer.py:121-183).

Repository-wide call-site search finds those classes only in their modules, package exports, tests, and dashboard display contracts. The research graph registers novelty_decider, not CompositeNoveltyScorer (plato/langgraph_agents/agents_graph.py:64-75, 94-115).

Consequence: the current novelty metric is architectural inventory, not a measured pipeline output.

### B. The no-key embedding fallback is not scientifically meaningful

StubEmbeddingBackend creates 384 coordinates by hashing each complete input string and coordinate index (plato/novelty/embedding_scorer.py:78-99). It is deterministic and useful for tests, but text semantics are not preserved. The backend is automatically selected whenever OPENAI_API_KEY is absent (plato/novelty/embedding_scorer.py:137-147).

Consequence: a local no-key run can return a numeric “novelty” score that looks precise but is not a defensible semantic-similarity measure.

### C. Novelty is currently absence-of-retrieval judged by the drafting model

The prompt defines novelty as no significant overlap after sufficient searching and asks the model to decide novel/not novel/query (plato/langgraph_agents/prompts.py:90-139). The node retries JSON parsing, updates the query, and forces “novel” at the maximum iteration bound (plato/langgraph_agents/literature.py:51-126).

Problems:

- “Sufficient searching” has no coverage threshold.
- Search failure and evidence of absence are not statistically separated.
- Reaching the iteration cap can force a novel verdict.
- No score calibration, nearest-prior-art record, cutoff, or abstention confidence is persisted.
- The same model proposes queries and decides novelty.
- Unknown-year or post-cutoff leakage is not blocked.

### D. The declared biology novelty corpus is metadata only

The biology profile declares PubMed as novelty_corpus and includes PubMed, Europe PMC, and broader scholarly adapters (plato/domain/__init__.py:110-146). novelty_corpus has no consumer outside the domain schema and tests. Live retrieval fans out, deduplicates, and reranks selected adapters (plato/retrieval/orchestrator.py:65-119), but it does not construct a reproducible corpus snapshot.

PubMed works without a key and retrieves metadata plus abstracts (plato/retrieval/sources/pubmed.py:1-14, 200-260). Europe PMC is also public/no-key (plato/retrieval/sources/europe_pmc.py:1-7, 185-231). These are good fixture sources, but live results are not a frozen benchmark.

### E. Retrieval ordering is weak in the current local environment

Reranking prefers Cohere, then a sentence-transformer cross-encoder, then first-seen order (plato/retrieval/reranker.py:43-87). The local checkout has neither a Cohere key nor sentence-transformers. Therefore the default local path is first-seen-wins, not relevance ranking.

### F. Gap and counter-evidence controls are useful but not validated as discovery metrics

The gap detector can flag:

- claim contradiction clusters;
- idea keywords appearing in fewer than two sources;
- all sources sharing a fixed method keyword (plato/langgraph_agents/gap_detector.py:1-18, 125-226).

It is deterministic and tested (tests/unit/test_gap_detector.py:45-197), but its fixed method vocabulary is astronomy/ML-heavy and omits most biology methods (plato/langgraph_agents/gap_detector.py:36-59).

Counter-evidence retrieval dispatches exactly three deterministic variants: fail to replicate, null result, and limitations (plato/langgraph_agents/counter_evidence.py:40-58, 114-154). Tests prove fan-out and dedup, not recall or biological usefulness (tests/unit/test_counter_evidence.py:47-84, 143-158).

### G. The current evaluation harness still does not test scientific-agent efficacy

EvalRunner executes only set_data_description, get_idea, and get_method. get_results and get_paper remain skipped (evals/runner.py:1-18, 175-199). When no paper exists, scoring concatenates idea and method text as paper_text (evals/runner.py:214-219).

Only one of six golden tasks is biology, and it is a prompt with expected keywords/signals and two source DOIs, not a bundled dataset (evals/golden/protein_structure_alphafold.json:1-8). The globin experiment is not connected to that GoldenTask.

The current metrics include keyword/method/source recall, costs, latency, tool errors, citation/evidence rates, and model-judge axes (evals/metrics.py:22-63). Summary statistics are mean, p50, and p95 only (evals/runner.py:422-475). There are no:

- repeated runs;
- paired baseline or ablation conditions;
- task-level confidence intervals;
- significance or effect-size calculations;
- human expert labels;
- data/execution correctness endpoints;
- explicit missing/infrastructure-failure status.

### H. Judge failures and reviewer parse failures remain fail-open/confounded

The default eval panel includes claude-sonnet-4-5 (evals/runner.py:37-40), but that identifier is absent from the registered model dictionary (plato/llm.py:102-132). Judge provider/model/parse failures are converted to all-zero JudgeResults (evals/judge.py:96-117), so infrastructure failures are indistinguishable from scientifically bad outputs.

Paper reviewer parse failures become severity zero with no issues (plato/paper_agents/reviewer_panel.py:44-86). All reviewers call LLM_call against the one client held in graph state (plato/paper_agents/reviewer_panel.py:89-130; get_paper exposes one llm argument at plato/plato.py:1154-1162).

### I. The autonomous loop still does not execute research

ResearchLoop calls a supplied factory and score function, then keeps/discards based on the score (plato/loop/research_loop.py:278-353). The CLI factory creates Plato, but the score function only reads the latest manifest (plato/cli.py:249-278). The dashboard default factory returns None and similarly scores existing manifests (dashboard/backend/src/plato_dashboard/api/loop_control.py:216-245).

No v2 efficacy claim should use this loop until each iteration declares and executes a workflow in an isolated run directory.

### J. There is no local generative-model path today

The registered model table contains hosted OpenAI, Anthropic, Google, and Hugging Face model identifiers (plato/llm.py:16-132). The graph readers instantiate those hosted clients, and EvalRunner's nightly workflow supplies hosted provider secrets (.github/workflows/eval-nightly.yml:24-41). A local OpenAI-compatible base URL or Ollama provider is not implemented.

LocalJupyterExecutor can run Python at zero token/model cost (plato/executor/local_jupyter.py:91-119, 238-286), but it is an executor, not a language model.

## Alignment with current primary benchmarks

The recommended design borrows evaluation principles rather than copying a benchmark wholesale.

| Benchmark | Primary lesson for Plato-Bio v2 |
|---|---|
| ScienceAgentBench (ICLR 2025) | Evaluate authentic workflow tasks separately; require self-contained executable programs, execution/result metrics, cost, multiple attempts, expert validation, and contamination controls. It used 102 tasks from 44 papers and nine subject-matter experts. https://proceedings.iclr.cc/paper_files/paper/2025/hash/f12b4df26344f3be803c06b555252efe-Abstract-Conference.html |
| BixBench | Use real multi-step biological datasets and open-answer result interpretation; over 50 scenarios and nearly 300 questions expose long-horizon bioinformatics weakness. The current public dataset is about 5.91 GB, so it is a second-phase external benchmark, not the smallest local slice. https://arxiv.org/abs/2503.00096 and https://huggingface.co/datasets/futurehouse/BixBench |
| BAISBench | Include real omics data, expert-labeled cell annotation, study-derived discovery questions, and a human baseline. Current v2 reports 15 expert-labeled datasets, 193 questions from 41 studies, and six graduate bioinformaticians. https://arxiv.org/abs/2505.08341 |
| BioDSA-1K | Score hypothesis decision, evidence-conclusion alignment, reasoning correctness, code executability, and an explicit Not Verifiable class. https://arxiv.org/abs/2505.16100 |
| BioVerge | Use historical biomedical hypotheses and PubMed literature, separate generation from evaluation, and test structured/textual evidence plus self-evaluation ablations. Its ABC literature-based discovery framing is directly applicable. https://arxiv.org/abs/2511.08866 |
| LAB-Bench | Measure foundational research capabilities separately; multiple-choice is used where automatic open-ended evaluation is unreliable. Passing is necessary, not sufficient, for research usefulness. https://www.futurehouse.org/research/lab-bench-measuring-capabilities-of-language-models-for-biology-research |
| CORE-Bench | Reproducing published results with code/data is a distinct prerequisite for discovery; use isolated, standardized execution and task-specific accuracy. https://arxiv.org/abs/2409.11363 |
| Virtual Lab nanobody study | A top-tier discovery claim couples the agent workflow to a novel computational pipeline and wet-lab confirmation. Plato-Bio should treat this as the long-term bar, not something a local literature benchmark can claim. https://www.nature.com/articles/s41586-025-09442-9 |

## Recommended smallest high-value implementation slice

### Name

Plato-Bio Temporal Rediscovery Pilot (PTRP).

### Scientific question

Given only a frozen corpus available before a known discovery, can Plato's evidence-aware novelty layer rank the later-reported biological relationship above plausible decoys while avoiding false claims of novelty for relationships already explicit in the pre-cutoff literature?

This is a retrospective temporal rediscovery test. A positive result supports the ranking method; it is not a prospective discovery.

### Pilot scope

- Ten tasks for the first publishable pilot; five tasks are acceptable only as an engineering smoke.
- At least three biological areas, such as metabolism/disease, gene/pathway/phenotype, and protein/function.
- One target A-C relationship per task first reported or strongly established after a declared cutoff.
- Pre-cutoff corpus: 50-300 title/abstract records per task.
- Positive target plus at least 20 decoy A-C candidate pairs.
- Two negative-control types:
  - already-known pairs directly co-mentioned before cutoff;
  - unsupported pairs with no sufficient bridge evidence.
- Exclude patient-level data, clinical treatment recommendations, high-risk pathogen engineering, and any task whose source/license or discovery date is ambiguous.

### Frozen fixture contract

Do not use the existing GoldenTask schema. Its fields describe idea/method generation, not temporal discovery (evals/tasks.py:50-65). Add a separate schema so endpoint semantics cannot drift.

Proposed owner:

- evals/biological_novelty/tasks.py
- evals/biological_novelty/fixtures/<task_id>/task.json
- evals/biological_novelty/fixtures/<task_id>/corpus.jsonl

TemporalNoveltyTask should contain:

- id and biological area;
- exact ISO cutoff date;
- target concept A and target concept C;
- aliases/identifiers for A and C;
- target relation text;
- validation PMID/DOI and first-publication date;
- bridge concepts allowed only for scoring diagnostics, not candidate generation;
- decoy pairs and labels;
- corpus path, license/provenance note, and SHA-256;
- task curator and independent reviewer status;
- explicit leakage exclusions;
- safety class and exclusion rationale.

FrozenLiteratureRecord should contain:

- PMID/PMCID/DOI;
- title and abstract;
- exact publication date and source of that date;
- authors/venue;
- controlled concept ids/aliases used for matching;
- retrieval timestamp and API URL;
- SHA-256 of the raw response or normalized record;
- injection-signal list.

The current Source model stores only year (plato/state/models.py:43-67). The pilot should own exact dates in its fixture schema instead of changing the production persistence model in the first slice.

### Deterministic candidate pipeline

Proposed production owners:

- plato/novelty/temporal_scorer.py
- plato/novelty/evidence_bridge.py
- plato/novelty/models.py

Proposed steps:

1. Validate every corpus record has published_at < cutoff. Reject unknown dates and fail the task on leakage.
2. Normalize declared concept aliases with token-boundary matching. Preserve exact matched spans and record ids.
3. Build an undirected weighted concept graph from independent source-level co-mentions.
4. Generate A-C candidates only where at least one A-B source and a different B-C source exist and no pre-cutoff source directly states A-C.
5. Fit a local scikit-learn TfidfVectorizer on the frozen corpus. Use cosine relevance for query-to-source and candidate-context scoring.
6. Compute transparent features:
   - independent bridge-source count;
   - distinct bridge-concept count;
   - minimum support on each side of the bridge;
   - TF-IDF relevance of A-B and B-C evidence;
   - direct-prior-art penalty;
   - contradictory/limitation source count;
   - source diversity;
   - evidence-date margin to cutoff;
   - provenance completeness.
7. Produce a weighted score whose initial weights are fixed before looking at target ranks.
8. Return ranked candidates with their complete evidence paths and an abstain reason when coverage is insufficient.
9. Persist results as JSONL and a manifest; never emit “discovered” or “true.” Use candidate, temporally novel, rediscovered target, or unsupported.

The key improvement over the current scorer is that a candidate cannot earn a high score merely because its text differs from retrieved papers. It must have positive bridge evidence, no direct pre-cutoff prior art, provenance, and enough corpus coverage.

### Baselines and ablations

Run identical frozen tasks under paired conditions:

| Condition | Purpose |
|---|---|
| Frequency baseline | Rank by direct term/co-mention frequency only. |
| TF-IDF baseline | Rank candidate context by lexical semantic relevance. |
| ABC bridge | Require A-B and B-C evidence; rank by bridge support. |
| Evidence-aware PTRP | ABC + TF-IDF + source diversity + prior-art/counter-evidence penalties. |

Ablations:

- minus strict temporal gate;
- minus TF-IDF relevance;
- minus source-independence requirement;
- minus direct-prior-art penalty;
- minus counter-evidence penalty;
- minus provenance-completeness gate;
- use current hash stub as a negative-control representation, explicitly labeled non-semantic.

Do not include “full Plato agent” in this deterministic table. That would mix a component benchmark with an unavailable hosted-model workflow.

### Primary and secondary endpoints

Primary endpoints:

- Recall@10: fraction of tasks whose hidden target is in the top ten.
- Mean reciprocal rank of the hidden target.
- False-novelty rate on already-known control pairs.

Secondary endpoints:

- nDCG@10 when multiple graded target/near-target labels exist;
- Precision@10 over curated target and plausible-positive labels;
- abstention rate and selective accuracy;
- evidence-path precision under manual audit;
- provenance completeness rate;
- target-rank stability under corpus bootstrap and alias perturbation;
- counter-evidence recall on curated limitation/negative sources;
- runtime and peak memory;
- percentage of tasks rejected for date/provenance leakage.

Do not use average abstract or residue rows as independent samples. The task is the unit of inference.

### Statistical analysis

- Freeze primary endpoints, scoring weights, and exclusions before the final run.
- Use paired per-task differences for all condition comparisons.
- Report 10,000-replicate stratified bootstrap 95% confidence intervals over tasks.
- Use an exact paired permutation test for reciprocal-rank/nDCG differences when task count permits.
- Use McNemar's exact test for paired target-in-top-10 outcomes.
- Report effect sizes and raw task-level results, not only P values.
- Apply Holm correction across the three primary condition comparisons or declare one primary comparison: evidence-aware PTRP versus ABC bridge.
- For a five-task smoke, report task rows and intervals only; do not claim significance.
- After the pilot, power the full task count from observed paired effects rather than choosing 20-30 retrospectively.

### Reproducibility artifacts

Proposed experiment owners:

- preprint/experiments/build_temporal_novelty_fixtures.py
- preprint/experiments/run_temporal_novelty_benchmark.py
- preprint/experiments/analyze_temporal_novelty_benchmark.py
- preprint/results/temporal_novelty/manifest.json
- preprint/results/temporal_novelty/task_results.csv
- preprint/results/temporal_novelty/candidates.jsonl
- preprint/results/temporal_novelty/condition_summary.csv
- preprint/results/temporal_novelty/bootstrap.json

The manifest should record:

- git commit and dirty status;
- fixture and raw-response hashes;
- cutoff and leakage policy;
- Python, NumPy, SciPy, scikit-learn, pandas, and statsmodels versions;
- vectorizer configuration and vocabulary hash;
- score weights;
- random/bootstrap seeds;
- task ids and exclusions;
- commands;
- runtime;
- output hashes.

The repository already demonstrates the desired pattern through the globin manifest and output hashes (preprint/experiments/run_globin_structure_benchmark.py:388-405).

### Tests

Proposed test owners:

- tests/unit/test_temporal_novelty_tasks.py
- tests/unit/test_evidence_bridge.py
- tests/unit/test_temporal_novelty_scorer.py
- tests/unit/test_temporal_novelty_metrics.py
- tests/unit/test_temporal_novelty_manifest.py
- tests/safety/test_temporal_novelty_injection.py

Required cases:

1. post-cutoff record causes hard failure;
2. unknown publication date causes hard failure;
3. A-B and B-C from the same source do not count as an independent bridge;
4. direct pre-cutoff A-C prior art applies a non-novel label;
5. duplicate DOI/PMID does not increase bridge support;
6. exact aliases use token boundaries and avoid substring collisions;
7. target rank is deterministic across processes;
8. hash stub performs worse than or equal to meaningful lexical baseline on a synthetic semantic fixture;
9. no evidence returns abstain, not a perfect novelty score;
10. malformed/poisoned abstract is blocked or quarantined with its signal persisted;
11. every candidate contains traceable evidence record ids;
12. bootstrap output is reproducible under a fixed seed;
13. fixture and output hashes are stable;
14. negative and already-known controls score correctly.

## Follow-on scientific-agent efficacy program

The PTRP slice is necessary but insufficient. The next v2 lane should evaluate full scientific workflows.

### Benchmark composition

Use four complementary task families rather than one monolithic score:

1. Literature retrieval: a small, license-compatible LAB-Bench/AutoResearchBench-style subset.
2. Biological data analysis: a pinned BixBench or BAISBench subset with public data capsules.
3. Hypothesis validation: BioDSA-style true/false/not-verifiable tasks with executable analysis.
4. Computational reproducibility: medicine/biology tasks modeled on CORE-Bench.

At least 20 total tasks across three biological domains are needed before a broad efficacy claim. Every task needs a versioned dataset, data license, checksum, expected artifacts, quantitative oracle, failure rubric, and expert review.

### Full-system conditions

Once a local model endpoint exists, compare:

1. deterministic/scripted oracle to verify the harness;
2. direct single-agent generation;
3. Plato idea/method only;
4. Plato full results/paper pipeline;
5. Plato full minus verification/evidence gates;
6. Plato full minus counter-evidence/gap detection;
7. optional original upstream Plato/Denario baseline.

Hold the model snapshot, prompts, tool environment, task data, budget, and attempt count fixed. Run at least five independent generations per task/condition after the deterministic pilot.

### Efficacy metrics

- task success and pass@k;
- executable-code rate;
- numerical/result accuracy;
- correct hypothesis decision including Not Verifiable;
- evidence-conclusion alignment;
- citation precision/recall;
- supported-claim precision/recall, not just unsupported rate;
- critical scientific error rate;
- human correction time;
- cost, latency, tokens, and tool failures;
- run-to-run reliability;
- human preference/quality under blinded expert review;
- provenance completeness.

LLM-judge scores can remain secondary. They must record each judge outcome, parsing status, and missingness; infrastructure failure must not become scientific zero.

### Human evaluation

- Recruit at least three independent domain experts.
- Blind system/condition identity and randomize output order.
- Use a frozen rubric for correctness, rigor, novelty framing, evidence quality, and usefulness.
- Record adjudication and inter-rater agreement.
- Keep machine and human endpoints separate.
- Predefine what constitutes a critical error.

## Biological novelty versus biological truth

The pipeline should emit three separate dimensions:

1. Prior-art novelty: is the exact relationship absent from the searched/frozen corpus?
2. Evidence plausibility: do independent sources support a mechanistic bridge?
3. Empirical validity: does new data or an independent experiment support the relationship?

Only the first two are available in PTRP. The third requires prospective computational or experimental validation. The software must not collapse them into one “novelty score.”

For prospective v2 hypotheses:

- label every output unvalidated candidate;
- require a human to approve an analysis plan;
- run a frozen, held-out public dataset;
- define falsification criteria before analysis;
- preserve negative results;
- seek independent replication;
- reserve “discovery” for a finding that survives independent confirmation.

The current v1 globin outputs are excellent reproducibility anchors but expected confirmation of known AlphaFold performance, not biological novelty (preprint/manuscript.md:103-137).

## Safety requirements

### Literature ingestion

The current literature path wraps suspicious abstracts and logs injection signals but retains the payload (plato/langgraph_agents/literature.py:185-245; tests/safety/test_prompt_injection.py:76-115). For frozen benchmark fixtures:

- scan at ingest;
- quarantine any signal at threshold one;
- persist the raw hash and signal list;
- use only sanitized normalized text for scoring;
- never let corpus text modify configuration or cutoff fields.

### Code execution

LocalJupyterExecutor launches a local kernel and executes supplied Python (plato/executor/local_jupyter.py:96-134, 138-238). SECURITY.md warns that generated code execution lacks a sandbox and should not run with production credentials or on shared hosts (SECURITY.md:39-68).

The deterministic PTRP implementation should not execute model-generated code. Later agent efficacy runs should use disposable containers, no secrets, read-only input mounts, bounded CPU/RAM/time, disabled network after fixture setup, and an isolated output directory.

### Biological dual-use and clinical scope

- Exclude pathogen enhancement, toxin optimization, wet-lab protocol optimization for harmful agents, and clinical treatment recommendation tasks from the pilot.
- Mark genomic/clinical tasks as research-only and non-diagnostic.
- Use public, non-identifiable data only.
- Require a task-level safety classification and human reviewer.
- Report excluded tasks and reasons rather than silently dropping them.

## Manuscript v2 experiment paths

Update the paper only after results are frozen.

Suggested new sections in preprint/manuscript.md:

- Methods: temporal rediscovery task construction;
- Methods: candidate generation and evidence scoring;
- Methods: baselines, ablations, and statistics;
- Results: novelty benchmark with per-task ranks and CIs;
- Results: leakage, abstention, and negative controls;
- Discussion: temporal rediscovery is not prospective discovery;
- Limitations: concept curation, abstract-only evidence, corpus incompleteness, and no wet-lab validation.

Suggested figures/tables:

- task/cutoff/validation-source table;
- paired target-rank plot across conditions;
- Recall@K curves with task-bootstrap CIs;
- false-novelty and abstention plot;
- example evidence bridge with exact source ids and dates;
- full task-level supplemental table;
- benchmark manifest and claim-to-evidence supplement.

Do not replace the v1 structural result. Treat it as a separate reproducibility case study and add the temporal benchmark as the first measurement of the novelty layer.

## Implementation order

### P0 — measurement contract

1. Add TemporalNoveltyTask and FrozenLiteratureRecord schemas.
2. Curate two synthetic fixtures and one real historical fixture.
3. Implement leakage validation and baseline metrics.
4. Add deterministic TF-IDF and ABC evidence bridge.
5. Persist complete ranked candidates and a manifest.
6. Add negative/already-known controls.
7. Run five-task engineering smoke.

### P1 — publishable pilot

1. Expand to ten independently reviewed tasks across at least three areas.
2. Freeze weights and analysis plan before final scoring.
3. Run paired conditions and bootstrap analysis.
4. Manually audit top-ten evidence paths.
5. Update manuscript and supplement with all task rows.

### P2 — agent efficacy

1. Add a local OpenAI-compatible model provider with explicit base URL/model digest.
2. Add an end-to-end eval runner that executes results and paper stages.
3. Add pinned BixBench/BAIS/BioDSA/CORE-style subsets.
4. Run multiple repetitions, baselines, and gate ablations.
5. Conduct blinded expert evaluation.

### P3 — genuine discovery

1. Generate prospective candidates on data unavailable to task curation.
2. Pre-register falsification analysis.
3. Validate on held-out data.
4. Obtain independent computational and ideally wet-lab confirmation.

## Validation commands

Current read-only validation executed:

    .venv/bin/python -m pytest -q --tb=short --no-header \
      tests/unit/test_eval_runner.py \
      tests/unit/test_golden_tasks_loadable.py \
      tests/unit/test_biology_domain.py \
      tests/unit/test_biology_end_to_end.py \
      tests/unit/test_embedding_novelty.py \
      tests/unit/test_composite_novelty.py \
      tests/unit/test_retrieval_orchestrator.py \
      tests/unit/test_pubmed_adapter.py \
      tests/unit/test_europe_pmc_adapter.py \
      tests/unit/test_counter_evidence.py \
      tests/unit/test_gap_detector.py \
      tests/unit/test_evidence_matrix_node.py \
      tests/unit/test_preprint_globin_benchmark.py

Result: 128 passed in 15.24 seconds. This proves current component contracts only.

Recommended v2 gates after implementation:

    .venv/bin/python -m pytest -q --tb=short \
      tests/unit/test_temporal_novelty_tasks.py \
      tests/unit/test_evidence_bridge.py \
      tests/unit/test_temporal_novelty_scorer.py \
      tests/unit/test_temporal_novelty_metrics.py \
      tests/unit/test_temporal_novelty_manifest.py \
      tests/safety/test_temporal_novelty_injection.py

    .venv/bin/python preprint/experiments/run_temporal_novelty_benchmark.py \
      --fixtures evals/biological_novelty/fixtures \
      --output preprint/results/temporal_novelty

    .venv/bin/python preprint/experiments/analyze_temporal_novelty_benchmark.py \
      --input preprint/results/temporal_novelty \
      --bootstrap-replicates 10000 \
      --seed 20260711

    .venv/bin/python -m pytest tests/unit tests/trajectory tests/safety -q --tb=short

    ruff check plato/novelty evals/biological_novelty preprint/experiments tests
    ruff format --check plato/novelty evals/biological_novelty preprint/experiments tests

## Coverage, depth, gaps, and assumption checks

### Coverage

| Area | Files/primary sources inspected | Depth |
|---|---:|---|
| Prior audit and post-audit git changes | prior report + 4 current commits | High |
| Novelty implementation | scorer modules, graph node, prompt, tests, dashboard references | High |
| Biology retrieval | domain, orchestrator, reranker, PubMed, Europe PMC, OpenAlex, tests | High |
| Evaluation harness | tasks, metrics, runner, judge, all golden fixtures, tests, nightly CI | High |
| Evidence and gap controls | evidence node, counter-evidence, gap detector, tests | High |
| Biological case study | script, manifest, target table, test, manuscript | High |
| Local execution/model feasibility | dependencies, installed packages, executors, model registry | High |
| Safety | SECURITY, sanitizer, prompt/PDF tests, executor boundary | High |
| External benchmark design | 8 primary papers/official project pages | Medium-high |
| Dashboard/product/deploy | only novelty/loop seams | Low by design |

### Depth

- Static call-site tracing confirms the quantitative novelty scorer is unwired.
- Source-model and adapter tracing confirms there is no exact temporal-cutoff contract.
- Dependency probing confirms what can run locally now.
- Current targeted tests were executed rather than inferred.
- v1 results and manuscript limitations were checked against their source scripts and machine-readable outputs.

### Gaps

- No independent domain expert reviewed this proposed task set.
- Historical discovery tasks have not yet been curated, so feasibility is architectural rather than empirical.
- Dataset redistribution and abstract licensing must be reviewed per fixture source before committing corpora.
- No local model was installed or benchmarked.
- BixBench and BAISBench were not downloaded because their current datasets are multi-gigabyte and unnecessary for the smallest slice.
- No prospective biological claim can be made from this report.

### Assumption checks

| Assumption | Check | Status |
|---|---|---|
| The v1 measurement bugs are fixed | Current code and regression tests inspected | Confirmed |
| Composite novelty affects live decisions | Repository-wide call-site search | False |
| The no-key embedding is semantic | Implementation inspected | False; hash stub |
| Biology retrieval is available without paid keys | PubMed/Europe PMC adapters inspected | Confirmed, network still required to build fixtures |
| Live retrieval is historically frozen | Adapter/query/state contracts inspected | False |
| The current biology eval is end-to-end | Runner and fake test inspected | False |
| Full generative evaluation can run locally now | Model registry, executables, installed packages checked | False |
| Deterministic temporal pilot can run locally | Installed NumPy/SciPy/scikit-learn/pandas/statsmodels checked | Confirmed |
| Temporal rediscovery equals new discovery | Scientific endpoint analysis | False |
| The proposed pilot can improve v2 evidence | Maps directly to unwired novelty and benchmark gaps | Strongly supported, pending task curation |

## Final recommendation

Implement PTRP before broadening the globin panel or spending on live agents. It is the smallest slice that:

- measures a presently claimed but unwired novelty capability;
- uses authentic biological literature and explicit historical cutoffs;
- supports deterministic baselines and ablations;
- runs in the current local environment;
- produces machine-readable, inspectable evidence;
- creates a clean bridge to later BixBench/BAIS/BioDSA-style full-agent evaluation.

Do not advertise a higher paper score merely because PTRP exists. Upgrade the manuscript claim only if the hidden target ranks improve over paired baselines with low false-novelty rates, complete provenance, stable results, and task-level uncertainty. Reserve a biological discovery claim for prospective held-out validation and independent confirmation.
