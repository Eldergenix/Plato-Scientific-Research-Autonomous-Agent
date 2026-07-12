#!/usr/bin/env python3
"""Reproduce a declared Plato-Bio AlphaFold-to-experiment structure panel.

The default is the original three-globin case study. ``--panel-file`` accepts a
larger predeclared JSON panel. The script aligns identical, sequence-matched
C-alpha atoms, reports whole-chain and high-confidence-core superpositions,
and writes a hashed machine-readable bundle with hypothesis-only discrepancy
regions.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import spearmanr


PANEL = (
    {
        "target": "hemoglobin_alpha",
        "uniprot": "P69905",
        "pdb_id": "1A3N",
        "chain": "A",
    },
    {
        "target": "hemoglobin_beta",
        "uniprot": "P68871",
        "pdb_id": "1A3N",
        "chain": "B",
    },
    {
        "target": "myoglobin",
        "uniprot": "P02144",
        "pdb_id": "3RGK",
        "chain": "A",
    },
)

BOOTSTRAP_REPLICATES = 2_000
BOOTSTRAP_BLOCK_SIZE = 10
BOOTSTRAP_SEED = 20260711
DEFAULT_DISCREPANCY_ERROR_ANGSTROM = 2.0
DEFAULT_DISCREPANCY_PLDDT = 90.0
CORE_PLDDT_THRESHOLD = 70.0

AA3_TO_1 = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
    "GLN": "Q",
    "GLU": "E",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LEU": "L",
    "LYS": "K",
    "MET": "M",
    "PHE": "F",
    "PRO": "P",
    "SER": "S",
    "THR": "T",
    "TRP": "W",
    "TYR": "Y",
    "VAL": "V",
    "MSE": "M",
}


@dataclass(frozen=True)
class Residue:
    name: str
    number: int
    insertion_code: str
    coord: tuple[float, float, float]
    confidence: float

    @property
    def aa(self) -> str:
        return AA3_TO_1.get(self.name, "X")


@dataclass(frozen=True)
class TargetResult:
    target: str
    uniprot: str
    pdb_id: str
    chain: str
    experimental_method: str
    experimental_resolution_angstrom: float | None
    predicted_residues: int
    experimental_residues: int
    matched_residues: int
    predicted_sequence_coverage: float
    experimental_sequence_coverage: float
    sequence_identity: float
    ca_rmsd_angstrom: float
    ca_rmsd_ci95_low: float
    ca_rmsd_ci95_high: float
    high_confidence_residues: int
    high_confidence_ca_rmsd_angstrom: float
    high_confidence_ca_rmsd_ci95_low: float
    high_confidence_ca_rmsd_ci95_high: float
    median_ca_error_angstrom: float
    fraction_within_2a: float
    fraction_within_5a: float
    mean_plddt: float
    spearman_plddt_vs_negative_error: float
    spearman_pvalue: float


def load_panel(path: Path | None) -> list[dict[str, str]]:
    """Load and validate a predeclared target panel."""

    payload = list(PANEL) if path is None else json.loads(path.read_text())
    if not isinstance(payload, list) or not payload:
        raise ValueError("Panel must be a non-empty JSON list")
    required = {"target", "uniprot", "pdb_id", "chain"}
    panel: list[dict[str, str]] = []
    seen_targets: set[str] = set()
    for index, raw in enumerate(payload):
        if not isinstance(raw, dict):
            raise ValueError(f"Panel row {index} is not an object")
        missing = required - raw.keys()
        if missing:
            raise ValueError(f"Panel row {index} is missing {sorted(missing)}")
        normalized = {key: str(value).strip() for key, value in raw.items()}
        target = normalized["target"]
        if not target:
            raise ValueError(f"Panel row {index} has an empty target")
        if target in seen_targets:
            raise ValueError(f"Duplicate panel target: {target}")
        seen_targets.add(target)
        panel.append(normalized)
    return panel


def moving_block_bootstrap_rmsd_ci(
    distances: np.ndarray,
    *,
    replicates: int = BOOTSTRAP_REPLICATES,
    block_size: int = BOOTSTRAP_BLOCK_SIZE,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """Descriptive 95% RMSD interval using a moving-block bootstrap.

    Contiguous residue errors are locally correlated, so blocks are sampled
    instead of treating every residue as independent. The interval remains a
    descriptive uncertainty summary rather than a population-level claim.
    """

    values = np.asarray(distances, dtype=float)
    if values.ndim != 1 or values.size < 3:
        raise ValueError("At least three one-dimensional distances are required")
    if replicates < 100:
        raise ValueError("At least 100 bootstrap replicates are required")
    block_size = max(1, min(int(block_size), values.size))
    blocks_needed = math.ceil(values.size / block_size)
    rng = np.random.default_rng(seed)
    estimates = np.empty(replicates, dtype=float)
    max_start = values.size - block_size
    for replicate in range(replicates):
        starts = rng.integers(0, max_start + 1, size=blocks_needed)
        sample = np.concatenate(
            [values[start : start + block_size] for start in starts]
        )[: values.size]
        estimates[replicate] = float(np.sqrt(np.mean(np.square(sample))))
    low, high = np.quantile(estimates, [0.025, 0.975])
    return float(low), float(high)


def detect_discrepancy_regions(
    residue_rows: list[dict],
    *,
    error_threshold: float = DEFAULT_DISCREPANCY_ERROR_ANGSTROM,
    plddt_threshold: float = DEFAULT_DISCREPANCY_PLDDT,
) -> list[dict]:
    """Group high-confidence coordinate discrepancies into candidate regions.

    These are hypothesis-generating candidates, not established novelties.
    Literature/context review and independent validation remain mandatory.
    """

    qualifying = sorted(
        (
            row
            for row in residue_rows
            if float(row["ca_error_angstrom"]) >= error_threshold
            and float(row["plddt"]) >= plddt_threshold
        ),
        key=lambda row: (row["target"], int(row["alphafold_residue_number"])),
    )
    groups: list[list[dict]] = []
    for row in qualifying:
        if (
            groups
            and groups[-1][-1]["target"] == row["target"]
            and int(row["alphafold_residue_number"])
            == int(groups[-1][-1]["alphafold_residue_number"]) + 1
        ):
            groups[-1].append(row)
        else:
            groups.append([row])

    candidates: list[dict] = []
    for index, group in enumerate(groups, start=1):
        errors = np.array([float(row["ca_error_angstrom"]) for row in group])
        confidence = np.array([float(row["plddt"]) for row in group])
        target = str(group[0]["target"])
        start = int(group[0]["alphafold_residue_number"])
        end = int(group[-1]["alphafold_residue_number"])
        candidates.append(
            {
                "candidate_id": f"{target}:{start}-{end}",
                "target": target,
                "uniprot": group[0]["uniprot"],
                "pdb_id": group[0]["pdb_id"],
                "experimental_chain": group[0]["experimental_chain"],
                "alphafold_residue_start": start,
                "alphafold_residue_end": end,
                "residue_count": len(group),
                "mean_plddt": round(float(np.mean(confidence)), 3),
                "median_ca_error_angstrom": round(float(np.median(errors)), 6),
                "max_ca_error_angstrom": round(float(np.max(errors)), 6),
                "candidate_score": round(
                    float(
                        np.max(errors)
                        * np.mean(confidence)
                        / 100
                        * math.log2(len(group) + 1)
                    ),
                    6,
                ),
                "candidate_status": (
                    "regional_hypothesis_candidate"
                    if len(group) >= 2
                    else "isolated_hypothesis_candidate"
                ),
                "novelty_status": "not_established",
                "evidence_tier": "computational_structural_discrepancy",
                "required_follow_up": (
                    "Review construct mutations, ligands, oligomeric state, alternate PDB "
                    "entries, and experimental conditions; then validate independently."
                ),
            }
        )
    return sorted(
        candidates, key=lambda row: float(row["candidate_score"]), reverse=True
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size:
        return
    request = urllib.request.Request(url, headers={"User-Agent": "Plato-Bio/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        destination.write_bytes(response.read())


def alphafold_model_url(accession: str) -> tuple[str, dict]:
    api_url = f"https://alphafold.ebi.ac.uk/api/prediction/{accession}"
    request = urllib.request.Request(api_url, headers={"User-Agent": "Plato-Bio/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload:
        raise RuntimeError(f"AlphaFold DB returned no model for {accession}")
    record = payload[0]
    pdb_url = record.get("pdbUrl")
    if not pdb_url:
        version = record["latestVersion"]
        pdb_url = (
            f"https://alphafold.ebi.ac.uk/files/AF-{accession}-F1-model_v{version}.pdb"
        )
    return str(pdb_url), record


def parse_ca_atoms(path: Path, chain: str) -> list[Residue]:
    residues: list[Residue] = []
    seen: set[tuple[int, str]] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("ATOM") or line[12:16].strip() != "CA":
            continue
        if line[21:22].strip() != chain:
            continue
        alternate = line[16:17]
        if alternate not in {" ", "A"}:
            continue
        residue_number = int(line[22:26])
        insertion_code = line[26:27].strip()
        key = (residue_number, insertion_code)
        if key in seen:
            continue
        seen.add(key)
        residues.append(
            Residue(
                name=line[17:20].strip(),
                number=residue_number,
                insertion_code=insertion_code,
                coord=(float(line[30:38]), float(line[38:46]), float(line[46:54])),
                confidence=float(line[60:66]),
            )
        )
    if not residues:
        raise RuntimeError(f"No C-alpha atoms found in {path} chain {chain}")
    return residues


def parse_experimental_metadata(path: Path) -> tuple[str, float | None]:
    """Read the experimental method and optional resolution from a PDB header."""

    method = "unknown"
    resolution: float | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("EXPDTA"):
            method = line[10:].strip().lower()
        elif line.startswith("REMARK   2 RESOLUTION."):
            resolution_text = line.split("RESOLUTION.", maxsplit=1)[1]
            for field in resolution_text.split():
                try:
                    resolution = float(field)
                except ValueError:
                    continue
                else:
                    break
        elif line.startswith("ATOM"):
            break
    return method, resolution


def global_alignment(seq_a: str, seq_b: str) -> list[tuple[int | None, int | None]]:
    """Needleman-Wunsch alignment returning index pairs."""

    match, mismatch, gap = 2, -1, -2
    rows, cols = len(seq_a) + 1, len(seq_b) + 1
    score = np.zeros((rows, cols), dtype=np.int32)
    trace = np.zeros((rows, cols), dtype=np.int8)
    score[:, 0] = np.arange(rows) * gap
    score[0, :] = np.arange(cols) * gap
    trace[1:, 0] = 1
    trace[0, 1:] = 2

    for i in range(1, rows):
        for j in range(1, cols):
            diagonal = score[i - 1, j - 1] + (
                match if seq_a[i - 1] == seq_b[j - 1] else mismatch
            )
            up = score[i - 1, j] + gap
            left = score[i, j - 1] + gap
            best = max(diagonal, up, left)
            score[i, j] = best
            trace[i, j] = 0 if best == diagonal else (1 if best == up else 2)

    pairs: list[tuple[int | None, int | None]] = []
    i, j = len(seq_a), len(seq_b)
    while i or j:
        direction = trace[i, j]
        if i and j and direction == 0:
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif i and (j == 0 or direction == 1):
            pairs.append((i - 1, None))
            i -= 1
        else:
            pairs.append((None, j - 1))
            j -= 1
    pairs.reverse()
    return pairs


def kabsch_align(moving: np.ndarray, fixed: np.ndarray) -> np.ndarray:
    return kabsch_apply(moving, fixed, moving)


def kabsch_apply(
    moving_fit: np.ndarray,
    fixed_fit: np.ndarray,
    coordinates: np.ndarray,
) -> np.ndarray:
    """Fit one coordinate subset and apply its rigid transform to another."""

    moving_center = moving_fit.mean(axis=0)
    fixed_center = fixed_fit.mean(axis=0)
    centered_moving = moving_fit - moving_center
    centered_fixed = fixed_fit - fixed_center
    covariance = centered_moving.T @ centered_fixed
    u, _, vt = np.linalg.svd(covariance)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1
        rotation = u @ vt
    return (coordinates - moving_center) @ rotation + fixed_center


def analyze_target(
    spec: dict, raw_dir: Path, residue_rows: list[dict]
) -> tuple[TargetResult, list[dict]]:
    accession = spec["uniprot"]
    pdb_id = spec["pdb_id"]
    experimental_path = raw_dir / f"{pdb_id}.pdb"
    download(f"https://files.rcsb.org/download/{pdb_id}.pdb", experimental_path)

    model_url, model_record = alphafold_model_url(accession)
    model_path = raw_dir / f"AF-{accession}-F1.pdb"
    download(model_url, model_path)

    experimental = parse_ca_atoms(experimental_path, spec["chain"])
    experimental_method, experimental_resolution = parse_experimental_metadata(
        experimental_path
    )
    predicted = parse_ca_atoms(model_path, "A")
    aligned_pairs = global_alignment(
        "".join(residue.aa for residue in predicted),
        "".join(residue.aa for residue in experimental),
    )
    comparable = [
        (predicted[i], experimental[j])
        for i, j in aligned_pairs
        if i is not None
        and j is not None
        and predicted[i].aa == experimental[j].aa
        and predicted[i].aa != "X"
    ]
    if len(comparable) < 3:
        raise RuntimeError(f"Insufficient matched residues for {spec['target']}")

    moving = np.array([pred.coord for pred, _ in comparable], dtype=float)
    fixed = np.array([exp.coord for _, exp in comparable], dtype=float)
    plddt = np.array([pred.confidence for pred, _ in comparable], dtype=float)
    aligned = kabsch_align(moving, fixed)
    whole_chain_distances = np.linalg.norm(aligned - fixed, axis=1)
    core_mask = plddt >= CORE_PLDDT_THRESHOLD
    if int(np.sum(core_mask)) < 3:
        raise RuntimeError(
            f"Insufficient pLDDT >= {CORE_PLDDT_THRESHOLD:g} residues for "
            f"{spec['target']}"
        )
    core_aligned = kabsch_apply(moving[core_mask], fixed[core_mask], moving)
    core_aligned_distances = np.linalg.norm(core_aligned - fixed, axis=1)
    core_distances = core_aligned_distances[core_mask]
    correlation = spearmanr(plddt, -core_aligned_distances)
    target_seed = BOOTSTRAP_SEED + int(
        hashlib.sha256(spec["target"].encode()).hexdigest()[:8], 16
    )
    rmsd_ci_low, rmsd_ci_high = moving_block_bootstrap_rmsd_ci(
        whole_chain_distances,
        seed=target_seed,
    )
    core_rmsd_ci_low, core_rmsd_ci_high = moving_block_bootstrap_rmsd_ci(
        core_distances,
        seed=target_seed + 1,
    )

    identities = sum(
        1
        for i, j in aligned_pairs
        if i is not None and j is not None and predicted[i].aa == experimental[j].aa
    )
    paired_positions = sum(
        1 for i, j in aligned_pairs if i is not None and j is not None
    )
    identity = identities / paired_positions if paired_positions else math.nan

    local_rows = []
    for index, ((pred, exp), distance) in enumerate(
        zip(comparable, core_aligned_distances, strict=True), start=1
    ):
        row = {
            "target": spec["target"],
            "uniprot": accession,
            "pdb_id": pdb_id,
            "experimental_chain": spec["chain"],
            "aligned_index": index,
            "residue": pred.aa,
            "alphafold_residue_number": pred.number,
            "experimental_residue_number": exp.number,
            "plddt": round(pred.confidence, 3),
            "ca_error_angstrom": round(float(distance), 6),
            "alignment_basis": f"pLDDT>={CORE_PLDDT_THRESHOLD:g} core",
        }
        residue_rows.append(row)
        local_rows.append(row)

    result = TargetResult(
        target=spec["target"],
        uniprot=accession,
        pdb_id=pdb_id,
        chain=spec["chain"],
        experimental_method=experimental_method,
        experimental_resolution_angstrom=experimental_resolution,
        predicted_residues=len(predicted),
        experimental_residues=len(experimental),
        matched_residues=len(comparable),
        predicted_sequence_coverage=len(comparable) / len(predicted),
        experimental_sequence_coverage=len(comparable) / len(experimental),
        sequence_identity=float(identity),
        ca_rmsd_angstrom=float(np.sqrt(np.mean(np.square(whole_chain_distances)))),
        ca_rmsd_ci95_low=rmsd_ci_low,
        ca_rmsd_ci95_high=rmsd_ci_high,
        high_confidence_residues=int(np.sum(core_mask)),
        high_confidence_ca_rmsd_angstrom=float(
            np.sqrt(np.mean(np.square(core_distances)))
        ),
        high_confidence_ca_rmsd_ci95_low=core_rmsd_ci_low,
        high_confidence_ca_rmsd_ci95_high=core_rmsd_ci_high,
        median_ca_error_angstrom=float(np.median(core_aligned_distances)),
        fraction_within_2a=float(np.mean(core_aligned_distances <= 2.0)),
        fraction_within_5a=float(np.mean(core_aligned_distances <= 5.0)),
        mean_plddt=float(np.mean(plddt)),
        spearman_plddt_vs_negative_error=float(correlation.statistic),
        spearman_pvalue=float(correlation.pvalue),
    )

    metadata = {
        "target": spec["target"],
        "alphafold_model_url": model_url,
        "alphafold_version": model_record.get("latestVersion"),
        "alphafold_model_created_date": model_record.get("modelCreatedDate"),
        "alphafold_global_metric": model_record.get("globalMetricValue"),
        "alphafold_sha256": sha256(model_path),
        "experimental_pdb_url": f"https://files.rcsb.org/download/{pdb_id}.pdb",
        "experimental_pdb_sha256": sha256(experimental_path),
        "experimental_method": experimental_method,
        "experimental_resolution_angstrom": experimental_resolution,
    }
    return result, [metadata]


def save_figures(
    results: list[TargetResult],
    residue_rows: list[dict],
    figures_dir: Path,
    *,
    benchmark_name: str = "globin",
    error_threshold: float = DEFAULT_DISCREPANCY_ERROR_ANGSTROM,
    plddt_threshold: float = DEFAULT_DISCREPANCY_PLDDT,
) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)
    use_core_metric = len(results) > 4
    ordered = sorted(
        results,
        key=lambda result: (
            result.high_confidence_ca_rmsd_angstrom
            if use_core_metric
            else result.ca_rmsd_angstrom
        ),
    )
    labels = [result.target.replace("_", " ") for result in ordered]
    rmsd = [
        (
            result.high_confidence_ca_rmsd_angstrom
            if use_core_metric
            else result.ca_rmsd_angstrom
        )
        for result in ordered
    ]
    low_error = [
        (
            result.high_confidence_ca_rmsd_angstrom
            - result.high_confidence_ca_rmsd_ci95_low
            if use_core_metric
            else result.ca_rmsd_angstrom - result.ca_rmsd_ci95_low
        )
        for result in ordered
    ]
    high_error = [
        (
            result.high_confidence_ca_rmsd_ci95_high
            - result.high_confidence_ca_rmsd_angstrom
            if use_core_metric
            else result.ca_rmsd_ci95_high - result.ca_rmsd_angstrom
        )
        for result in ordered
    ]
    if len(results) <= 4:
        fig, ax = plt.subplots(figsize=(7.2, 4.2))
        bars = ax.bar(
            labels,
            rmsd,
            color="#2563A6",
            edgecolor="#16324F",
            linewidth=0.8,
            yerr=[low_error, high_error],
            capsize=3,
        )
        ax.set_ylabel("Cα RMSD after alignment (Å)")
        ax.set_ylim(0, max(result.ca_rmsd_ci95_high for result in ordered) * 1.24)
        for bar, value in zip(bars, rmsd, strict=True):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + 0.03,
                f"{value:.2f}",
                ha="center",
                va="bottom",
                fontsize=9,
            )
    else:
        fig, ax = plt.subplots(figsize=(8.0, max(5.0, len(results) * 0.36)))
        positions = np.arange(len(ordered))
        ax.barh(
            positions,
            rmsd,
            color="#2563A6",
            edgecolor="#16324F",
            linewidth=0.6,
            xerr=[low_error, high_error],
            capsize=2,
        )
        ax.set_yticks(positions, labels)
        ax.set_xlabel("High-confidence-core Cα RMSD (Å)")
    display_name = benchmark_name.replace("_", " ")
    ax.set_title(f"AlphaFold-to-experiment agreement: {display_name}")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x" if len(results) > 4 else "y", color="#D9DEE5", linewidth=0.7)
    ax.set_axisbelow(True)
    fig.tight_layout()
    rmsd_name = (
        "figure_2_globin_rmsd.png"
        if benchmark_name == "globin"
        else f"{benchmark_name}_rmsd.png"
    )
    fig.savefig(figures_dir / rmsd_name, dpi=300)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    ordinary = [
        row
        for row in residue_rows
        if float(row["plddt"]) < plddt_threshold
        or float(row["ca_error_angstrom"]) < error_threshold
    ]
    discrepancies = [
        row
        for row in residue_rows
        if float(row["plddt"]) >= plddt_threshold
        and float(row["ca_error_angstrom"]) >= error_threshold
    ]
    ax.scatter(
        [row["plddt"] for row in ordinary],
        [row["ca_error_angstrom"] for row in ordinary],
        s=9,
        color="#2563A6",
        alpha=0.45,
        edgecolors="none",
        label="Other matched residues",
    )
    if discrepancies:
        ax.scatter(
            [row["plddt"] for row in discrepancies],
            [row["ca_error_angstrom"] for row in discrepancies],
            s=20,
            color="#B33A3A",
            alpha=0.85,
            edgecolors="none",
            label="High-confidence discrepancy candidate",
        )
    ax.axhline(error_threshold, color="#5F6368", linestyle="--", linewidth=0.8)
    ax.axvline(plddt_threshold, color="#5F6368", linestyle="--", linewidth=0.8)
    ax.set_xlabel("pLDDT")
    ax.set_ylabel("Aligned Cα error (Å)")
    ax.set_title("Confidence versus structural discrepancy")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(color="#E2E6EB", linewidth=0.5)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    scatter_name = (
        "figure_3_plddt_error.png"
        if benchmark_name == "globin"
        else f"{benchmark_name}_plddt_error.png"
    )
    fig.savefig(figures_dir / scatter_name, dpi=300)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("preprint/results/globin_benchmark"),
    )
    parser.add_argument("--panel-file", type=Path)
    parser.add_argument("--benchmark-name", default="globin")
    parser.add_argument("--figures-dir", type=Path)
    parser.add_argument("--allow-failures", action="store_true")
    parser.add_argument(
        "--discrepancy-error-threshold",
        type=float,
        default=DEFAULT_DISCREPANCY_ERROR_ANGSTROM,
    )
    parser.add_argument(
        "--discrepancy-plddt-threshold",
        type=float,
        default=DEFAULT_DISCREPANCY_PLDDT,
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    raw_dir = output_dir / "raw"
    figures_dir = (
        args.figures_dir.resolve()
        if args.figures_dir
        else output_dir.parents[1] / "figures"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    panel = load_panel(args.panel_file)

    residue_rows: list[dict] = []
    results: list[TargetResult] = []
    sources: list[dict] = []
    failures: list[dict[str, str]] = []
    for spec in panel:
        try:
            result, metadata = analyze_target(spec, raw_dir, residue_rows)
        except Exception as exc:
            failures.append(
                {
                    "target": spec["target"],
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            if not args.allow_failures:
                raise
        else:
            results.append(result)
            sources.extend(metadata)
    if not results:
        raise RuntimeError("No panel target completed successfully")

    target_path = output_dir / "target_summary.csv"
    with target_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(asdict(results[0]).keys()),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)

    residue_path = output_dir / "residue_metrics.csv"
    with residue_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(residue_rows[0].keys()),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(residue_rows)

    candidate_rows = detect_discrepancy_regions(
        residue_rows,
        error_threshold=args.discrepancy_error_threshold,
        plddt_threshold=args.discrepancy_plddt_threshold,
    )
    candidate_path = output_dir / "candidate_regions.csv"
    candidate_fields = [
        "candidate_id",
        "target",
        "uniprot",
        "pdb_id",
        "experimental_chain",
        "alphafold_residue_start",
        "alphafold_residue_end",
        "residue_count",
        "mean_plddt",
        "median_ca_error_angstrom",
        "max_ca_error_angstrom",
        "candidate_score",
        "candidate_status",
        "novelty_status",
        "evidence_tier",
        "required_follow_up",
    ]
    with candidate_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=candidate_fields,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(candidate_rows)

    save_figures(
        results,
        residue_rows,
        figures_dir,
        benchmark_name=args.benchmark_name,
        error_threshold=args.discrepancy_error_threshold,
        plddt_threshold=args.discrepancy_plddt_threshold,
    )
    aggregate = {
        "targets_declared": len(panel),
        "targets_completed": len(results),
        "targets_failed": len(failures),
        "matched_residues": sum(result.matched_residues for result in results),
        "median_target_rmsd_angstrom": float(
            np.median([result.ca_rmsd_angstrom for result in results])
        ),
        "targets_below_1a_rmsd": sum(
            result.ca_rmsd_angstrom < 1.0 for result in results
        ),
        "median_target_high_confidence_rmsd_angstrom": float(
            np.median([result.high_confidence_ca_rmsd_angstrom for result in results])
        ),
        "targets_below_1a_high_confidence_rmsd": sum(
            result.high_confidence_ca_rmsd_angstrom < 1.0 for result in results
        ),
        "candidate_regions": len(candidate_rows),
        "regional_candidates": sum(
            row["candidate_status"] == "regional_hypothesis_candidate"
            for row in candidate_rows
        ),
    }
    manifest = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "benchmark_name": args.benchmark_name,
        "panel_declared_before_analysis": panel,
        "panel_file": str(args.panel_file.resolve()) if args.panel_file else None,
        "panel_file_sha256": sha256(args.panel_file) if args.panel_file else None,
        "coordinate_method": (
            "matching C-alpha atoms after Needleman-Wunsch sequence alignment; "
            "whole-chain and pLDDT>=70 core Kabsch superpositions are reported"
        ),
        "candidate_alignment_basis": (
            "one rigid transform fit on matched AlphaFold residues with pLDDT>=70, "
            "then applied to every matched residue"
        ),
        "bootstrap": {
            "method": "moving-block residue bootstrap",
            "replicates": BOOTSTRAP_REPLICATES,
            "block_size": BOOTSTRAP_BLOCK_SIZE,
            "seed": BOOTSTRAP_SEED,
            "interpretation": "descriptive interval; residues are not independent biological replicates",
        },
        "candidate_rule": {
            "minimum_ca_error_angstrom": args.discrepancy_error_threshold,
            "minimum_plddt": args.discrepancy_plddt_threshold,
            "novelty_interpretation": "hypothesis-generating only; novelty is not established",
        },
        "sources": sources,
        "results": [asdict(result) for result in results],
        "failures": failures,
        "aggregate": aggregate,
        "candidate_regions": candidate_rows,
        "output_sha256": {
            "target_summary.csv": sha256(target_path),
            "residue_metrics.csv": sha256(residue_path),
            "candidate_regions.csv": sha256(candidate_path),
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        json.dumps({"aggregate": aggregate, "results": manifest["results"]}, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
