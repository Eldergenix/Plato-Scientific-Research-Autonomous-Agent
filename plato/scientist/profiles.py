"""Domain profiles for the live scientist.

A campaign's domain decides which literature sources it searches and which extra
packages its experiments may import. The biology and astro profiles reuse the
library's :mod:`plato.domain` registry (single source of truth for their source lists);
``general`` covers statistics, machine learning and everything else.

The domain comes from the campaign's program (the agent's ``domain`` argument) and,
when that is unspecific, from the research plan's own domain label, so "general"
campaigns about gene expression still get PubMed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from plato.domain import get_domain

# Packages every experiment may import (installed in docker/requirements-scientist.txt).
BASE_PACKAGES: tuple[str, ...] = (
    "numpy",
    "scipy",
    "pandas",
    "scikit-learn",
    "matplotlib",
    "statsmodels",
)


# Library source -> the variant that returns only citable literature.
LITERATURE_ONLY = {"datacite": "datacite_literature"}


@dataclass(frozen=True)
class ScientistProfile:
    name: str
    retrieval_sources: tuple[str, ...]
    extra_packages: tuple[str, ...] = ()
    guidance: str = ""
    # Extra rules for a live sandbox session (the plato-lab E2B template), where this
    # domain's command-line tools and the public data APIs are reachable. The offline
    # local and Modal executors never see it: their packages are fixed by ``packages``.
    workspace_guidance: str = ""

    @property
    def packages(self) -> tuple[str, ...]:
        return BASE_PACKAGES + self.extra_packages


GENERAL = ScientistProfile(
    name="general",
    # OpenCitations is a DOI resolver, not a full-text search; it is used by the
    # citation checks instead (see plato.scientist.citations).
    retrieval_sources=(
        "arxiv",
        "openalex",
        "semantic_scholar",
        "crossref",
        "doaj",
        "europe_pmc",
    ),
)


def _from_library(
    name: str,
    extra: tuple[str, ...],
    guidance: str,
    workspace_guidance: str = "",
) -> ScientistProfile:
    lib = get_domain(name)
    return ScientistProfile(
        name=name,
        # Campaigns cite papers: DataCite is searched for literature records only.
        retrieval_sources=tuple(
            LITERATURE_ONLY.get(s, s) for s in lib.retrieval_sources
        ),
        extra_packages=extra,
        guidance=guidance,
        workspace_guidance=workspace_guidance,
    )


# What the molecular tools in the plato-lab template may and may not be used to claim.
# Each paragraph names the tool, the statistic it produces and the kind of claim that
# statistic can carry: a computed measurement, a transferred inference or a model
# estimate. The point is that an annotation or a score is never written up as a
# measurement, and that a condition-dependent claim is tested by varying the condition.
MOLECULAR_GUIDANCE = (
    "Molecular work in this sandbox: state what kind of evidence each claim rests on, and "
    "never let a database annotation stand in for a result you computed. "
    "Compounds: parse and standardise with RDKit (InChIKey for identity), and treat "
    "descriptors, scaffolds and matched pairs as computed facts; predicted properties are "
    "model estimates, so name the model. Generate conformers with RDKit ETKDG and refine "
    "them with xtb (GFN2) when geometry matters. "
    "Proteins: phmmer, jackhmmer and hmmbuild/hmmsearch give profile-HMM homology, mmseqs "
    "fast sequence search and foldseek structural search; mkdssp gives secondary structure "
    "from coordinates. Function carried over from a homologue is an inference, not an "
    "observation: report identity, coverage and E-value (or TM-score) with it, and keep "
    "predicted structures (AlphaFold DB) apart from experimental ones, with pLDDT. "
    "Pathways: membership in Reactome, KEGG or STRING is a reference annotation and proves "
    "nothing on its own. A pathway claim must come from a statistic computed on your own "
    "data: gseapy over-representation or permutation GSEA against a background set that "
    "matches what the assay could have detected, FDR-corrected, reporting the background, "
    "the null and the set size. Topology claims (hubs, shortest paths, bottlenecks) need a "
    "degree-preserving randomisation as the null, not the observed graph alone. "
    "Interactions: AutoDock Vina scores rank poses within one receptor and box; they are "
    "not binding affinities, and the receptor preparation, box and seed belong in the "
    "report with the redocking control. Physics-based estimates are model energies: give "
    "xtb interaction energies relative to the separated monomers at the same level, Psi4 "
    "SAPT components (electrostatics, exchange, induction, dispersion) when the question is "
    "what drives an interaction, and OpenMM or LAMMPS for ensemble behaviour, with the "
    "force field and the sampling time stated. When the claim is about conditions (solvent, "
    "pH, ionic strength, temperature, mutation), run the sweep and report the trend with "
    "error bars across replicate seeds, never a single point."
)


BIOLOGY = _from_library(
    "biology",
    ("biopython",),
    "Biology campaigns: use Bio.Seq/Bio.SeqIO/Bio.Align for sequence work (no Entrez: the "
    "sandbox is offline), statsmodels for GLMs and multiple-testing correction "
    "(statsmodels.stats.multitest.multipletests), and report effect sizes with intervals.",
    MOLECULAR_GUIDANCE,
)
ASTRO = _from_library(
    "astro",
    ("astropy",),
    "Astronomy campaigns: use astropy.units and astropy.constants for physical quantities, "
    "astropy.cosmology (e.g. Planck18) for distances and ages, and astropy.stats for "
    "sigma clipping. No remote catalogue queries: the sandbox is offline.",
)

PROFILES: dict[str, ScientistProfile] = {p.name: p for p in (GENERAL, BIOLOGY, ASTRO)}

# Word-start anchored so "general", "standard" or "journal" never match.
_BIO = re.compile(
    r"\b(bio\w*|genes?\b|genetic\w*|genom\w*|protein\w*|cells?\b|clinic\w*|"
    r"chem\w*|molecul\w*|ligands?\b|docking|drugs?\b|enzym\w*|metabol\w*|"
    r"pathways?\b|receptors?\b|inhibitors?\b|antibod\w*|peptides?\b|"
    r"medic\w*|epidem\w*|ecolog\w*|neuro\w*|pharma\w*|immun\w*|microb\w*|vir(us|al)\w*|"
    r"diseases?\b|health\w*|\w*omics\b|rna\b|dna\b|sequencing|physiolog\w*|patholog\w*|"
    r"cancer\w*|tumou?r\w*|transcript\w*)"
)
_ASTRO = re.compile(
    r"\b(astro\w*|cosmolog\w*|galax\w*|stellar|stars?\b|planet\w*|exoplanet\w*|solar\b|"
    r"black.?holes?|gravitational|telescop\w*|supernova\w*|quasars?\b|redshift\w*|orbit\w*)"
)


def classify(domain: str | None) -> str | None:
    """Map a free-text domain label to a profile name, or None if it is unspecific."""
    # snake_case and kebab-case labels ("computational_biology") become words.
    text = re.sub(r"[_\-/]+", " ", (domain or "").strip().lower())
    if not text or text == "general":
        return None
    if text in PROFILES:
        return text
    if _ASTRO.search(text):
        return "astro"
    if _BIO.search(text):
        return "biology"
    return "general"


def resolve_profile(*domains: str | None) -> ScientistProfile:
    """First specific match among ``domains`` (most authoritative first), else general.

    "general" from an earlier label never shadows a specific later one: the agent often
    leaves the domain at its default while the plan labels it computational_biology."""
    fallback = None
    for d in domains:
        name = classify(d)
        if name in ("biology", "astro"):
            return PROFILES[name]
        fallback = fallback or name
    return PROFILES[fallback or "general"]


def get_profile(name: str | None) -> ScientistProfile:
    return PROFILES.get(name or "general", GENERAL)
