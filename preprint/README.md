# Plato-Bio preprint package

This directory contains the arXiv-oriented manuscript, submission source, and evidence used to produce it.

The author metadata is standardized across the portal and publication files as
**Stefan G. Creadore, Praxa Labs, an independent open-source research initiative, United States**
(ORCID: `0000-0003-2268-053X`; correspondence: `stefan@nex-t1.ai`).

The current release targets arXiv category `q-bio.QM`, with `cs.AI` as a
cross-list. The earlier bioRxiv package and screening record are retained for
provenance; they are not the files to use for a new arXiv submission.

## Current arXiv deliverables

- `arxiv/Plato-Bio-arXiv-source.zip` — upload this TeX source archive as the main submission.
- `latex/Plato-Bio-LaTeX-preprint.pdf` — locally compiled reference PDF; do not upload it in place of TeX source.
- `latex/Plato-Bio-LaTeX-Supplement.pdf` — optional supplementary reference PDF.
- `Plato-Bio-arXiv-preprint.docx` — editable source for author revisions.
- `latex/plato-bio.tex` — self-contained LaTeX main manuscript.
- `latex/plato-bio-supplement.tex` — LaTeX supplementary material.
- `latex/references.bib` — reusable BibTeX reference library.
- `manuscript.md` — canonical prose source.
- `ARXIV_SUBMISSION_METADATA.md` — ASCII-safe portal metadata and the required human confirmation gate.

## Historical bioRxiv deliverables

- `Plato-Bio-bioRxiv-preprint.pdf` and `Plato-Bio-bioRxiv-preprint.docx` are the July 2026 bioRxiv-oriented artifacts.
- `SUBMISSION_METADATA.md` records the bioRxiv screening outcome and must not be used as arXiv portal metadata.

## Reproduce the evidence

```bash
.venv/bin/python preprint/experiments/run_globin_structure_benchmark.py
.venv/bin/python preprint/experiments/run_globin_structure_benchmark.py --panel-file preprint/experiments/diverse_structure_panel.json --output-dir preprint/results/diverse_structure_benchmark --figures-dir preprint/figures --benchmark-name diverse_structure_panel
.venv/bin/python preprint/experiments/run_temporal_novelty_benchmark.py --fixtures evals/biological_novelty/fixtures/engineering_smoke.json --output-dir preprint/results/temporal_novelty_smoke
.venv/bin/python preprint/experiments/run_temporal_novelty_benchmark.py --fixtures evals/biological_novelty/fixtures/historical_pilot.json --output-dir preprint/results/temporal_novelty_historical_pilot
.venv/bin/python -m evals.biomedical_benchmarks
.venv/bin/python preprint/experiments/run_software_validation.py
.venv/bin/python preprint/experiments/build_summary_figures.py
```

The structural benchmarks download declared RCSB PDB and AlphaFold DB records only when cached raw files are absent. The manifests record upstream URLs, versions, methods, resolutions, and SHA-256 hashes. The temporal benchmark freezes publication cutoffs and evidence paths. The CompBioBench importer pins and verifies its task catalog but does not report agent performance. The software-validation script writes exact pytest/JUnit counts and environment metadata.

## Build and verify the manuscript

```bash
/Users/0xnexis/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 preprint/build_manuscript.py
```

The builder creates the DOCX and supplemental DOCX. The repository workflow then renders both with the bundled LibreOffice renderer, visually inspects every page, and retains the generated PDFs as submission artifacts.

The LaTeX package is generated from the same canonical Markdown and result
files. See `latex/README.md` for reproducible Tectonic compilation commands.
Build the arXiv upload archive after regenerating LaTeX:

```bash
.venv/bin/python preprint/arxiv/build_package.py
```

## Interpretation boundary

This package validates software contracts, one historical rediscovery pilot, a synthetic engineering smoke, and a 15-target public structural screen. The historical pilot is retrospective, and all structural discrepancy regions are unvalidated hypotheses. It does not claim that the default evaluator runs results/paper stages, that self-critique is independent peer review, or that Plato has autonomously discovered a biological fact.
