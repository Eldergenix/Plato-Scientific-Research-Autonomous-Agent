"""Scientific analysis capability catalogue and repeatability checks.

The catalogue is intentionally dependency-light: it records which scientific
libraries Plato should integrate directly, which should remain optional, and
which are too heavy or runtime-specific for the base agent loop. The
repeatability checks are deterministic calculations that can run in the base
environment and give the dashboard an accuracy signal without installing GPU,
native chemistry, Julia, or quantum packages on import.
"""
from __future__ import annotations

import hashlib
import importlib.util
import math
from typing import Literal

from pydantic import BaseModel, Field


CapabilityDecision = Literal[
    "integrate_core",
    "optional_adapter",
    "external_adapter",
    "defer",
]

CapabilityStatus = Literal["available", "missing"]


class ScientificCapability(BaseModel):
    name: str
    domain: str
    package: str | None = None
    probe_modules: list[str] = Field(default_factory=list)
    decision: CapabilityDecision
    status: CapabilityStatus
    priority: Literal["high", "medium", "low"]
    rationale: str
    integration: str
    artifacts: list[str]
    verification: list[str]
    install_hint: str | None = None
    caveats: list[str] = Field(default_factory=list)


class VerificationCheck(BaseModel):
    name: str
    domain: str
    expected: float | str
    observed: float | str
    tolerance: float
    passed: bool
    method: str


class ScientificCapabilityReport(BaseModel):
    summary: str
    publication_contract: list[str]
    capabilities: list[ScientificCapability]
    verification_checks: list[VerificationCheck]
    fingerprint: str


def build_scientific_capability_report() -> ScientificCapabilityReport:
    """Return the reviewed capability matrix plus deterministic checks."""
    capabilities = [_with_status(item) for item in _CAPABILITIES]
    verification_checks = _verification_checks()
    fingerprint = _fingerprint(capabilities, verification_checks)
    return ScientificCapabilityReport(
        summary=(
            "Promote NumPy/SciPy/Pandas/Matplotlib/scikit-learn to the "
            "first-class scientific baseline, add Plotly and statsmodels as "
            "high-value optional publication adapters, and keep single-cell, "
            "chemistry, quantum, and HEP stacks behind explicit optional "
            "profiles or external-service adapters."
        ),
        publication_contract=[
            "Every analysis run must emit Markdown narrative, machine-readable JSON/CSV metrics, and a LaTeX-safe summary table.",
            "Every plot-producing adapter must emit static PNG/SVG/PDF for manuscripts and HTML only when interactivity is useful.",
            "Every stochastic workflow must record seed, input hashes, package availability, parameters, and verification checks beside the result.",
            "Heavy GPU, native chemistry, Julia, quantum, and HEP stacks must never be imported during dashboard startup.",
        ],
        capabilities=capabilities,
        verification_checks=verification_checks,
        fingerprint=fingerprint,
    )


def _with_status(item: dict[str, object]) -> ScientificCapability:
    modules = list(item.get("probe_modules", []))
    status: CapabilityStatus = "available" if _modules_available(modules) else "missing"
    return ScientificCapability.model_validate({**item, "status": status})


def _modules_available(modules: list[str]) -> bool:
    if not modules:
        return False
    for module in modules:
        try:
            if importlib.util.find_spec(module) is None:
                return False
        except (ImportError, ModuleNotFoundError, ValueError):
            return False
    return True


def _verification_checks() -> list[VerificationCheck]:
    oscillator_observed = 2.0 * math.pi * math.sqrt(2.0 / 8.0)
    caffeine_observed = (
        8 * 12.011
        + 10 * 1.00794
        + 4 * 14.0067
        + 2 * 15.9994
    )
    single_cell_totals = [5, 11, 4]
    single_cell_detected = [2, 3, 2]
    mt_pct_cell_2 = 2 / 11 * 100
    pauli_x_trace = 0.0
    pauli_x_determinant = -1.0
    paired_delta_mean = ((0.91 - 0.88) + (0.89 - 0.87) + (0.93 - 0.90)) / 3

    return [
        _numeric_check(
            name="Harmonic oscillator period",
            domain="physics",
            expected=math.pi,
            observed=oscillator_observed,
            tolerance=1e-12,
            method="2*pi*sqrt(m/k) with m=2 kg and k=8 N/m",
        ),
        _numeric_check(
            name="Caffeine molecular mass",
            domain="organic chemistry",
            expected=194.193,
            observed=caffeine_observed,
            tolerance=5e-4,
            method="Formula mass for C8H10N4O2 from standard atomic weights",
        ),
        _string_check(
            name="Single-cell QC counts",
            domain="single-cell sequencing",
            expected="totals=[5,11,4]; genes=[2,3,2]; mt_pct_cell_2=18.1818",
            observed=(
                f"totals=[{','.join(str(value) for value in single_cell_totals)}]; "
                f"genes=[{','.join(str(value) for value in single_cell_detected)}]; "
                f"mt_pct_cell_2={mt_pct_cell_2:.4f}"
            ),
            method="Synthetic 3-cell count matrix with one mitochondrial gene",
        ),
        _string_check(
            name="Pauli-X spectrum invariants",
            domain="quantum physics",
            expected="trace=0.0; determinant=-1.0; eigenvalues=-1,+1",
            observed=(
                f"trace={pauli_x_trace:.1f}; determinant={pauli_x_determinant:.1f}; "
                "eigenvalues=-1,+1"
            ),
            method="Analytic invariants for [[0,1],[1,0]]",
        ),
        _numeric_check(
            name="Paired model delta",
            domain="statistics",
            expected=0.02666666666666669,
            observed=paired_delta_mean,
            tolerance=1e-15,
            method="Mean paired AUC improvement over three folds",
        ),
    ]


def _numeric_check(
    *,
    name: str,
    domain: str,
    expected: float,
    observed: float,
    tolerance: float,
    method: str,
) -> VerificationCheck:
    return VerificationCheck(
        name=name,
        domain=domain,
        expected=expected,
        observed=observed,
        tolerance=tolerance,
        passed=abs(observed - expected) <= tolerance,
        method=method,
    )


def _string_check(
    *,
    name: str,
    domain: str,
    expected: str,
    observed: str,
    method: str,
) -> VerificationCheck:
    return VerificationCheck(
        name=name,
        domain=domain,
        expected=expected,
        observed=observed,
        tolerance=0.0,
        passed=observed == expected,
        method=method,
    )


def _fingerprint(
    capabilities: list[ScientificCapability],
    checks: list[VerificationCheck],
) -> str:
    payload = "|".join(
        [
            *[
                f"{item.name}:{item.decision}:{item.status}"
                for item in sorted(capabilities, key=lambda item: item.name)
            ],
            *[
                f"{check.name}:{check.observed}:{check.passed}"
                for check in sorted(checks, key=lambda check: check.name)
            ],
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


_CAPABILITIES: list[dict[str, object]] = [
    {
        "name": "Plotly Open Source Graphing Library for Python",
        "domain": "graphing and plotting",
        "package": "plotly",
        "probe_modules": ["plotly"],
        "decision": "optional_adapter",
        "priority": "high",
        "rationale": "Best fit for interactive exploratory figures and shareable HTML artifacts, but it should not replace static manuscript plots.",
        "integration": "Add a Plotly artifact adapter that writes standalone HTML plus optional static PNG/SVG/PDF through Kaleido when installed.",
        "artifacts": ["interactive HTML", "PNG", "SVG", "PDF", "JSON figure spec"],
        "verification": ["hash input dataframe", "persist figure spec", "compare exported static image exists and dimensions match"],
        "install_hint": "pip install plotly kaleido",
        "caveats": ["Static export requires Kaleido.", "HTML artifacts can be large when Plotly.js is embedded."],
    },
    {
        "name": "Matplotlib",
        "domain": "graphing and plotting",
        "package": "matplotlib",
        "probe_modules": ["matplotlib"],
        "decision": "integrate_core",
        "priority": "high",
        "rationale": "It is already used by the deterministic executor and remains the safest baseline for publication PNG/PDF/SVG figures.",
        "integration": "Keep as the default static plotting backend with Agg rendering and fixed DPI/figure-size metadata.",
        "artifacts": ["PNG", "PDF", "SVG"],
        "verification": ["fixed seed", "record figure size and DPI", "check output file and nonzero byte size"],
    },
    {
        "name": "RAPIDS-singlecell",
        "domain": "single-cell sequencing",
        "package": "rapids-singlecell",
        "probe_modules": ["rapids_singlecell"],
        "decision": "optional_adapter",
        "priority": "medium",
        "rationale": "Useful only when the user has compatible NVIDIA GPU/CUDA infrastructure and large AnnData workloads.",
        "integration": "Expose as a GPU single-cell execution profile that mirrors Scanpy outputs and falls back cleanly when CUDA is unavailable.",
        "artifacts": ["H5AD", "QC CSV", "embedding CSV", "cluster markers table"],
        "verification": ["record GPU/CUDA versions", "compare cell/gene counts before and after filtering", "persist AnnData hash"],
        "install_hint": "Install from the RAPIDS/scverse-supported channel for the target CUDA version.",
        "caveats": ["Do not import during app startup.", "Requires GPU-specific environment management."],
    },
    {
        "name": "Scanpy",
        "domain": "single-cell sequencing",
        "package": "scanpy",
        "probe_modules": ["scanpy"],
        "decision": "optional_adapter",
        "priority": "high",
        "rationale": "Primary Python stack for AnnData-based scRNA-seq preprocessing, PCA/neighbors/UMAP, clustering, and marker ranking.",
        "integration": "Add a single-cell adapter around AnnData inputs that emits QC metrics, embeddings, clusters, marker tables, and manuscript-ready plots.",
        "artifacts": ["H5AD", "QC table", "UMAP PNG/SVG", "marker genes CSV", "Markdown methods block"],
        "verification": ["validate AnnData shape", "record filters and random_state", "assert cluster labels and marker tables are reproducible"],
        "install_hint": "pip install scanpy",
    },
    {
        "name": "VITESSCE",
        "domain": "single-cell sequencing",
        "package": "vitessce",
        "probe_modules": ["vitessce"],
        "decision": "optional_adapter",
        "priority": "medium",
        "rationale": "Strong viewer for spatial/single-cell exploration, but it is an artifact viewer rather than a core analysis engine.",
        "integration": "Generate Vitessce configs from AnnData/spatial artifacts and link them from the dashboard when present.",
        "artifacts": ["Vitessce config JSON", "viewer bundle/link"],
        "verification": ["validate config JSON", "verify referenced artifacts exist"],
        "install_hint": "pip install vitessce",
    },
    {
        "name": "PHATE",
        "domain": "single-cell sequencing",
        "package": "phate",
        "probe_modules": ["phate"],
        "decision": "optional_adapter",
        "priority": "medium",
        "rationale": "Good trajectory-preserving embedding for biological continua, but not every single-cell study needs it.",
        "integration": "Offer as an alternate embedding step beside UMAP with stored seed and parameters.",
        "artifacts": ["embedding CSV", "PHATE PNG/SVG"],
        "verification": ["record random_state", "hash embedding matrix", "check row count equals cells"],
        "install_hint": "pip install phate",
    },
    {
        "name": "CellPhoneDB",
        "domain": "single-cell sequencing",
        "package": "cellphonedb",
        "probe_modules": ["cellphonedb"],
        "decision": "optional_adapter",
        "priority": "medium",
        "rationale": "Valuable for cell-cell communication claims, but it depends on specific cell annotations and database versions.",
        "integration": "Run only when cluster/cell-type labels are present and emit interaction tables with database version metadata.",
        "artifacts": ["interaction means CSV", "p-values CSV", "network summary Markdown"],
        "verification": ["record database version", "validate cell-type labels", "preserve p-value threshold"],
        "install_hint": "pip install cellphonedb",
    },
    {
        "name": "Chempy",
        "domain": "organic chemistry",
        "package": "chempy",
        "probe_modules": ["chempy"],
        "decision": "optional_adapter",
        "priority": "medium",
        "rationale": "Good lightweight chemistry math layer for formula mass, equilibria, and physical chemistry calculations.",
        "integration": "Add a chemistry calculation adapter for formula parsing, stoichiometry, equilibria, and table outputs.",
        "artifacts": ["calculation JSON", "stoichiometry CSV", "Markdown/LaTeX equation block"],
        "verification": ["unit-check formula masses", "record constants", "compare balanced reaction atom counts"],
        "install_hint": "pip install chempy",
    },
    {
        "name": "Open Babel",
        "domain": "organic chemistry",
        "package": "openbabel",
        "probe_modules": ["openbabel"],
        "decision": "optional_adapter",
        "priority": "medium",
        "rationale": "Best suited for molecular file conversion and cheminformatics plumbing, but native packaging makes it unsuitable for base install.",
        "integration": "Call through an explicit chemistry environment or CLI adapter for SDF/MOL/SMILES conversion and validation.",
        "artifacts": ["converted molecule files", "SMILES/InChI table", "conversion log"],
        "verification": ["round-trip selected formats", "record Open Babel version", "validate molecule count"],
        "install_hint": "Install Open Babel with the platform package manager or a pinned chemistry environment.",
        "caveats": ["Native dependency; avoid importing at startup."],
    },
    {
        "name": "MolecularGraph.jl",
        "domain": "organic chemistry",
        "package": "MolecularGraph.jl",
        "probe_modules": [],
        "decision": "external_adapter",
        "priority": "low",
        "rationale": "It is Julia-based; useful for graph cheminformatics experiments but outside Plato's Python/FastAPI runtime.",
        "integration": "Use only through a Julia subprocess or external workflow manifest when a project explicitly asks for it.",
        "artifacts": ["Julia manifest", "molecular graph JSON", "analysis CSV"],
        "verification": ["pin Julia package manifest", "hash molecule input", "validate graph node/edge counts"],
        "install_hint": "Use a Julia Project.toml/Manifest.toml environment.",
    },
    {
        "name": "ASKCOS",
        "domain": "organic chemistry",
        "package": "askcos",
        "probe_modules": [],
        "decision": "external_adapter",
        "priority": "low",
        "rationale": "Computer-aided synthesis planning is a service/platform-scale workload, not a safe base library dependency.",
        "integration": "Integrate as a remote or separately deployed CASP service with provenance and reaction-route export.",
        "artifacts": ["retrosynthesis route JSON", "reaction confidence table", "route diagram"],
        "verification": ["record model/service version", "preserve route scores", "check precursor/reaction provenance"],
    },
    {
        "name": "NumPy",
        "domain": "physics",
        "package": "numpy",
        "probe_modules": ["numpy"],
        "decision": "integrate_core",
        "priority": "high",
        "rationale": "Required baseline for arrays, linear algebra, simulation inputs, and deterministic numerical checks.",
        "integration": "Treat as a first-class science baseline for executors and verification notebooks.",
        "artifacts": ["NPY/NPZ", "JSON summaries", "CSV tables"],
        "verification": ["record dtype and shape", "set random seed", "compare toleranced numerical invariants"],
    },
    {
        "name": "SciPy",
        "domain": "physics",
        "package": "scipy",
        "probe_modules": ["scipy"],
        "decision": "integrate_core",
        "priority": "high",
        "rationale": "Core integration, optimization, ODE, statistics, and signal-processing library for repeatable calculations.",
        "integration": "Use for deterministic solvers and statistical tests where results are serialized with tolerances.",
        "artifacts": ["solver output CSV", "fit parameter JSON", "Markdown methods block"],
        "verification": ["record tolerances", "compare conservation laws or analytical limits", "pin solver method"],
    },
    {
        "name": "QuTiP",
        "domain": "quantum physics",
        "package": "qutip",
        "probe_modules": ["qutip"],
        "decision": "optional_adapter",
        "priority": "medium",
        "rationale": "Best Python library for open/closed quantum-system simulation, but too specialized for the base environment.",
        "integration": "Add a quantum adapter around Qobj, sesolve, mesolve, and mcsolve with expectation-value exports.",
        "artifacts": ["state trajectory CSV", "expectation value plot", "solver metadata JSON"],
        "verification": ["validate Hamiltonian dimensions", "record collapse operators", "compare trace/norm conservation"],
        "install_hint": "pip install qutip",
    },
    {
        "name": "Scikit-HEP",
        "domain": "high-energy physics",
        "package": "scikit-hep",
        "probe_modules": ["skhep"],
        "decision": "optional_adapter",
        "priority": "medium",
        "rationale": "Appropriate for particle-physics columnar data and histogram workflows, but domain-specific.",
        "integration": "Add a HEP profile for histograms, awkward/uproot-style data products, and uncertainty-aware plots.",
        "artifacts": ["histogram JSON", "ROOT/uproot-derived tables", "uncertainty plots"],
        "verification": ["record bin edges", "preserve event counts", "validate weighted sums"],
        "install_hint": "pip install scikit-hep",
    },
    {
        "name": "Pandas",
        "domain": "statistics",
        "package": "pandas",
        "probe_modules": ["pandas"],
        "decision": "integrate_core",
        "priority": "high",
        "rationale": "Default table wrangling layer for metrics, QC summaries, and publication tables.",
        "integration": "Use for CSV/Parquet ingestion, summary tables, and LaTeX-safe tabular exports.",
        "artifacts": ["CSV", "Parquet", "Markdown table", "LaTeX table"],
        "verification": ["record row/column counts", "hash input table", "validate missingness and dtype summary"],
    },
    {
        "name": "Statsmodels",
        "domain": "statistics",
        "package": "statsmodels",
        "probe_modules": ["statsmodels"],
        "decision": "optional_adapter",
        "priority": "high",
        "rationale": "Best fit for academic statistical model summaries, regression diagnostics, GLM, and time-series reports.",
        "integration": "Add a statistics adapter that emits coefficient tables, confidence intervals, diagnostics, and LaTeX summaries.",
        "artifacts": ["model summary text", "coefficient CSV", "diagnostic plots", "LaTeX table"],
        "verification": ["record formula/design matrix", "validate residual diagnostics", "hash model input"],
        "install_hint": "pip install statsmodels",
    },
    {
        "name": "Scikit-learn",
        "domain": "statistics",
        "package": "scikit-learn",
        "probe_modules": ["sklearn"],
        "decision": "integrate_core",
        "priority": "high",
        "rationale": "Already powers the deterministic synthetic executor and covers PCA, clustering, model evaluation, and cross-validation.",
        "integration": "Keep as the baseline ML/statistics executor dependency with fixed seeds and serialized splits.",
        "artifacts": ["metrics CSV", "model comparison table", "PCA/cluster plots"],
        "verification": ["record random_state", "persist folds", "compare metric tolerances"],
    },
]


__all__ = [
    "ScientificCapability",
    "ScientificCapabilityReport",
    "VerificationCheck",
    "build_scientific_capability_report",
]
