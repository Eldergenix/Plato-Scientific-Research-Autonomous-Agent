---
id: research-2026-07-11-plato-scientific-manuscript-audit
type: research
date: 2026-07-11
backend: codex-sub-agents
---

# Research: Plato scientific manuscript audit

**Backend:** codex-sub-agents  
**Scope:** Plato's scientific-agent architecture, implemented and documented claims, evaluation design, available results and datasets, manuscript/reproducibility artifacts, tests, scientific limitations, authorship/metadata gaps, and work still required for a defensible bioRxiv preprint.  
**Repository:** `/Users/0xnexis/Downloads/plato-master` at the checked-out `main` worktree.  
**Non-goal:** This pass did not edit application code, existing user files, README, or manuscript content. It only created this research artifact.

## Executive conclusion

Plato has a substantial implementation and unit/trajectory test surface for multi-stage scientific-agent orchestration: separate idea/method and paper LangGraphs, multi-source retrieval, citation validation, claim/evidence linking, a four-axis reviewer loop, execution backends, reproducibility manifests, and an evaluation harness. The root README accurately identifies the intended end-to-end stages and major hardening components (`README.md:5-32`), and the paper graph statically orders drafting, citation validation, scientific verification, evidence linking, and review (`plato/paper_agents/agents_graph.py:99-181`).

However, at the start of this audit the repository did **not** contain the empirical evidence needed for a scientific systems paper about the current code. There were no tracked `evals/results/` metrics, no tracked system-evaluation tables/figures, no pre-existing tracked manuscript source, and no bioRxiv preset. More importantly, the current evaluation harness explicitly skips `get_results()` and `get_paper()` (`evals/runner.py:1-18`, `evals/runner.py:175-199`), the default biology task is constructed with the default astro domain (`evals/runner.py:467-483` versus `plato/plato.py:76-97`), and the CLI/dashboard autonomous loop does not execute a Plato workflow before rescoring existing manifests (`plato/cli.py:249-278`, `dashboard/backend/src/plato_dashboard/api/loop_control.py:216-245`). These are manuscript-blocking validity defects, not minor editorial issues.

The defensible paper today is therefore an **architecture and validation-protocol paper with explicitly preliminary results**, unless the measurement plumbing is repaired and a preregistered, replicated biological benchmark is completed. Unit-test success can substantiate software behavior, but it cannot support claims of improved scientific validity, autonomy, novelty, biological discovery, or manuscript quality.

There are also two distinct possible paper subjects in this checkout that must not be conflated: (A) a software/systems paper evaluating Plato, or (B) the local ART-clinic DEA application study. The current user request reads most naturally as (A), while the only local completed manuscript is (B). The ART artifact cannot supply Results for a Plato systems paper, and a Plato architecture description cannot cure the ART study's missing data/code/provenance.

## Research method and iterative retrieval record

The required three-cycle iterative retrieval procedure was executed.

### Pre-flight

- No repository-root `AGENTS.md` exists. The parent `../AGENTS.md` was read after the first five command boundary and applies to this tree.
- No `docs/code-map/` directory was present.
- `graphify` was not installed, so structural graph navigation fell through to scoped search and source reads.
- `ao` produced no prior-art results; scoped searches of `.agents/{research,learnings,knowledge,patterns,retros,plans,brainstorm}` and `~/.agents/patterns` produced no relevant prior artifact.
- Git history was scoped to `evals/`, paper agents, manifests, and the research loop. Relevant commits included the original eval harness, real-run wiring, citation/paper hardening, and two `loop: keep` commits.

### Cycle 1: broad discovery

Search terms: `autonomous`, `research agent`, `benchmark/evaluation`, `manuscript/paper`, `reproducibility`.

| Result | Relevance | Reason |
|---|---:|---|
| `README.md` | 0.90 | Public capability and workflow claims. |
| `evals/runner.py`, `evals/metrics.py`, `evals/tasks.py`, `evals/judge.py` | 1.00 | Direct benchmark implementation. |
| `evals/golden/*.json` | 0.95 | Complete benchmark prompt set and gold signals. |
| `plato/langgraph_agents/agents_graph.py` | 0.95 | Idea/method/literature architecture. |
| `plato/paper_agents/agents_graph.py` | 1.00 | Paper-generation architecture and gates. |
| `plato/loop/research_loop.py` | 1.00 | Claimed autonomous iteration implementation. |
| `plato/state/manifest.py` | 0.95 | Reproducibility data model. |
| `docs/features/*.md` | 0.80 | Design intent and public documentation. |
| `examples/*.ipynb` | 0.35 | Demonstrations with embedded outputs, not a controlled system evaluation. |
| dashboard screenshots | 0.15 | Product/UI evidence, not scientific evidence. |

Terms extracted from files scoring at least 0.5: `EvalRunner`, `GoldenTask`, `manifest.json`, `validation_report.json`, `evidence_matrix.jsonl`, `ResearchLoop`, `reviewer_panel`, `citation_validator_node`, `redraft_node`.

### Cycle 2: exact seam tracing

| Result | Relevance | Reason |
|---|---:|---|
| `tests/unit/test_eval_runner.py` | 0.95 | Shows eval behavior is heavily mocked and establishes what tests actually prove. |
| `tests/unit/test_biology_end_to_end.py` | 0.95 | Reveals biology “end-to-end” is a fake-Plato path with an explicit domain injection. |
| `tests/unit/test_research_loop.py` | 0.95 | Shows loop tests deliberately avoid real Plato. |
| `tests/trajectory/test_paper_graph_trajectory.py` | 0.90 | Static graph topology proof. |
| citation/evidence/revision/verifier tests | 0.90 | Component-level behavioral proof. |
| `.github/workflows/eval-nightly.yml` | 0.90 | Intended live eval environment and ephemeral result upload. |
| `docs/Write_paper/...pdf` and `examples/Project2/**` | 0.55 | Local completed scientific example, but ignored/untracked and unrelated to Plato system evaluation. |

Terms extracted: `latest_manifest_score`, `citation_validation_rate`, `unsupported_claim_rate`, `paper_v1.tex`, `paper_metadata`, `scientific_verifier_node`, `STRICT_ACCURACY_THRESHOLD`, `publication gate`, `expected_method_signals`.

### Cycle 3: validity and completeness checks

This cycle tested whether the discovered controls are both wired and scientifically measurable. It found the high-priority contradictions documented below: skipped heavy eval stages, default-domain leakage, unused method signals, unsupported default judge identifier, missing real pipeline invocation in the autonomous loop, same-model drafting/review, missing critique persistence, incomplete manifest wiring, no tracked evaluation output, no bioRxiv preset, and version/docs drift. No further high-relevance terms emerged, so retrieval stopped after the third cycle.

## Key files

| File | Purpose |
|---|---|
| `README.md` | Public product, workflow, paper, citation, and version claims. |
| `plato/plato.py` | Public orchestration API for idea, method, results, paper, referee, packaging. |
| `plato/langgraph_agents/agents_graph.py` | Idea/method/literature graph. |
| `plato/paper_agents/agents_graph.py` | Paper drafting, validation, evidence, review, and redraft graph. |
| `plato/paper_agents/scientific_verifier.py` | Artifact/reference/numeric-claim consistency checks. |
| `plato/paper_agents/citation_validator_node.py` | Mandatory reference validation and report emission. |
| `plato/tools/citation_reports.py` | 99.99% citation-accuracy gate calculation. |
| `plato/paper_agents/evidence_matrix_node.py` | Claim-to-source labels and unsupported-claim rate. |
| `plato/paper_agents/reviewer_panel.py` | Four reviewer nodes. |
| `plato/loop/research_loop.py` | Iterative score/keep/discard and git checkpoint mechanism. |
| `plato/state/manifest.py` | Run-manifest schema and atomic writer. |
| `evals/*` | Golden tasks, metrics, multi-model judge, runner, result aggregation. |
| `evals/golden/*.json` | Six prompt-based tasks (five astro, one biology). |
| `.github/workflows/eval-nightly.yml` | Nightly live-eval job and ephemeral artifact upload. |
| `tests/unit/*`, `tests/trajectory/*` | Component and structural proof; predominantly mocked for LLM/network behavior. |
| `plato/domain/__init__.py` | Astro and biology profiles. |
| `plato/executor/*` | Result-execution protocol and local/remote implementations. |
| `plato/paper_agents/journal.py` | Available journal/preprint presets (no bioRxiv preset). |

## Findings

### 1. Implemented architecture that can be described, with careful wording

#### 1.1 Public workflow

The public API exposes the intended sequence: describe data, generate an idea, generate a method, execute analysis, and draft a LaTeX manuscript (`README.md:72-119`). `Plato.get_paper` consumes `idea.md`, `methods.md`, `results.md`, and plot assets and supports a bounded reviewer loop (`plato/plato.py:1154-1192`).

The idea/method graph is a conditional LangGraph with a clarifier, maker/hater loop, novelty check, literature summary, claim extraction, counter-evidence search, gap detection, and referee path (`plato/langgraph_agents/agents_graph.py:38-120`). This supports an architectural claim that Plato uses explicit state-machine orchestration rather than a single prompt.

The paper graph contains a linear section-drafting chain followed by reference validation, scientific verification, claim extraction/evidence linking, four reviewer branches, aggregation, and a severity/cap-gated redraft loop (`plato/paper_agents/agents_graph.py:99-181`; routing threshold at `plato/paper_agents/routers.py:24-55`). This supports a static architecture claim; it does not prove that the loop improves papers.

#### 1.2 Reference and evidence controls

The citation validator collects structured/BibTeX sources, writes a validation report, blocks drafts with no references, and blocks when the computed accuracy gate fails (`plato/paper_agents/citation_validator_node.py:320-389`). The report gate requires at least one reference, a validation rate of at least 0.9999, and zero `LIKELY` hallucinations (`plato/tools/citation_reports.py:10-63`). The manuscript may truthfully describe this as a **configured validation gate**. It must not claim 99.99% observed citation accuracy until evaluated against independently curated labels.

The scientific verifier cross-checks quantitative claims, local artifact inventory, named analysis operations, provenance language, validation language, and the citation report, raising on blocking issues (`plato/paper_agents/scientific_verifier.py:54-177`). This is a heuristic consistency checker based partly on text patterns (`plato/paper_agents/scientific_verifier.py:13-50`), not an independent re-execution or proof of scientific correctness.

The paper graph explicitly places citation validation before the scientific verifier and evidence/review chain (`plato/paper_agents/agents_graph.py:137-181`). This topology is covered by structural tests, but topology alone does not establish semantic correctness (`tests/trajectory/test_paper_graph_trajectory.py:80-138`).

#### 1.3 Domain and execution extensibility

`DomainProfile` captures retrieval sources, keyword extraction, journal presets, executor, and novelty corpus (`plato/domain/__init__.py:21-44`). The built-in biology profile uses PubMed/Europe PMC and other scholarly indexes, MeSH keywords, `local_jupyter`, and PubMed novelty (`plato/domain/__init__.py:110-146`). This is relevant to a biological preprint, but actual biology efficacy is not established.

The executor contract returns results text, plot paths, structured artifacts, cost, and token counts (`plato/executor/__init__.py:37-80`). A deterministic synthetic scikit-learn executor uses fixed default sample/split/seed parameters (`plato/executor/sklearn_synthetic.py:30-66`) and stratified cross-validation (`plato/executor/sklearn_synthetic.py:80-125`). This is useful as a reproducibility smoke test, not as a benchmark of agentic scientific discovery.

#### 1.4 Reproducibility primitives

`RunManifest` has fields for workflow, timing/status, domain, git/project hashes, models, prompt hashes, seeds, sources, cost, and tokens (`plato/state/manifest.py:30-50`), and `ManifestRecorder` writes atomically (`plato/state/manifest.py:103-205`). These schema/writer claims are supported.

The system can create a submission ZIP containing canonical TeX/PDF, bibliography, verification reports, and figures (`plato/plato.py:1267-1335`). The package README itself correctly warns that author details, disclosures, cover letters, and ethics statements remain manual (`plato/plato.py:1293-1305`).

### 2. Evaluation assets exist, but there are no publishable benchmark results

The eval schema contains citation validation rate, unsupported-claim rate, novelty/referee/coherence scores, cost, tokens, latency, tool-error rate, keyword recall, and gold-source recall (`evals/metrics.py:22-56`). Six JSON tasks are present: five astronomy/physics prompts and one biology prompt. The protein task tests an AlphaFold/cryo-EM idea and lists two gold DOI strings (`evals/golden/protein_structure_alphafold.json:1-8`); the other domains/tasks are visible in `evals/golden/cmb_lensing_residuals.json:1-8`, `evals/golden/dark_matter_substructure.json:1-8`, `evals/golden/gw231123_followup.json:1-8`, `evals/golden/harmonic_oscillator.json:1-36`, and `evals/golden/stellar_classification_with_gaia.json:1-8`.

The nightly workflow installs the project, provides provider keys, runs `python -m evals.runner`, and uploads `evals/results/` as a GitHub Actions artifact (`.github/workflows/eval-nightly.yml:24-48`). No `evals/results/` file is tracked in the current checkout. Therefore, the repository exposes an experiment runner but not inspectable benchmark observations, confidence intervals, baselines, ablations, or result provenance.

The runner explicitly states and implements that `get_results` and `get_paper` are skipped (`evals/runner.py:6-18`, `evals/runner.py:175-199`). It falls back to scoring concatenated idea/method text when no paper exists (`evals/runner.py:214-240`). Consequently, fields named `paper_coherence` and `gold_source_recall` generally do **not** measure a paper in the default nightly run.

### 2.1 A separate local ART-clinic study exists, but is not reproducible

Ignored local files describe a DEA analysis of CDC National ART Surveillance System data. The data description points to a private/nonportable `/mnt/ceph/.../art_data_2020_2024.csv` path (`examples/Project2/input_files/data_description.md:50-63`). The methods document defines the intended clinic-year-age DMU but presents much of the filtering/calculation code as commented “Example” pseudocode and explicitly leaves exact category strings to be verified (`examples/Project2/input_files/methods.md:44-82`, `examples/Project2/input_files/methods.md:84-125`). No raw data, executable analysis script, prepared-data CSV, score CSV, checksum, or environment lock for this study is present.

The local results claim 1,126,080 initial records, 31,164 final DMUs, and missing local output paths (`examples/Project2/input_files/results.md:5-19`, `examples/Project2/input_files/results.md:38-46`). They define a DMU as unique clinic-year-age (`examples/Project2/input_files/results.md:9-13`) yet report 2,464-2,849 DMUs per year-age stratum (`examples/Project2/input_files/results.md:48-63`). That internal count pattern warrants a deduplication/filter-level audit against the raw CDC schema before any clinical interpretation; it is a risk signal, not a confirmed analytical error without the source data.

The ignored binary `docs/Write_paper/Project2/paper/paper_v2_no_citations.pdf` was inspected directly: it is an 11-page AASTeX draft titled “Efficiency and Performance Frontier Analysis of US ART Clinics (2020-2022) using Data Envelopment Analysis,” created 2025-08-06, with placeholder-like author/affiliation and astronomy keywords despite the clinical subject. Because it is binary, this observation is page-cited rather than line-cited (`docs/Write_paper/Project2/paper/paper_v2_no_citations.pdf`, p. 1). Its filename and content confirm it is not a citation-bearing, submission-ready artifact.

### 3. Submission-critical validity defects

#### P0-A — The autonomous loop does not run the research pipeline

The public documentation says each loop iteration runs the full pipeline (`docs/features/autonomous-loop.md:22-31`). In the CLI, the factory only constructs a `Plato` object and the scorer reads the latest existing manifest; no idea, literature, method, results, paper, referee, or mutation call occurs (`plato/cli.py:249-278`). The dashboard loop is more explicit: its default factory returns `None`, and every iteration scores existing manifests (`dashboard/backend/src/plato_dashboard/api/loop_control.py:216-245`).

`ResearchLoop.run` itself only calls the supplied factory and `score_fn`, then keeps/discards repository state (`plato/loop/research_loop.py:278-353`). Its unit tests state that they never instantiate real Plato and instead use deterministic mock scores (`tests/unit/test_research_loop.py:1-5`, `tests/unit/test_research_loop.py:78-105`). Thus the code proves a generic score/checkpoint loop, not autonomous research improvement. The manuscript must not claim a working “leave overnight and receive a refined paper” system without fixing and testing the invocation path.

#### P0-B — The eval harness does not evaluate the advertised end-to-end system

The runner only executes `set_data_description → get_idea → get_method` (`evals/runner.py:81-95`, `evals/runner.py:175-185`). Citation/evidence metrics are therefore usually zero-by-absence, and paper quality is judged from idea/method fallback text (`evals/runner.py:214-255`). A paper about end-to-end research, experiment execution, citation verification, reviewer revision, or compiled preprints cannot use this harness unchanged.

The default eval factory also drops `task.domain`: it constructs `Plato(project_dir=..., clear_project_dir=True)` (`evals/runner.py:467-483`), while `Plato` defaults to `domain="astro"` (`plato/plato.py:76-97`). The only biology “end-to-end” test uses a fake Plato and manually passes `domain=_task.domain` (`tests/unit/test_biology_end_to_end.py:176-217`). Therefore the nightly protein task currently exercises the astro profile, not the biology profile.

#### P0-C — The documented paper-review anti-self-grading safeguard is absent

Documentation claims each reviewer uses a different model, `get_paper` accepts `judge_models`, and the drafting model is rejected from the panel (`docs/features/reviewer-panel.md:63-68`). The actual `get_paper` signature has only one `llm` parameter and no `judge_models` argument (`plato/plato.py:1154-1162`). Drafting and all four reviewer nodes call the same `state["llm"]["llm"]` client (`plato/paper_agents/tools.py:35-61`; `plato/paper_agents/reviewer_panel.py:89-130`). This is self-review, not an independent panel.

The separate eval `LLMJudge` does enforce an identifier-level self-judge check (`evals/judge.py:66-94`), but one default judge identifier, `claude-sonnet-4-5`, is not registered in the current model table (`evals/runner.py:37-40`; current Claude keys at `plato/llm.py:117-120`). Judge errors are converted to zero scores rather than failed evaluations (`evals/judge.py:96-117`), which can silently depress panel medians.

#### P0-D — Gold method signals are never scored

`GoldenTask` defines `expected_method_signals` (`evals/tasks.py:50-65`), and every golden task supplies them, but the runner only scores idea keywords and gold sources (`evals/runner.py:221-240`). There is no method-signal metric in `Metrics` or the summary fields (`evals/metrics.py:22-56`, `evals/runner.py:422-450`). This removes a primary objective check of methodology quality.

#### P0-E — Reproducibility claims exceed current wiring

The docs say every workflow records prompt hashes, seeds, source IDs, model versions, tokens, and cost (`docs/features/manifest.md:1-32`). `get_paper` creates a recorder and callbacks but does not put the recorder into the graph state (`plato/plato.py:1201-1239`), while prompt hashing is a no-op when `state["recorder"]` is absent (`plato/paper_agents/tools.py:13-32`). The tests inject fake/real recorders manually into synthetic states (`tests/unit/test_prompt_hash_recording.py:29-65`; `tests/unit/test_r9_manifest_e2e.py:80-125`) and do not prove public API wiring.

`get_results` performs executor dispatch, moves plots, and writes results, but never starts or finishes a manifest (`plato/plato.py:989-1129`). Repository-wide source searches found no production `recorder.update(seeds=...)` or `recorder.update(source_ids=...)` call. Therefore the manuscript may describe the manifest **schema and atomic recorder**, but not complete end-to-end provenance capture until these fields are wired and demonstrated on real runs.

#### P0-F — No tracked manuscript/evaluation artifact can be submitted as-is

At audit start there was no pre-existing tracked `.tex`, `.bib`, system manuscript Markdown, `CITATION.cff`, CodeMeta file, Zenodo metadata file, evaluation summary, or scientific result figure for the current system. Manuscript files created concurrently by the main task are intentionally outside this read-only evidence baseline. The local checkout contained an ignored 11-page ART-clinic DEA example PDF and ignored supporting files under `docs/Write_paper/Project2` and `examples/Project2`; the ignore policy excludes `paper/`, bibliography files, `input_files/*`, plot outputs, and `uv.lock` (`.gitignore:3-13`, `.gitignore:200-225`). That local PDF is a generated domain paper about ART clinics, not an evaluation of Plato, and it is explicitly the `paper_v2_no_citations` artifact. It must not be repurposed as evidence for Plato's system manuscript.

#### P0-G — The unsupported-claim metric's producer and consumer disagree

The real `evidence_matrix_node` computes the in-memory unsupported-claim rate from drafted claims, but persists only `EvidenceLink` rows to `evidence_matrix.jsonl` (`plato/paper_agents/evidence_matrix_node.py:218-232`). The eval artifact reader requires Claim-shaped rows to establish the denominator and returns `0.0` when no claims are found (`evals/runner.py:379-409`). Its unit fixture manually writes both Claim and EvidenceLink rows (`tests/unit/test_eval_runner.py:331-420`), so it does not model the real producer. A real emitted matrix can therefore be scored as zero unsupported claims despite containing no persisted claim denominator. Any historical metric output using this path is invalid until recomputed from a corrected artifact contract.

### 4. Additional scientific and documentation gaps

#### 4.1 Benchmark breadth and biological relevance

Only one of six golden tasks is labeled biology, and it is a prompt description rather than a bundled dataset or reproducible experimental fixture (`evals/golden/protein_structure_alphafold.json:1-8`). The biology profile is implemented (`plato/domain/__init__.py:110-146`), but the repository does not contain a completed biological benchmark, expert labels, or biological case-study results. A bioRxiv submission needs a concrete biological research contribution or a convincing biological-methods evaluation, not an astro-dominant software demo.

#### 4.2 No baseline, ablation, repeats, or uncertainty analysis

The evaluator aggregates means/p50/p95 across tasks (`evals/runner.py:412-464`) but provides no baseline conditions, paired ablations, independent repeats, randomization plan, confidence intervals, or significance testing. Six heterogeneous tasks are also too few to interpret percentiles robustly. The configured LLM panel is not a substitute for blinded human scientific adjudication.

#### 4.3 Unit tests are predominantly implementation tests

The main eval tests declare that they use no real LLM/network and implement a fake Plato that writes synthetic manifests (`tests/unit/test_eval_runner.py:1-18`, `tests/unit/test_eval_runner.py:147-210`). The biology test likewise uses `_FakeBiologyPlato` (`tests/unit/test_biology_end_to_end.py:62-133`). These are appropriate software tests, but they cannot become manuscript result rows labeled “accuracy,” “quality,” or “end-to-end success.”

Reviewer parsing is also fail-open: malformed/non-dict reviewer output becomes severity 0 with no issues (`plato/paper_agents/reviewer_panel.py:75-86`). That behavior is acceptable for pipeline availability only if parse failure is separately recorded; it is unsafe as a scientific quality gate because infrastructure/model-format failures can look like clean reviews.

#### 4.4 Example and documentation drift

The root package version is `1.0.1` (`pyproject.toml:1-16`), while README says “What's new in 0.2” (`README.md:7-38`) and SECURITY calls the project pre-1.0 (`SECURITY.md:26-37`). The dashboard changelog says five golden tasks and stubbed executors (`dashboard/CHANGELOG.md:8-18`, `dashboard/CHANGELOG.md:107-112`) even though six task JSONs and concrete executor modules are present. The documented anti-self-grading and critique-sidecar behaviors also exceed the implementation (`docs/features/reviewer-panel.md:50-68`; no writer exists in `plato/paper_agents/reviewer_panel.py:89-130`).

The tracked full-workflow example calls `get_paper(..., add_citations=False)` (`examples/full_workflow.py:42-69`), but the current citation router always sends no-citation drafts into a gate that raises when no references exist (`plato/paper_agents/routers.py:8-21`; `plato/paper_agents/citation_validator_node.py:333-360`). The example is therefore incompatible with the current default gate.

#### 4.5 Reproducibility environment is not publication-frozen

Python compatibility is bounded, but most dependencies use ranges (`pyproject.toml:14-50`); a local `uv.lock` exists but is ignored (`.gitignore:216-219`). The production Dockerfile uses an unpinned `python:3.12-slim` base and installs a registry package rather than the checked-out source (`docker/Dockerfile.prod:1-38`). A manuscript release needs an immutable code tag/commit, committed environment lock or digest-pinned image, exact model snapshots, prompts, task data, and archival DOI.

Cost/budget reporting is also an estimate rather than complete accounting: unknown models return zero cost, and the table currently assigns both GPT-5.5 identifiers a zero price (`plato/observability/manifest_callback.py:1-7`, `plato/observability/manifest_callback.py:20-35`, `plato/observability/manifest_callback.py:68-74`). A paper must disclose the pricing snapshot and missing-price handling.

#### 4.6 Safety limitations must be stated

The security policy warns that LLM-generated code can execute in the same Python process without a sandbox and advises against shared hosts/production credentials (`SECURITY.md:39-68`). It also describes prompt-injection filtering as heuristic with residual risk (`SECURITY.md:70-90`). Any paper claiming safe autonomous research must state these limitations and separately evaluate containment and injection robustness.

### 5. Existing authorship and scholarly metadata

Package metadata lists Pablo Villanueva-Domingo, Francisco Villaescusa-Navarro, and Boris Bolliet as project authors (`pyproject.toml:5-12`), and README cites both a prior 2025 Plato paper with a much larger author list and the software artifact (`README.md:223-255`). A new manuscript must establish whether it is (a) a revision/extension of the prior paper, (b) a fork-specific paper, or (c) a new empirical study using Plato. Do not infer manuscript authorship from package metadata or commit history.

Missing manuscript-level metadata includes confirmed author order, affiliations, ORCIDs, corresponding author, CRediT contributions, funding, acknowledgments, competing interests, ethics/IRB status, data/code availability, prior-preprint relationship, and consent from upstream authors. The dashboard's `PublicationAuthor` model only records name, email, affiliation, a free-form role, and order (`dashboard/backend/src/plato_dashboard/domain/models.py:119-132`).

There is no `BIORXIV` journal enum or preset; the available preprint preset is `ARXIV`, alongside journal-specific presets (`plato/paper_agents/journal.py:6-48`, `plato/paper_agents/latex_presets.py:190-209`). The generated submission-package README is generic and explicitly delegates current author instructions/metadata to the operator (`plato/plato.py:1293-1305`).

## Tests executed in this audit

Command:

```bash
.venv/bin/python -m pytest -q --tb=short --no-header \
  tests/unit/test_eval_runner.py \
  tests/unit/test_golden_tasks_loadable.py \
  tests/unit/test_gold_source_coercion.py \
  tests/unit/test_research_loop.py \
  tests/unit/test_manifest.py \
  tests/unit/test_r9_manifest_e2e.py \
  tests/unit/test_citation_validator_node.py \
  tests/unit/test_evidence_matrix_node.py \
  tests/unit/test_revision_loop.py \
  tests/unit/test_scientific_verifier.py \
  tests/unit/test_paper_artifact_publish.py \
  tests/trajectory/test_paper_graph_trajectory.py
```

Result: **123 passed in 1.95 seconds**. This proves the selected component contracts and static topology in the current environment. It does not prove live provider behavior, end-to-end experiment execution, end-to-end paper generation, autonomous improvement, or scientific validity because the relevant tests explicitly use mocks/fakes (`tests/unit/test_eval_runner.py:1-18`, `tests/unit/test_research_loop.py:1-5`).

The independently dispatched repository explorer also ran broader regression lanes in the shared checkout:

- core suite: **909 passed, 6 skipped in 64.66 seconds**;
- dashboard backend: **267 passed in 17.13 seconds**;
- its targeted scientific/eval/paper selection: **97 passed in 1.34 seconds**.

The six core skips covered opt-in/missing live dependencies or credentials (E2B, Modal, Postgres, Hugging Face, and a platform-specific path case). These results materially strengthen software-regression confidence, but do not change the empirical manuscript blockers because the live end-to-end scientific benchmark remains absent.

## Test commands required or suggested by repository configuration

### Core gates

```bash
.venv/bin/python -m pytest tests/unit/ -q --tb=short --timeout=30
.venv/bin/python -m pytest tests/trajectory/ -q --tb=short --timeout=30 --no-header
.venv/bin/python -m pytest tests/safety/ -q --tb=short --timeout=30 --no-header
ruff check plato/ evals/ tests/
ruff format --check plato/ evals/ tests/
mypy --ignore-missing-imports --no-strict-optional --check-untyped-defs plato/state plato/retrieval plato/tools plato/io plato/safety plato/novelty plato/loop plato/domain plato/observability
python .github/scripts/check_import_cycles.py --root plato
```

These mirror `.github/workflows/test-fast.yml:36-68` and `.github/workflows/lint.yml:31-84`. Note that current CI masks trajectory and safety failures with `|| echo` (`.github/workflows/test-fast.yml:50-68`); a manuscript release should run them as hard gates.

### Dashboard and packaging

```bash
.venv/bin/python -m pytest dashboard/backend/tests -v --tb=short
cd dashboard/frontend && npm ci && npx tsc --noEmit
cd dashboard/frontend && npx playwright test
docker buildx build --file dashboard/Dockerfile --tag plato-dashboard:preprint --load .
```

The backend command is the configured workflow (`.github/workflows/dashboard-backend.yml:9-19`); frontend typecheck/Playwright are configured at `.github/workflows/dashboard-frontend.yml:9-61`.

### Optional/live integrations

```bash
PLATO_POSTGRES_DSN=postgresql://... pytest tests/integration/test_postgres_checkpointer.py -v --tb=short
PLATO_TEST_E2B=1 E2B_API_KEY=... pytest tests/integration/test_e2b_executor_live.py -v
PLATO_TEST_MODAL=1 pytest tests/integration/test_modal_executor_live.py -v
pytest tests/integration/test_huggingface_live.py -v
python -m evals.runner
bash scripts/security_smoke.sh
```

The Postgres workflow is specified at `.github/workflows/integration-postgres.yml:37-59`; E2B and Modal opt-in conditions are explicit at `tests/integration/test_e2b_executor_live.py:1-45` and `tests/integration/test_modal_executor_live.py:1-43`; the nightly eval command is `.github/workflows/eval-nightly.yml:30-48`; the local security scan contract is `scripts/security_smoke.sh:1-29`.

## Minimum defensible experiment program before manuscript claims

### Stage 0 — Repair measurement validity

1. Make the default eval factory pass `domain=task.domain`.
2. Add a method-signal metric and test it.
3. Run the actual `get_results`, `get_paper`, and compilation/verification stages or rename the harness to an idea/method benchmark and create a separate end-to-end harness.
4. Use the actual drafting model identifier(s) from manifests; require all judge models to be registered and fail/mark missing instead of turning infrastructure errors into scientific zeros.
5. Add independent reviewer models to `get_paper`, or state plainly that reviewer roles are same-model self-critique.
6. Wire the recorder through public graph states, add a `get_results` manifest, and populate source IDs, seeds, prompt hashes, executor/package versions, data hashes, and artifact hashes.
7. Align `evidence_matrix.jsonl` producer/consumer schemas and add a test that scores a real node-emitted artifact.
8. Make reviewer parse failures explicit error/missing outcomes, not severity-zero successes.
9. Make CLI/dashboard loop iterations execute a declared workflow before scoring. Never use `git add -A` or `reset --hard` against a user's dirty repository as experimental control; operate in isolated per-run worktrees/copies.
10. Persist raw judge responses, per-axis scores, validation/evidence artifacts, task outputs, and failed-run diagnostics.

### Stage 1 — Build a biological benchmark suitable for bioRxiv

- Freeze at least 20-30 biology tasks across molecular biology, genomics, structural biology, bioinformatics, single-cell analysis, and epidemiology/statistics.
- For each task, archive a versioned public dataset or deterministic fixture, license, checksum, expected method signals, curated sources, known quantitative checks, and failure criteria.
- Exclude tasks for which privacy, patient consent, or redistribution status is unresolved.
- Have at least two domain experts independently label claim support, citation correctness, methodological adequacy, and critical errors; report adjudication and inter-rater agreement.

### Stage 2 — Compare conditions and ablations

Use a paired design on identical frozen tasks and model snapshots:

1. Single-pass/basic Plato baseline.
2. + multi-source retrieval.
3. + citation gate.
4. + claim/evidence matrix.
5. + reviewer/revision loop.
6. Full corrected pipeline.
7. Optional external baseline(s), disclosed and version-pinned.

Run at least 5 independent repetitions per task/condition for stochastic models. Randomize order; record temperature/seed where supported, provider/model snapshot, prompts, code SHA, cost, token counts, latency, and retries.

### Stage 3 — Primary and secondary endpoints

Recommended primary endpoints:

- end-to-end completion rate;
- independently verified citation precision and recall;
- human-adjudicated unsupported factual-claim rate;
- critical methodological-error rate;
- quantitative-result correctness against known checks;
- reproducible artifact/manifest completeness;
- LaTeX compile and submission-package success.

Secondary endpoints:

- method-signal recall;
- blind human scores for rigor, coherence, novelty framing, and usefulness;
- cost, tokens, latency, and tool-call error rate;
- correction magnitude after each revision pass;
- safety outcomes for prompt injection and untrusted code execution.

Treat LLM-as-judge scores as secondary sensitivity measures, never sole ground truth.

### Stage 4 — Statistical analysis

- Report task-level raw outcomes and paired effect sizes, not only pooled means.
- Use hierarchical/bootstrap 95% confidence intervals over tasks and repetitions.
- Use paired permutation/Wilcoxon tests for condition comparisons where appropriate, with multiplicity control for multiple ablations/endpoints.
- Predefine missing/failure handling. A failed judge/provider call must remain a missing/infrastructure outcome, not a quality score of zero.
- Include robustness analyses by biological domain, task difficulty, model provider, and source availability.

### Stage 5 — Required figures/tables

1. Architecture/data-flow figure showing idea/method graph, executor, paper graph, validation artifacts, and manifest boundaries.
2. Benchmark/task composition table with data licenses and domains.
3. Paired ablation plot for primary endpoints with 95% CIs.
4. Citation precision/recall and unsupported-claim plots.
5. Cost/latency/completion trade-off plot.
6. Reviewer revision trajectory plot across passes.
7. Failure taxonomy table, including live-provider and safety failures.
8. Reproducibility checklist and artifact inventory.

## Recommended manuscript framing

Working title after experiments: **“Plato: an evidence-gated multi-agent workflow for reproducible biological research and manuscript generation.”** Use “evidence-gated” only after the end-to-end gate is empirically exercised; do not use “autonomous improvement” until the loop is repaired and evaluated.

Suggested structure:

1. Abstract — quantified benchmark outcomes only.
2. Introduction — problem, related systems, prior Plato paper, explicit new contribution.
3. System design — graphs, execution, retrieval, evidence, revision, provenance.
4. Biological benchmark and study design — frozen tasks/data, baselines, repetitions, human annotation, statistics.
5. Results — task-level and paired aggregate outcomes with uncertainty.
6. Case studies — successes and failures, including a fully reproducible biology run.
7. Safety, limitations, and responsible use.
8. Data/code availability and reproducibility statement.
9. Authorship, CRediT, funding, competing interests, ethics, acknowledgments.

## Claims allowed versus not yet supported

| Claim | Status |
|---|---|
| Plato implements explicit multi-stage LangGraph workflows | Supported by source/topology tests. |
| Plato has a configured 99.99% citation gate | Supported as configuration; **not** as observed accuracy. |
| Plato records a run-manifest schema atomically | Supported at component level. |
| Plato can package citation-bearing TeX/PDF and reports | Supported at component level. |
| Plato improves scientific quality | Unsupported; no baseline/ablation results. |
| Plato autonomously refines research overnight | Contradicted by default CLI/dashboard invocation paths. |
| Reviewer panel is independent/anti-self-grading | Contradicted for `get_paper`; same model is used. |
| Nightly eval is end-to-end | Contradicted; results/paper stages are skipped. |
| Biology evaluation uses the biology profile by default | Contradicted by default eval factory. |
| Plato achieves 99.99% citation accuracy | Unsupported and must not be stated. |
| Plato is bioRxiv-ready | Unsupported until biological experiments, metadata, manuscript source/PDF, and submission assets exist. |

## Coverage validation

Explored:

- root package/docs/config/readme/security;
- idea/method and paper graph construction;
- citation, evidence, scientific-verifier, reviewer, redraft, manifest, loop, domain, executor, and packaging implementations;
- all eval source files and six golden JSONs;
- scoped relevant unit, safety, trajectory, integration, and manual full-paper tests;
- CI workflows and test commands;
- tracked and ignored manuscript/result/figure candidates;
- relevant scoped git history and blame;
- dashboard publication/authorship models and loop adapter;
- scholarly metadata/preset searches.

Not explored deeply because they are noncritical to the manuscript decision: general dashboard UI implementation, deployment infrastructure, every retrieval-adapter body, every prompt body, and every historical commit. External bioRxiv rules are intentionally outside this repo-only subtask and are being handled separately by the main agent.

## Depth validation

| Area | Depth (0-4) | Assessment |
|---|---:|---|
| Core workflow architecture | 4 | Nodes, edges, routers, state and public entry points traced. |
| Citation/evidence/scientific gates | 4 | Gate calculation, artifacts, ordering, failure behavior traced. |
| Eval harness and tasks | 4 | Runner, metrics, judge, factory, all task JSONs, mocks, CI traced. |
| Autonomous loop | 4 | Generic loop, CLI adapter, dashboard adapter, tests, docs/history traced. |
| Reproducibility | 4 | Schema, writer, callback/state handoff, missing result manifest, locks traced. |
| Biological readiness | 3 | Domain/task/tool surfaces traced; no live biology experiment exists to inspect. |
| Existing manuscript assets | 3 | Tracked/ignored search and local PDF inspection completed; no system manuscript exists. |
| Authorship/submission metadata | 3 | Package/dashboard metadata inspected; final human choices necessarily unknown. |
| Live provider behavior | 1 | Not run; requires credentials, paid services, and a corrected study protocol. |

## Critical gaps and assumptions

1. **Unknown:** final manuscript authors, consent, affiliations, ORCIDs, contributions, conflicts, funding, corresponding author, and relation to the prior Plato paper.
2. **Unknown:** whether historical nightly eval artifacts exist in GitHub Actions. They are not in this checkout; if retrieved, they still require validity review because of the harness defects above.
3. **Unknown:** whether live Modal/E2B/Hugging Face/Postgres tests recently passed. Default/local proof cannot imply this.
4. **Unknown:** exact biological claim and target bioRxiv subject category.
5. **Assumption challenged:** docs are not authoritative evidence of wiring. Multiple public docs are stale or contradicted by source.
6. **Assumption challenged:** passing tests do not mean end-to-end scientific success; the highest-value tests explicitly mock the system.
7. **Assumption challenged:** local ignored example papers/plots are not release artifacts and cannot be attributed to the current system paper without provenance.

## Recommendations

1. Treat P0-A through P0-G as blockers before drafting Results/Discussion or making efficacy/autonomy claims.
2. Fix and test measurement plumbing first; otherwise new experimental numbers will be invalid by construction.
3. Retrieve any historical Action artifacts only as exploratory diagnostics, not final results.
4. Freeze a biology-first benchmark and analysis protocol before paid live runs.
5. Produce raw JSON/JSONL/CSV outputs, a deterministic analysis script, figures, a preprint manuscript source, compiled PDF, bibliography, data/code availability statements, and a release archive in the repository (or an archival DOI-linked companion repository).
6. Reconcile version/docs/security language and clearly distinguish upstream Plato from Eldergenix fork-specific contributions.
7. Obtain explicit human authorship and disclosure metadata before populating the preprint.
8. Use a neutral bioRxiv-compatible manuscript template/package rather than presenting the existing ARXIV preset as bioRxiv-specific.
