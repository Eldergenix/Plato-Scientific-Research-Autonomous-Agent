# Plato-Bio preprint package

This directory contains a bioRxiv-oriented manuscript and the evidence used to produce it.

## Submission deliverables

- `Plato-Bio-bioRxiv-preprint.pdf` — upload this as the single main manuscript.
- `Plato-Bio-Supplement.pdf` — upload this as Supplemental Material.
- `Plato-Bio-bioRxiv-preprint.docx` — editable source for author revisions.
- `latex/plato-bio.tex` — self-contained LaTeX main manuscript.
- `latex/plato-bio-supplement.tex` — LaTeX supplementary material.
- `latex/references.bib` — reusable BibTeX reference library.
- `manuscript.md` — canonical prose source.
- `SUBMISSION_METADATA.md` — paste-ready portal metadata and the required human confirmation gate.

## Reproduce the evidence

```bash
.venv/bin/python preprint/experiments/run_globin_structure_benchmark.py
.venv/bin/python preprint/experiments/run_software_validation.py
.venv/bin/python preprint/experiments/build_summary_figures.py
```

The structural benchmark downloads declared RCSB PDB and AlphaFold DB records only when the cached raw files are absent. The output manifest records upstream URLs, versions, and SHA-256 hashes. The software-validation script writes exact pytest/JUnit counts and environment metadata.

## Build and verify the manuscript

```bash
/Users/0xnexis/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 preprint/build_manuscript.py
```

The builder creates the DOCX and supplemental DOCX. The repository workflow then renders both with the bundled LibreOffice renderer, visually inspects every page, and retains the generated PDFs as submission artifacts.

The LaTeX package is generated from the same canonical Markdown and result
files. See `latex/README.md` for reproducible Tectonic compilation commands.

## Interpretation boundary

This package validates software contracts and one deterministic public-data biological computation. It does not claim that the default evaluator runs results/paper stages, that self-critique is independent peer review, or that Plato autonomously improves scientific research.
