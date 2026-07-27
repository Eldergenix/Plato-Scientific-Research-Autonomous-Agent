# Plato

[![Python Version](https://img.shields.io/badge/python-%3E%3D3.12-blue.svg)](https://www.python.org/downloads/) [![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

Plato is a multi-agent research workflow that turns a data specification into
research ideas, methods, executable analyses, and manuscript drafts. Its
verification gates are designed to make evidence and limitations inspectable;
human authors remain responsible for scientific validity and publication.

## Plato-Bio preprint

**Plato-Bio: verification-first biological novelty screening with temporal
rediscovery and structural benchmarks** is a fork-specific methods and
validation study of Plato's computational-biology workflow. It asks a narrow
question: can an AI-assisted research system make its evidence, intermediate
claims, calculations, and limitations inspectable enough for a human scientist
to verify?

Stefan G. Creadore is the sole author, writing through **Praxa Labs, an
independent open-source research initiative, United States**. The manuscript is
prepared for arXiv with `cs.AI` as the primary category and `q-bio.QM` as a
cross-list. It has not been peer reviewed, and this repository does not claim
that arXiv submission or moderation validates its conclusions.

### Important links

- [Current preprint PDF](preprint/latex/Plato-Bio-LaTeX-preprint.pdf)
- [Supplementary PDF](preprint/latex/Plato-Bio-LaTeX-Supplement.pdf)
- [Canonical manuscript](preprint/manuscript.md)
- [LaTeX source](preprint/latex/plato-bio.tex) and
  [BibTeX references](preprint/latex/references.bib)
- [Reproduction and artifact guide](preprint/README.md)
- [arXiv source package](preprint/arxiv/Plato-Bio-arXiv-source.zip) and
  [submission metadata](preprint/ARXIV_SUBMISSION_METADATA.md)
- [Experiment scripts](preprint/experiments),
  [machine-readable results](preprint/results), and
  [figures](preprint/figures)
- [Author ORCID](https://orcid.org/0000-0003-2268-053X)
- [GitHub repository](https://github.com/Eldergenix/Plato-Scientific-Research-Autonomous-Agent)

### Abstract

Large language model research agents can connect literature retrieval,
analysis code, and manuscript preparation, but coherent output does not
establish scientific validity. Plato-Bio extends the open Plato/Denario
architecture with explicit workflow states, provenance records, citation
checks, claim-to-evidence links, scoped file writes, and publication gates. A
source audit found and repaired three measurement defects: loss of task domain
in the default evaluation factory, omission of declared method signals from
scoring, and evidence sidecars that lacked the drafted-claim denominator.

The study then evaluated two deliberately limited use cases. In one frozen
historical task, independent pre-1986 literature bridges ranked the
later-studied fish-oil/Raynaud relation first. In a separate comparison of
AlphaFold models with experimental structures for 15 human proteins, 11
targets had high-confidence-core Cα RMSD below 1 Å (median 0.501 Å), while 27
traceable discrepancy regions were retained as unvalidated hypotheses. These
results support reproducible software contracts and auditable screening
baselines—not autonomous discovery, general agent efficacy, or established
biological novelty.

### Overview

Plato represents research as explicit state machines rather than one
monolithic prompt. The biology profile routes retrieval and analysis toward
biomedical sources and tools; downstream controls emit citation reports,
claim/evidence matrices, consistency checks, run manifests, analysis outputs,
and manuscript artifacts. Human authors remain responsible for source review,
scientific interpretation, authorship, and publication.

The study separates three evidence lanes:

1. **Software-contract validation** tests whether implemented controls behave
   as declared.
2. **Temporal rediscovery** tests whether pre-cutoff literature can recover a
   relation studied later.
3. **Structural hypothesis triage** compares declared AlphaFold and
   experimental structures while preserving confidence and experimental
   context.

The lanes are complementary but not interchangeable. Passing software tests
does not measure biological accuracy, and a retrospective or descriptive
benchmark does not establish prospective novelty.

### Scientific study and experiments

| Experiment | Design | Primary outputs |
|---|---|---|
| Source audit and measurement repair | Inspected the evaluation factory, method-signal scoring, and claim/evidence persistence; added regression coverage for each repair | Correct biology routing, `method_signal_recall`, and Claim plus EvidenceLink JSONL records |
| Deterministic software validation | Ran biology, genomics-adapter, evidence/citation, adversarial-safety, and full Python suites on a clean recorded revision | 931 passes and 6 skips in the full suite; no failures or errors |
| Temporal rediscovery pilot | Ranked candidates from a frozen set of pre-1986 PubMed records, with later validation held out | Frequency, TF–IDF, A–B/B–C bridge, and evidence-aware rankings with explicit controls and abstention |
| Original globin comparison | Sequence-aware Cα alignment and Kabsch superposition for hemoglobin α, hemoglobin β, and myoglobin | Sub-ångström RMSD, residue-level error, pLDDT, source URLs, and hashes |
| Declared 15-protein structural screen | Compared AlphaFold predictions with experimental PDB structures using whole-chain and pLDDT≥70 core fits | Target/residue CSVs, bootstrap summaries, 27 traceable discrepancy regions, and `not_established` novelty labels |
| External benchmark alignment | Used ScienceAgentBench, BioDSA-1K, BixBench, and the pinned CompBioBench catalog as design constraints | Executable artifacts, baselines, provenance, abstention, and explicit failure boundaries; no claimed CompBioBench score |

### Results

- The complete recorded Python suite contained 937 tests: **931 passed, 6
  skipped, 0 failed, and 0 errored**. Targeted suites overlap with the full
  suite and therefore are not added to that total.
- In the single historical rediscovery task, corpus frequency ranked the
  held-out fish-oil/Raynaud relation third (MRR 0.333), TF–IDF ranked it second
  (MRR 0.500), and both bridge-only and evidence-aware conditions ranked it
  first (MRR and Recall@1 1.000). This is one retrospectively curated case, not
  a population estimate.
- The 15-target structure screen contained **2,688 matched residues**. Median
  whole-chain RMSD was 0.520 Å; median high-confidence-core RMSD was 0.501 Å,
  with 11 of 15 targets below 1 Å.
- Four targets retained core RMSD above 2 Å: KRAS, SUMO1, TP53, and estrogen
  receptor α. Confidence masking reduced SUMO1 from 16.610 Å over the whole
  chain to 2.576 Å over 74 high-confidence residues.
- The declared rule emitted **27 high-confidence discrepancy regions**, nine
  spanning at least two adjacent residues. Every region remains an
  unvalidated hypothesis requiring construct, ligand, oligomeric-state,
  alternate-structure, and experimental review.

### Conclusions

Plato-Bio demonstrates an inspectable route from retrieved literature or
predicted structures to candidate hypotheses. Its strongest contribution is
methodological: the workflow preserves known controls, abstentions, provenance,
and explicit `not_established` labels rather than treating difference or fluent
prose as discovery. General efficacy claims require a larger preregistered
benchmark, repeated agent runs, blinded expert adjudication, independent
replication, prospective analysis, and experimental validation.

### Selected scientific citations

1. King RD, et al. “The automation of science.” *Science* (2009).
   [doi:10.1126/science.1165620](https://doi.org/10.1126/science.1165620)
2. Lu C, et al. “The AI Scientist: Towards Fully Automated Open-Ended
   Scientific Discovery” (2024).
   [arXiv:2408.06292](https://arxiv.org/abs/2408.06292)
3. Schmidgall S, et al. “Agent Laboratory: Using LLM Agents as Research
   Assistants” (2025).
   [arXiv:2501.04227](https://arxiv.org/abs/2501.04227)
4. Villaescusa-Navarro F, et al. “The Denario project: deep knowledge AI
   agents for scientific discovery” (2025).
   [arXiv:2510.26887](https://arxiv.org/abs/2510.26887)
5. Varadi M, et al. “AlphaFold Protein Structure Database.” *Nucleic Acids
   Research* (2022).
   [doi:10.1093/nar/gkab1061](https://doi.org/10.1093/nar/gkab1061)
6. Jumper J, et al. “Highly accurate protein structure prediction with
   AlphaFold.” *Nature* (2021).
   [doi:10.1038/s41586-021-03819-2](https://doi.org/10.1038/s41586-021-03819-2)
7. Chen Z, et al. “ScienceAgentBench: Toward Rigorous Assessment of Language
   Agents for Data-Driven Scientific Discovery.” *ICLR* (2025).
   [Conference paper](https://proceedings.iclr.cc/paper_files/paper/2025/hash/f12b4df26344f3be803c06b555252efe-Abstract-Conference.html)
8. Wang Z, et al. “BioDSA-1K: Benchmarking Data Science Agents for Biomedical
   Research” (2025).
   [arXiv:2505.16100](https://arxiv.org/abs/2505.16100)
9. Mitchener L, et al. “BixBench: A Comprehensive Benchmark for LLM-Based
   Agents in Computational Biology” (2025).
   [arXiv:2503.00096](https://arxiv.org/abs/2503.00096)

The [canonical manuscript](preprint/manuscript.md) contains the complete
reference list, including the PDB, Kabsch, lDDT, FAIR, and historical Raynaud
literature used by the experiments.

### Reproduce the study

The validation package records exact literature cutoffs, PMIDs, candidate
rankings, abstentions, input URLs, versions, SHA-256 hashes, target- and
residue-level structural results, exact test counts, and figure-generation
code:

```bash
.venv/bin/python preprint/experiments/run_globin_structure_benchmark.py
.venv/bin/python preprint/experiments/run_globin_structure_benchmark.py --panel-file preprint/experiments/diverse_structure_panel.json --output-dir preprint/results/diverse_structure_benchmark --figures-dir preprint/figures --benchmark-name diverse_structure_panel
.venv/bin/python preprint/experiments/run_temporal_novelty_benchmark.py --fixtures evals/biological_novelty/fixtures/historical_pilot.json --output-dir preprint/results/temporal_novelty_historical_pilot
.venv/bin/python -m evals.biomedical_benchmarks
.venv/bin/python preprint/experiments/run_software_validation.py
.venv/bin/python preprint/experiments/build_summary_figures.py
```

The historical benchmark contains one manually curated retrospective task, and
the 27 structural discrepancy regions are hypothesis candidates with novelty
explicitly marked `not_established`. The evidence does **not** establish
autonomous discovery, independent peer review, prospective biological novelty,
or live end-to-end LLM efficacy. The imported 100-task CompBioBench catalog is
coverage metadata, not a performance claim.

## What's new in 1.0.1

Phase 5 hardening landed alongside the dashboard's 13-stream feature push:

- **Multi-source retrieval** — scholarly-source adapters behind a domain-aware
  orchestrator with rate-limit
  backoff, ETag caching, and per-host circuit breakers.
- **Citation validation** — every reference is resolved against Crossref +
  Retraction Watch + arXiv before the paper finalizes. The run dir gets a
  `validation_report.json` with per-reference pass/fail.
- **Claim → Evidence Matrix** — the literature pass extracts atomic claims
  with quote spans and links them to source records. Persisted as
  `evidence_matrix.jsonl` per run.
- **Reviewer-role revision loop** — methodology / statistics / novelty /
  writing axes feed an aggregator that drives a bounded redraft loop. These
  roles currently use the drafting client and are self-critique, not independent
  peer review.
- **Research-loop scaffold** — `plato loop --hours 8 --max-cost-usd 50`
  provides wall-clock/cost budgeting and git keep/discard checkpoints. The
  default adapters score existing artifacts; they do not yet execute a complete
  research cycle.
- **Reproducibility manifest primitives** — the manifest schema and recorder can
  capture git/project hashes, models, prompts, seeds, sources, tokens, and cost
  when supplied by the calling workflow; public-path coverage is not yet
  complete.
- **Observability** — opt in by setting `LANGFUSE_*` env vars; LangFuse
  callbacks are wired into every LangGraph invocation.
- **Pluggable domains** — `DomainProfile` registry exposes retrieval,
  keyword extractor, journal preset, executor, and novelty corpus as swap
  points. Astro is the default; biology ships out-of-the-box.
- **Multi-tenant dashboard** — set `PLATO_DASHBOARD_AUTH_REQUIRED=1` and
  the dashboard reads `X-Plato-User` from the upstream proxy to scope
  every project, key store, and run artifact per tenant.

See `docs/adr/` for the design decisions behind these changes and
`dashboard/CHANGELOG.md` for the full list.

## Resources

- [Live Plato demo](https://plato-production-9fea.up.railway.app)

- [GitHub repository](https://github.com/Eldergenix/Plato-Scientific-Research-Autonomous-Agent)

- [Prior Denario systems paper](https://arxiv.org/abs/2510.26887)


## Installation

To install plato create a virtual environment and pip install it. We recommend using Python 3.12:

```bash
python -m venv Plato_env
source Plato_env/bin/activate
pip install "plato[dashboard]"
```

Or alternatively install it with [uv](https://docs.astral.sh/uv/), initializing a project and installing it:

```bash
uv init
uv add plato[dashboard]
```

Then, run the Plato dashboard with:

```
plato dashboard
```

## Get started

Initialize a `Plato` instance and describe the data and tools to be employed.

```python
from plato import Plato

p = Plato(project_dir="project_dir")

prompt = """
Analyze the experimental data stored in data.csv using sklearn and pandas.
This data includes time-series measurements from a particle detector.
"""

p.set_data_description(prompt)
```

Generate a research idea from that data specification.

```python
p.get_idea()
```

Generate the methodology required for working on that idea.

```python
p.get_method()
```

With the methodology setup, perform the required computations and get the plots and results.

```python
p.get_results()
```

Finally, generate a latex article with the results. You can specify the journal style, in this example we choose the [APS (Physical Review Journals)](https://journals.aps.org/) style.

```python
from plato import Journal

p.get_paper(journal=Journal.APS)
```

You can also manually provide any info as a string or markdown file in an intermediate step, using the `set_idea`, `set_method` or `set_results` methods. For instance, for providing a file with the methodology developed by the user:

```python
p.set_method(path_to_the_method_file.md)
```

## Plato Dashboard (new, recommended)

A Linear-themed real-time web dashboard with full pipeline visualization, cost tracking, and live agent log streaming. See [dashboard/README.md](dashboard/README.md) for setup.

```bash
pip install "plato[dashboard]"
plato dashboard
```

The dashboard supersedes the legacy `plato run` Streamlit app for new workflows.

For hosted Railway SaaS/Lab deployments with Clerk auth or Clerk Billing, run
the local production gates and redacted strict preflight before deploying:

```bash
bash dashboard/scripts/check-local-production-gates.sh
bash dashboard/scripts/check-hosted-saas-preflight.sh --railway --service plato --environment production --hosted-required --strict
```

It verifies the Clerk user/Lab auth contract, `PLATO_BACKEND_PROXY_SECRET`,
public origin, Clerk proxy, and hosted billing flags without printing secret
values. Strict mode treats preflight warnings as release blockers. After
deploying, use the read-only production readiness check to probe the live app
and scan Railway logs:

```bash
bash dashboard/scripts/check-production-readiness.sh --service plato --environment production --origin https://discovering.app
```

If `railway variables --json`/`--kv` is unavailable but you have a local
Railway variables snapshot, pass it with `--variables-file`; the checker still
prints only redacted key status and lengths:

```bash
bash dashboard/scripts/check-production-readiness.sh --service plato --environment production --origin https://discovering.app --variables-file /path/to/railway-variables.json
```

See [dashboard/RAILWAY.md](dashboard/RAILWAY.md) for the full production
variable matrix.

## Build from source

### pip

You will need python 3.12 or higher installed. Clone Plato:

```bash
git clone https://github.com/Eldergenix/Plato-Scientific-Research-Autonomous-Agent.git
cd Plato-Scientific-Research-Autonomous-Agent
```

Create and activate a virtual environment

```bash
python3 -m venv Plato_env
source Plato_env/bin/activate
```

And install the project

```bash
pip install -e .
```

### uv

You can also install the project using [uv](https://docs.astral.sh/uv/), just running:

```bash
uv sync
```

which will create the virtual environment and install the dependencies and project. Activate the virtual environment if needed with

```bash
source .venv/bin/activate
```

## Docker

You can run Plato with [Docker](https://www.docker.com/) using the dashboard compose file:

```bash
docker compose -f dashboard/compose.yaml up --build
```

The local dashboard runs on `http://localhost:7878` by default.

You can also build an image locally with

```bash
docker build -f docker/Dockerfile.dev -t plato_src .
```

## Contributing

Pull requests are welcome! Feel free to open an issue for bugs, comments, questions and suggestions.

## Citation

If you make use of Plato, please cite the following references:

```bibtex
@article{villaescusanavarro2025platoprojectdeepknowledge,
         title={The Plato project: Deep knowledge AI agents for scientific discovery}, 
         author={Francisco Villaescusa-Navarro and Boris Bolliet and Pablo Villanueva-Domingo and Adrian E. Bayer and Aidan Acquah and Chetana Amancharla and Almog Barzilay-Siegal and Pablo Bermejo and Camille Bilodeau and Pablo Cárdenas Ramírez and Miles Cranmer and Urbano L. França and ChangHoon Hahn and Yan-Fei Jiang and Raul Jimenez and Jun-Young Lee and Antonio Lerario and Osman Mamun and Thomas Meier and Anupam A. Ojha and Pavlos Protopapas and Shimanto Roy and David N. Spergel and Pedro Tarancón-Álvarez and Ujjwal Tiwari and Matteo Viel and Digvijay Wadekar and Chi Wang and Bonny Y. Wang and Licong Xu and Yossi Yovel and Shuwen Yue and Wen-Han Zhou and Qiyao Zhu and Jiajun Zou and Íñigo Zubeldia},
         year={2025},
         eprint={2510.26887},
         archivePrefix={arXiv},
         primaryClass={cs.AI},
         url={https://arxiv.org/abs/2510.26887},
}

@software{Plato_2025,
          author = {Pablo Villanueva-Domingo, Francisco Villaescusa-Navarro, Boris Bolliet},
          title = {Plato: Modular Multi-Agent System for Scientific Research Assistance},
          year = {2025},
          url = {https://github.com/Eldergenix/Plato-Scientific-Research-Autonomous-Agent},
          note = {Available at https://github.com/Eldergenix/Plato-Scientific-Research-Autonomous-Agent},
          version = {latest}
          }

@software{CMBAGENT_2025,
          author = {Boris Bolliet},
          title = {CMBAGENT: Open-Source Multi-Agent System for Science},
          year = {2025},
          url = {https://github.com/CMBAgents/cmbagent},
          note = {Available at https://github.com/CMBAgents/cmbagent},
          version = {latest}
          }
```

## License

[GNU GENERAL PUBLIC LICENSE (GPLv3)](https://www.gnu.org/licenses/gpl-3.0.html)

Plato - Copyright (C) 2026 Pablo Villanueva-Domingo, Francisco Villaescusa-Navarro, Boris Bolliet
