---
id: research-2026-07-12-plato-v2-implementation-and-evidence
date: 2026-07-12
scope: Plato-Bio biological novelty and benchmark revision
---

# Plato-Bio v2 implementation and evidence synthesis

## Decision

The strongest locally executable revision was not an unconstrained LLM claim-generation run. It was a two-lane benchmark revision:

1. a frozen, leakage-controlled temporal rediscovery component with explicit A–B/B–C evidence paths, known-prior-art controls, abstention, baselines, and task-level metrics; and
2. a predeclared 15-target AlphaFold-to-experiment screen that reports both whole-chain and pLDDT-masked core RMSD before emitting hypothesis-only discrepancy regions.

This directly addresses the source audit's main gap while preserving the boundary between retrospective ranking, structural discrepancy, and biological discovery.

## External benchmark constraints

- ScienceAgentBench uses 102 executable tasks from 44 peer-reviewed papers, expert validation, result/cost metrics, and contamination controls. The best reported agent solved 32.4% without expert knowledge: <https://proceedings.iclr.cc/paper_files/paper/2025/hash/f12b4df26344f3be803c06b555252efe-Abstract-Conference.html>
- BioDSA-1K uses 1,029 hypothesis tasks and separates hypothesis decisions, evidence alignment, reasoning, executability, and non-verifiable cases: <https://arxiv.org/abs/2505.16100>
- BixBench uses more than 50 practical biological-analysis scenarios with nearly 300 open-answer questions and emphasizes long multi-step trajectories: <https://arxiv.org/abs/2503.00096>
- CompBioBench v1 provides 100 computational-biology tasks. Plato-Bio pins revision `c673f0855fce09d320f1677f168f7864eec52c1a` and verifies catalog SHA-256 `ac8a5dcf813e9e89556701648140a84b2757fe449e35650168de54baed75ce1c`: <https://huggingface.co/datasets/Genentech/compbiobench-data-v1>

The local design therefore requires machine-readable outputs, authentic or explicitly synthetic tasks, baselines, failure/abstention states, provenance, frozen inputs, and cautious endpoint language.

## Implemented evidence

### Temporal rediscovery

The scorer hard-fails on unknown dates or records at/after cutoff, deduplicates DOI/PMID sources, quarantines injection signals, and requires different records for the A–B and B–C edges. Direct A–C records are labeled known pre-cutoff; candidates without a bridge are unsupported.

Five synthetic engineering tasks produced:

- frequency: MRR 0.500, Recall@1 0.000;
- TF–IDF, bridge-only, and evidence-aware: MRR 1.000, Recall@1 1.000;
- Recall@10 1.000 and false-novelty rate 0.000 under all conditions.

These results validate engineering behavior only.

The historical pilot freezes six pre-1986 PubMed records and one declared negative control. PMID 58309 links Raynaud phenomenon to blood viscosity; PMID 4015748 links fish-oil omega-3 supplementation to lower blood viscosity. PMID 2536517, published in 1989, is the held-out direct clinical validation. Results:

- frequency target rank 3, reciprocal rank 0.333;
- TF–IDF target rank 2, reciprocal rank 0.500;
- bridge-only and evidence-aware target rank 1, reciprocal rank 1.000;
- direct nifedipine and prostaglandin-E1 controls were labeled known pre-cutoff.

Primary PubMed records:

- <https://pubmed.ncbi.nlm.nih.gov/58309/>
- <https://pubmed.ncbi.nlm.nih.gov/4015748/>
- <https://pubmed.ncbi.nlm.nih.gov/2536517/>

This is one retrospective, manually curated task and cannot estimate prospective discovery performance.

### Structural screen

All 15 predeclared targets completed, with 2,688 matched residues. Median whole-chain RMSD was 0.520 Å and 9/15 targets were below 1 Å. Median high-confidence-core RMSD was 0.501 Å and 11/15 were below 1 Å. Four targets remained above 2 Å after core fitting: KRAS 2.085 Å, SUMO1 2.576 Å, TP53 3.889 Å, and estrogen receptor alpha 4.961 Å.

SUMO1 demonstrates the value of confidence masking: the solution-NMR comparison was 16.610 Å over the whole chain but 2.576 Å across 74 pLDDT>=70 residues. The predeclared pLDDT>=90 and core-aligned error>=2 Å rule emitted 27 regions, 9 multi-residue. Every row is `novelty_status=not_established`.

## Remaining evidence gaps

- The historical benchmark needs many preregistered tasks, broader frozen retrieval, multiple curators, and blinded adjudication.
- CompBioBench datasets and agents were not executed; catalog integration is not a performance result.
- No local or hosted LLM was benchmarked end to end on result and paper generation.
- Structural candidates need alternate-structure, construct, ligand, oligomer, domain, local-score, and ensemble review.
- No prospective computational candidate or wet-lab validation was produced.

## Claim boundary

Supported: deterministic software contracts, one retrospective rediscovery case, a 15-target descriptive structural screen, and auditable candidate triage.

Unsupported: autonomous scientific discovery, general biological-agent efficacy, novel protein conformations, clinical utility, independent peer review, or a 10/10 scientific result.
