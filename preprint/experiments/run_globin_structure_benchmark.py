#!/usr/bin/env python3
"""Reproduce the Plato-Bio globin structure benchmark.

The script downloads three AlphaFold DB models and two experimental PDB
entries, aligns matching C-alpha atoms after global sequence alignment, and
writes a machine-readable result bundle.  It intentionally uses a small,
predeclared panel so the preprint reports a transparent case study rather than
an exploratory result selected after inspection.
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
    matched_residues: int
    sequence_identity: float
    ca_rmsd_angstrom: float
    median_ca_error_angstrom: float
    fraction_within_2a: float
    fraction_within_5a: float
    mean_plddt: float
    spearman_plddt_vs_negative_error: float
    spearman_pvalue: float


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
            "https://alphafold.ebi.ac.uk/files/"
            f"AF-{accession}-F1-model_v{version}.pdb"
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
    moving_center = moving.mean(axis=0)
    fixed_center = fixed.mean(axis=0)
    centered_moving = moving - moving_center
    centered_fixed = fixed - fixed_center
    covariance = centered_moving.T @ centered_fixed
    u, _, vt = np.linalg.svd(covariance)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1
        rotation = u @ vt
    return centered_moving @ rotation + fixed_center


def analyze_target(spec: dict, raw_dir: Path, residue_rows: list[dict]) -> tuple[TargetResult, list[dict]]:
    accession = spec["uniprot"]
    pdb_id = spec["pdb_id"]
    experimental_path = raw_dir / f"{pdb_id}.pdb"
    download(f"https://files.rcsb.org/download/{pdb_id}.pdb", experimental_path)

    model_url, model_record = alphafold_model_url(accession)
    model_path = raw_dir / f"AF-{accession}-F1.pdb"
    download(model_url, model_path)

    experimental = parse_ca_atoms(experimental_path, spec["chain"])
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
    aligned = kabsch_align(moving, fixed)
    distances = np.linalg.norm(aligned - fixed, axis=1)
    plddt = np.array([pred.confidence for pred, _ in comparable], dtype=float)
    correlation = spearmanr(plddt, -distances)

    identities = sum(
        1
        for i, j in aligned_pairs
        if i is not None and j is not None and predicted[i].aa == experimental[j].aa
    )
    paired_positions = sum(1 for i, j in aligned_pairs if i is not None and j is not None)
    identity = identities / paired_positions if paired_positions else math.nan

    local_rows = []
    for index, ((pred, exp), distance) in enumerate(zip(comparable, distances, strict=True), start=1):
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
        }
        residue_rows.append(row)
        local_rows.append(row)

    result = TargetResult(
        target=spec["target"],
        uniprot=accession,
        pdb_id=pdb_id,
        chain=spec["chain"],
        matched_residues=len(comparable),
        sequence_identity=float(identity),
        ca_rmsd_angstrom=float(np.sqrt(np.mean(np.square(distances)))),
        median_ca_error_angstrom=float(np.median(distances)),
        fraction_within_2a=float(np.mean(distances <= 2.0)),
        fraction_within_5a=float(np.mean(distances <= 5.0)),
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
    }
    return result, [metadata]


def save_figures(results: list[TargetResult], residue_rows: list[dict], figures_dir: Path) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)
    labels = [result.target.replace("_", " ") for result in results]
    rmsd = [result.ca_rmsd_angstrom for result in results]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    bars = ax.bar(labels, rmsd, color="#2563A6", edgecolor="#16324F", linewidth=0.8)
    ax.set_ylabel("Cα RMSD after alignment (Å)")
    ax.set_title("AlphaFold-to-experiment agreement in the globin case study")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#D9DEE5", linewidth=0.7)
    ax.set_axisbelow(True)
    ax.set_ylim(0, max(rmsd) * 1.24)
    for bar, value in zip(bars, rmsd, strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.03, f"{value:.2f}", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(figures_dir / "figure_2_globin_rmsd.png", dpi=300)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(9.0, 3.2), sharey=True)
    for ax, result in zip(axes, results, strict=True):
        rows = [row for row in residue_rows if row["target"] == result.target]
        ax.scatter(
            [row["plddt"] for row in rows],
            [row["ca_error_angstrom"] for row in rows],
            s=12,
            color="#2563A6",
            alpha=0.72,
            edgecolors="none",
        )
        ax.set_title(result.target.replace("_", " "), fontsize=9)
        ax.set_xlabel("pLDDT")
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(color="#E2E6EB", linewidth=0.5)
    axes[0].set_ylabel("Aligned Cα error (Å)")
    fig.suptitle("Residue confidence versus structural error", fontsize=11)
    fig.tight_layout()
    fig.savefig(figures_dir / "figure_3_plddt_error.png", dpi=300)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("preprint/results/globin_benchmark"),
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    raw_dir = output_dir / "raw"
    figures_dir = output_dir.parents[1] / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)

    residue_rows: list[dict] = []
    results: list[TargetResult] = []
    sources: list[dict] = []
    for spec in PANEL:
        result, metadata = analyze_target(spec, raw_dir, residue_rows)
        results.append(result)
        sources.extend(metadata)

    target_path = output_dir / "target_summary.csv"
    with target_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)

    residue_path = output_dir / "residue_metrics.csv"
    with residue_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(residue_rows[0].keys()))
        writer.writeheader()
        writer.writerows(residue_rows)

    save_figures(results, residue_rows, figures_dir)
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "panel_declared_in_source": [dict(item) for item in PANEL],
        "coordinate_method": "matching C-alpha atoms after Needleman-Wunsch sequence alignment and Kabsch superposition",
        "sources": sources,
        "results": [asdict(result) for result in results],
        "output_sha256": {
            "target_summary.csv": sha256(target_path),
            "residue_metrics.csv": sha256(residue_path),
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(manifest["results"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
