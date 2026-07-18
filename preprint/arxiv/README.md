# arXiv source package

`Plato-Bio-arXiv-source.zip` is the upload artifact for the Plato-Bio arXiv submission. It contains one top-level `plato-bio.tex` file and the six figures referenced by that file. The bibliography is embedded in the TeX source, so no external `.bbl` file is required.

Build the archive from the repository root after regenerating `preprint/latex/plato-bio.tex`:

```bash
.venv/bin/python preprint/arxiv/build_package.py
```

The builder normalizes figure paths for arXiv, rejects missing figures or unresolved parent-relative paths, and writes deterministic ZIP metadata.
