#!/usr/bin/env python3
"""Build the architecture and validation figures used in the preprint."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).resolve().parents[2]
FIGURES = ROOT / "preprint" / "figures"


def box(
    ax,
    x,
    y,
    width,
    height,
    label,
    *,
    fill="#F4F6F9",
    edge="#29445C",
    fontsize=8.4,
):
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.025",
        facecolor=fill,
        edgecolor=edge,
        linewidth=1.1,
    )
    ax.add_patch(patch)
    ax.text(x + width / 2, y + height / 2, label, ha="center", va="center", fontsize=fontsize)
    return patch


def arrow(ax, x1, y1, x2, y2, *, color="#4A6478"):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y1),
            (x2, y2),
            arrowstyle="-|>",
            mutation_scale=9,
            linewidth=1.0,
            color=color,
        )
    )


def architecture_figure() -> None:
    fig, ax = plt.subplots(figsize=(9.0, 4.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5)
    ax.axis("off")

    box(ax, 0.25, 2.0, 1.3, 1.0, "Data and\nresearch question", fill="#EEF3F8")
    stages = [
        (1.95, "Idea and\nclarification"),
        (3.35, "Biology-routed\nliterature"),
        (4.75, "Methods and\nanalysis"),
        (6.15, "Paper\ndrafting"),
        (7.55, "Reviewer and\nrevision loop"),
    ]
    for x, label in stages:
        box(ax, x, 2.15, 1.12, 0.7, label, fill="#F7F8FA")
    for start, end in zip([1.55, 3.07, 4.47, 5.87, 7.27], [1.95, 3.35, 4.75, 6.15, 7.55], strict=True):
        arrow(ax, start, 2.5, end, 2.5)
    box(ax, 8.95, 2.0, 0.8, 1.0, "PDF +\nsidecars", fill="#EEF3F8")
    arrow(ax, 8.67, 2.5, 8.95, 2.5)

    controls = [
        (2.0, "Prompt/input\nsanitation", 8.4),
        (3.65, "Claim-evidence\nmatrix", 8.4),
        (5.3, "Scoped execution\nand reproducibility\nmanifest", 7.4),
        (7.25, "Citation and\nscientific gates", 8.4),
    ]
    for x, label, fontsize in controls:
        box(
            ax,
            x,
            0.5,
            1.45,
            0.75,
            label,
            fill="#E7EEF5",
            edge="#1F4D78",
            fontsize=fontsize,
        )
        arrow(ax, x + 0.72, 1.25, x + 0.72, 2.13, color="#1F4D78")

    ax.text(0.25, 4.45, "Plato-Bio validation architecture", fontsize=14, weight="bold", color="#16324F")
    ax.text(
        0.25,
        4.08,
        "A supervised research workflow with domain routing and artifact-level verification gates.",
        fontsize=9.5,
        color="#53687A",
    )
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_1_architecture.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def validation_figure() -> None:
    payload = json.loads((ROOT / "preprint" / "results" / "software_validation.json").read_text())
    order = ["biology_domain", "genomics_adapters", "evidence_and_citations", "adversarial_safety"]
    labels = [
        "Biology domain",
        "Genomics adapters",
        "Evidence and citations",
        "Adversarial safety",
    ]
    passed = []
    skipped = []
    for key in order:
        suite = payload["suites"][key]
        skipped.append(suite["skipped"])
        passed.append(suite["tests"] - suite["failures"] - suite["errors"] - suite["skipped"])

    fig, ax = plt.subplots(figsize=(7.8, 4.3))
    bars = ax.barh(labels, passed, color="#2563A6", edgecolor="#16324F", linewidth=0.8)
    ax.barh(labels, skipped, left=passed, color="#C7CDD4", edgecolor="#6B7280", linewidth=0.6, label="Skipped")
    ax.invert_yaxis()
    ax.set_xlabel("Deterministic tests")
    ax.set_title("Targeted validation suites")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", color="#D9DEE5", linewidth=0.7)
    ax.set_axisbelow(True)
    for bar, value in zip(bars, passed, strict=True):
        ax.text(value + 0.7, bar.get_y() + bar.get_height() / 2, f"{value} passed", va="center", fontsize=8.5)
    if any(skipped):
        ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIGURES / "figure_4_validation_suites.png", dpi=300)
    plt.close(fig)


def main() -> int:
    FIGURES.mkdir(parents=True, exist_ok=True)
    architecture_figure()
    validation_figure()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
