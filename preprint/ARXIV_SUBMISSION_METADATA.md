# arXiv submission metadata

## Portal fields

- **Submission type:** New submission
- **Primary category:** q-bio.QM (Quantitative Methods)
- **Cross-list:** cs.AI (Artificial Intelligence)
- **Title:** Plato-Bio: verification-first biological novelty screening with temporal rediscovery and structural benchmarks
- **Authors:** Stefan G. Creadore (Praxa Labs, an independent open-source research initiative, United States)
- **Submitter is an author:** Yes
- **Comments:** 16 pages, 6 figures, 3 tables. Companion code and data: https://github.com/Eldergenix/Plato-Scientific-Research-Autonomous-Agent. This fork-specific validation study cites, but does not duplicate, arXiv:2510.26887.
- **Report number:** Leave blank; no institutional report number has been assigned.
- **Journal reference:** Leave blank; the manuscript has not been published.
- **DOI:** Leave blank; no DOI for another published version exists.
- **License recommendation:** Creative Commons Attribution 4.0 (CC BY 4.0)

## ASCII-safe abstract

Large language model research agents can connect literature retrieval, analysis code, and manuscript preparation, but coherent output does not establish scientific validity. We developed Plato-Bio, a biology-routed extension of the open Plato/Denario architecture that couples explicit workflow states with provenance records, citation checks, claim-to-evidence links, scoped file writes, and publication gates. A source audit identified and repaired three defects that could distort evaluation: loss of task domain in the default factory, omission of declared method signals from scoring, and evidence sidecars that lacked the drafted-claim denominator. On the current clean revision, the full Python suite completed with 931 passes, six skips, and no failures or errors; targeted biology, genomics, evidence/citation, and adversarial-safety suites likewise completed without failure. We evaluated two narrow use cases. In a frozen historical rediscovery task, independent pre-1986 literature bridges ranked the later-studied relation between fish oil and Raynaud phenomenon first; TF-IDF ranked it second and corpus frequency third. This single curated task measures retrospective ranking, not prospective discovery. In a separate comparison of AlphaFold models with experimental structures for 15 human proteins, 11 targets had high-confidence-core C-alpha RMSD below 1 Angstrom (median 0.501 Angstrom). Four targets exceeded 2 Angstrom, and confidence masking reduced the SUMO1 discrepancy from 16.61 to 2.58 Angstrom over 74 residues. The workflow emitted 27 traceable discrepancy regions, all retained as unvalidated hypotheses. Plato-Bio therefore provides reproducible software contracts and auditable screening baselines; broader claims of agent efficacy or biological novelty require preregistered evaluation, independent review, and prospective validation.

The abstract is ASCII-only and contains fewer than arXiv's 1,920-character maximum.

## Upload file

- `arxiv/Plato-Bio-arXiv-source.zip` is the complete main TeX submission. It contains one top-level TeX file, six referenced image assets, and embedded bibliography entries.
- `latex/Plato-Bio-LaTeX-preprint.pdf` is the 16-page local reference rendering compiled from the exact archive. arXiv should generate its own PDF from the uploaded TeX source.

## Human confirmation before final submission

Before clicking **Submit Article**, the corresponding author must confirm that:

- `Stefan G. Creadore` is the intended publication name and the sole author;
- no other contributor meets authorship criteria and all necessary submission consent has been obtained;
- `Praxa Labs, an independent open-source research initiative, United States` is accurate and does not imply that Praxa Labs is an incorporated entity or institutional affiliation;
- the correspondence address `stefan@nex-t1.ai` and ORCID `0000-0003-2268-053X` are correct;
- the funding, competing-interest, ethics, author-contribution, and generative-AI statements are accurate;
- this manuscript is a new fork-specific study rather than a replacement for arXiv:2510.26887;
- the submitter has the right to grant the selected distribution license; and
- the processed arXiv PDF matches the 16-page local reference rendering.
