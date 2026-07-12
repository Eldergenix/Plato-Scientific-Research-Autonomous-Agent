# Plato-Bio LaTeX publication package

This directory contains a journal-portable LaTeX representation of the main
Plato-Bio manuscript and its supplementary material.

## Files

- `plato-bio.tex` — generated, self-contained main manuscript.
- `plato-bio-supplement.tex` — generated supplementary manuscript.
- `references.bib` — reusable BibTeX records for journal resubmission.
- `build_latex.py` — regenerates both TeX sources from the canonical manuscript
  and machine-readable experiment outputs.
- `Plato-Bio-LaTeX-preprint.pdf` — compiled main manuscript.
- `Plato-Bio-LaTeX-Supplement.pdf` — compiled supplement.

## Regenerate and compile

```bash
.venv/bin/python preprint/latex/build_latex.py
python3 /Users/0xnexis/.codex/plugins/cache/openai-bundled/latex/0.2.4/scripts/compile_latex.py \
  /Users/0xnexis/Downloads/plato-master/preprint/latex/plato-bio.tex \
  --output-directory /Users/0xnexis/Downloads/plato-master/preprint/latex/build
python3 /Users/0xnexis/.codex/plugins/cache/openai-bundled/latex/0.2.4/scripts/compile_latex.py \
  /Users/0xnexis/Downloads/plato-master/preprint/latex/plato-bio-supplement.tex \
  --output-directory /Users/0xnexis/Downloads/plato-master/preprint/latex/build
```

The checked-in TeX embeds its numbered references so it compiles with the
bundled Tectonic runtime. `references.bib` is supplied separately for journals
that require BibTeX or a publisher-specific class.
