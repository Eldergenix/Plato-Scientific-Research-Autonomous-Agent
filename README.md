# Plato

[![Python Version](https://img.shields.io/badge/python-%3E%3D3.12-blue.svg)](https://www.python.org/downloads/) [![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

Plato is a multi-agent research workflow that turns a data specification into
research ideas, methods, executable analyses, and manuscript drafts. Its
verification gates are designed to make evidence and limitations inspectable;
human authors remain responsible for scientific validity and publication.

## Research validation and bioRxiv preprint

This repository now includes a submission-oriented computational biology study:
**“Plato-Bio: a verification-first multi-agent research workflow with a
reproducible structural-biology case study.”** The paper combines a source-code
audit, deterministic software validation, and a declared public-data comparison
of AlphaFold DB globin models with RCSB PDB structures.

- [Main preprint (PDF)](preprint/Plato-Bio-bioRxiv-preprint.pdf)
- [Supplementary material (PDF)](preprint/Plato-Bio-Supplement.pdf)
- [Editable manuscript (DOCX)](preprint/Plato-Bio-bioRxiv-preprint.docx)
- [Submission metadata and human confirmation gate](preprint/SUBMISSION_METADATA.md)
- [Reproduction guide](preprint/README.md)

The validation package records input URLs, versions, SHA-256 hashes, target- and
residue-level structural results, exact test counts, and figure-generation code.
Reproduce it with:

```bash
.venv/bin/python preprint/experiments/run_globin_structure_benchmark.py
.venv/bin/python preprint/experiments/run_software_validation.py
.venv/bin/python preprint/experiments/build_summary_figures.py
```

The reported evidence does **not** establish autonomous scientific improvement,
independent peer review, or live end-to-end LLM efficacy. The default evaluation
runner exercises the idea and method stages; live provider, hosted database, and
authenticated external-service paths remain separate validation lanes.

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
- **Reviewer panel + revision loop** — methodology / statistics / novelty /
  writing axes feed an aggregator that drives a redraft loop bounded by
  `Plato.get_paper(max_revision_iters=...)`.
- **Autonomous research loop** — `plato loop --hours 8 --max-cost-usd 50`
  iterates under a wall-clock + cost budget, committing improvements and
  reverting regressions.
- **Reproducibility manifest** — every workflow emits `manifest.json` with
  git sha, project sha-256, model versions, source ids, tokens, and cost.
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

<!-- ## Citation

If you use this library please link this repository and cite [arXiv:2506.xxxxx](arXiv:x2506.xxxxx). -->

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
