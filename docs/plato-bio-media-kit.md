# Plato-Bio media kit

This page provides verified language and links for journalists, podcast hosts,
conference organizers, collaborators, and other people discussing the
Plato-Bio preprint. It is intentionally conservative: the study reports
software validation and two limited benchmarks, not autonomous scientific
discovery or established biological novelty.

## Paper

**Title:** Plato-Bio: verification-first biological novelty screening with
temporal rediscovery and structural benchmarks

**Author:** Stefan G. Creadore

**Affiliation:** Praxa Labs, an independent open-source research initiative,
United States

**Status:** arXiv preprint; not peer reviewed

**Categories:** Artificial Intelligence (`cs.AI`); Quantitative Methods
(`q-bio.QM`)

**Public links:**

- arXiv: https://arxiv.org/abs/2607.23975
- PDF: https://arxiv.org/pdf/2607.23975
- Code and data:
  https://github.com/Eldergenix/Plato-Scientific-Research-Autonomous-Agent
- ORCID: https://orcid.org/0000-0003-2268-053X

## Plain-language summary

AI research agents can retrieve literature, write analysis code, and draft
scientific prose, but a fluent report is not evidence that the underlying
science is correct. Plato-Bio explores a narrower objective: making an
AI-assisted computational-biology workflow inspectable enough for a human
researcher to check its sources, calculations, intermediate claims, and
limitations.

The study first audited the software and repaired three defects that could
distort evaluation. It then examined two limited use cases. In one manually
curated historical task, evidence-bridge ranking placed a relation studied
later—between fish oil and Raynaud phenomenon—first using only pre-1986
literature. In a separate screen, the workflow compared existing AlphaFold
models with experimental structures for 15 human proteins. Eleven targets had
high-confidence-core C-alpha RMSD below 1 Angstrom, while 27 discrepancy
regions were retained as unvalidated hypotheses.

The results support auditable software contracts and reproducible screening
baselines. Larger preregistered evaluations, independent review, prospective
testing, and experimental validation are still required.

## Three central takeaways

1. **Traceability before novelty.** Scientific claims should remain linked to
   sources, calculations, software versions, and explicit uncertainty.
2. **A promising screen is not a discovery.** The temporal result comes from
   one retrospective task, and every structural discrepancy remains an
   unvalidated hypothesis.
3. **Human scientific judgment remains essential.** Passing software tests or
   producing coherent prose does not establish biological truth.

## Verified quantitative results

- Full recorded Python suite: 931 passes, 6 skips, 0 failures, and 0 errors.
- Historical pilot: bridge-only and evidence-aware ranking placed the held-out
  relation first; TF-IDF placed it second and corpus frequency third.
- Structural screen: 15 human proteins and 2,688 matched residues.
- Median whole-chain C-alpha RMSD: 0.520 Angstrom.
- Median high-confidence-core C-alpha RMSD: 0.501 Angstrom.
- Eleven of 15 targets had high-confidence-core RMSD below 1 Angstrom.
- Twenty-seven traceable discrepancy regions were retained as unvalidated
  hypotheses.

## Claims to avoid

Do not describe the study as having:

- discovered a new cure, treatment, protein, or biological mechanism;
- demonstrated autonomous scientific discovery;
- established that Plato-Bio is generally more effective than other research
  agents;
- predicted the protein structures used in the benchmark;
- validated the manuscript through arXiv moderation; or
- completed independent peer review or experimental validation.

Plato-Bio compared existing AlphaFold predictions with experimental PDB
structures; it did not generate the AlphaFold predictions. The historical
result is a single retrospective ranking task and should not be generalized to
prospective discovery.

## Suggested citation

Creadore, S. G. (2026). *Plato-Bio: verification-first biological novelty
screening with temporal rediscovery and structural benchmarks*. arXiv.
https://arxiv.org/abs/2607.23975

## Short author biography

Stefan G. Creadore is an independent researcher working through Praxa Labs, an
independent open-source research initiative in the United States. His
Plato-Bio work focuses on provenance, reproducibility, claim-to-evidence
linking, and conservative evaluation for AI-assisted biological research.

## Review policy for third-party summaries

Third-party explanations, interviews, podcasts, and conference descriptions
should not be called “author-reviewed” or “author-approved” until the author
has reviewed the final public version. AI-generated summaries should retain the
preprint and peer-review disclaimer and should be corrected when they blur the
boundary between screening results and established scientific findings.
