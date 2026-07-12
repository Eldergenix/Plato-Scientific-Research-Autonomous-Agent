# Plato-Bio preprint package

This directory contains a bioRxiv-oriented manuscript and the evidence used to produce it.

The author metadata is standardized across the portal and publication files as
**Stefan G. Creadore, Independent Researcher, Valrico, Florida, United States**
(ORCID: `0000-0003-2268-053X`; correspondence: `stefan@nex-t1.ai`).

The manuscript package is complete, but the current bioRxiv record was screened
out because bioRxiv requires a verifiable established research organization
with oversight responsibility. `Independent Researcher` is the accurate author
status, but it does not satisfy that requirement by itself. See
`SUBMISSION_METADATA.md` before attempting another deposit.

## Submission deliverables

- `Plato-Bio-bioRxiv-preprint.pdf` — upload this as the single main manuscript.
- `Plato-Bio-Supplement.pdf` — upload this as Supplemental Material.
- `Plato-Bio-bioRxiv-preprint.docx` — editable source for author revisions.
- `latex/plato-bio.tex` — self-contained LaTeX main manuscript.
- `latex/plato-bio-supplement.tex` — LaTeX supplementary material.
- `latex/Plato-Bio-LaTeX-preprint.pdf` — compiled LaTeX main manuscript.
- `latex/Plato-Bio-LaTeX-Supplement.pdf` — compiled LaTeX supplement.
- `latex/references.bib` — reusable BibTeX reference library.
- `manuscript.md` — canonical prose source.
- `SUBMISSION_METADATA.md` — paste-ready portal metadata and the required human confirmation gate.

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

## Interpretation boundary

This package validates software contracts, one historical rediscovery pilot, a synthetic engineering smoke, and a 15-target public structural screen. The historical pilot is retrospective, and all structural discrepancy regions are unvalidated hypotheses. It does not claim that the default evaluator runs results/paper stages, that self-critique is independent peer review, or that Plato has autonomously discovered a biological fact.
