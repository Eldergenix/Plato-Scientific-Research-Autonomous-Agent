#!/usr/bin/env python3
"""Run a frozen Plato-Bio temporal rediscovery fixture set.

Synthetic tasks validate measurement plumbing. Historical tasks test whether a
later-reported relation can be ranked from only pre-cutoff records; neither is
evidence of a prospective biological discovery.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import scipy
import sklearn

from evals.biological_novelty.metrics import (
    bootstrap_interval,
    mean_reciprocal_rank,
    recall_at_k,
    target_rank,
)
from plato.novelty.temporal import (
    CandidateStatus,
    TemporalNoveltyTask,
    score_temporal_task,
)


CONDITIONS = ("frequency", "tfidf", "abc_bridge", "evidence_aware")
BOOTSTRAP_REPLICATES = 10_000
SEED = 20260711


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_tasks(path: Path) -> list[TemporalNoveltyTask]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("Fixture must be a non-empty JSON list")
    tasks = [TemporalNoveltyTask.model_validate(item) for item in payload]
    if len({task.id for task in tasks}) != len(tasks):
        raise ValueError("Temporal novelty fixture contains duplicate task ids")
    return tasks


def _git_state() -> dict[str, object]:
    def run(*args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            check=False,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    return {
        "commit": run("rev-parse", "HEAD"),
        "dirty": bool(run("status", "--porcelain")),
    }


def _write_figure(
    summary_rows: list[dict],
    destination: Path,
    *,
    title: str,
) -> None:
    display_labels = {
        "frequency": "Frequency",
        "tfidf": "TF–IDF",
        "abc_bridge": "A–B/B–C bridge",
        "evidence_aware": "Evidence-aware",
    }
    labels = [display_labels[row["condition"]] for row in summary_rows]
    mrr = [float(row["mean_reciprocal_rank"]) for row in summary_rows]
    recall1 = [float(row["recall_at_1"]) for row in summary_rows]
    positions = np.arange(len(labels))
    width = 0.36
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.bar(
        positions - width / 2,
        mrr,
        width,
        color="#2563A6",
        label="Mean reciprocal rank",
    )
    ax.bar(
        positions + width / 2,
        recall1,
        width,
        color="#A65A2E",
        label="Recall@1",
    )
    ax.set_xticks(positions, labels, rotation=18, ha="right")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Task-level score")
    ax.set_title(title)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#D9DEE5", linewidth=0.7)
    ax.set_axisbelow(True)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(destination, dpi=300)
    plt.close(fig)


def run_benchmark(
    tasks: list[TemporalNoveltyTask],
    output_dir: Path,
    fixture_path: Path,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    task_rows: list[dict] = []
    candidate_lines: list[str] = []
    summary_rows: list[dict] = []
    bootstrap_payload: dict[str, object] = {}

    for condition in CONDITIONS:
        ranks: list[int | None] = []
        reciprocal_ranks: list[float] = []
        recall1_values: list[float] = []
        recall10_values: list[float] = []
        false_novelty_count = 0
        known_control_count = 0
        for task in tasks:
            candidates, quarantined = score_temporal_task(task, condition=condition)
            rank = target_rank(candidates, task.target_concept)
            ranks.append(rank)
            reciprocal_ranks.append(0.0 if rank is None else 1.0 / rank)
            recall1_values.append(float(rank is not None and rank <= 1))
            recall10_values.append(float(rank is not None and rank <= 10))
            known_controls = [
                candidate
                for candidate in candidates
                if candidate.direct_prior_record_ids
            ]
            known_control_count += len(known_controls)
            false_novelty_count += sum(
                candidate.status is CandidateStatus.TEMPORALLY_NOVEL_CANDIDATE
                for candidate in known_controls
            )
            task_rows.append(
                {
                    "task_id": task.id,
                    "condition": condition,
                    "target_concept": task.target_concept,
                    "target_rank": rank or "",
                    "target_reciprocal_rank": 0.0 if rank is None else 1.0 / rank,
                    "target_in_top_1": bool(rank is not None and rank <= 1),
                    "target_in_top_10": bool(rank is not None and rank <= 10),
                    "quarantined_records": len(quarantined),
                    "synthetic": task.synthetic,
                }
            )
            for candidate in candidates:
                candidate_lines.append(
                    json.dumps(
                        {
                            "task_id": task.id,
                            "condition": condition,
                            **candidate.model_dump(mode="json"),
                        },
                        sort_keys=True,
                    )
                )

        summary = {
            "condition": condition,
            "task_count": len(tasks),
            "mean_reciprocal_rank": mean_reciprocal_rank(ranks),
            "recall_at_1": recall_at_k(ranks, 1),
            "recall_at_10": recall_at_k(ranks, 10),
            "false_novelty_rate": (
                false_novelty_count / known_control_count
                if known_control_count
                else 0.0
            ),
        }
        summary_rows.append(summary)
        bootstrap_payload[condition] = {
            "mean_reciprocal_rank_ci95": bootstrap_interval(
                reciprocal_ranks,
                np.mean,
                replicates=BOOTSTRAP_REPLICATES,
                seed=SEED,
            ),
            "recall_at_1_ci95": bootstrap_interval(
                recall1_values,
                np.mean,
                replicates=BOOTSTRAP_REPLICATES,
                seed=SEED + 1,
            ),
            "recall_at_10_ci95": bootstrap_interval(
                recall10_values,
                np.mean,
                replicates=BOOTSTRAP_REPLICATES,
                seed=SEED + 2,
            ),
        }

    task_path = output_dir / "task_results.csv"
    with task_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(task_rows[0].keys()),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(task_rows)

    summary_path = output_dir / "condition_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(summary_rows[0].keys()),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    candidates_path = output_dir / "candidates.jsonl"
    candidates_path.write_text("\n".join(candidate_lines) + "\n", encoding="utf-8")
    bootstrap_path = output_dir / "bootstrap.json"
    bootstrap_path.write_text(
        json.dumps(bootstrap_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    synthetic_count = sum(task.synthetic for task in tasks)
    historical_count = len(tasks) - synthetic_count
    if historical_count:
        benchmark_name = "Plato-Bio Historical Temporal Rediscovery Pilot"
        interpretation = (
            "Frozen pre-cutoff records test retrospective ranking against later "
            "validation publications. The pilot is small and manually curated; it "
            "does not establish prospective discovery ability or biological truth."
        )
    else:
        benchmark_name = "Plato-Bio Temporal Rediscovery Engineering Smoke"
        interpretation = (
            "Synthetic fixtures verify leakage controls, evidence bridges, ranking, "
            "abstention semantics, and task-level statistics. They are not evidence "
            "of biological discovery or real-world agent efficacy."
        )
    figure_path = output_dir / "temporal_rediscovery.png"
    _write_figure(summary_rows, figure_path, title=benchmark_name)

    manifest = {
        "schema_version": 1,
        "benchmark": benchmark_name,
        "interpretation": interpretation,
        "git": _git_state(),
        "fixture": str(fixture_path),
        "fixture_sha256": sha256(fixture_path),
        "task_count": len(tasks),
        "synthetic_task_count": synthetic_count,
        "historical_task_count": historical_count,
        "validation_publications": [task.validation_id for task in tasks],
        "conditions": list(CONDITIONS),
        "primary_metrics": ["mean reciprocal rank", "Recall@1", "Recall@10"],
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "seed": SEED,
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "elapsed_seconds": time.perf_counter() - started,
        "condition_summary": summary_rows,
        "output_sha256": {
            path.name: sha256(path)
            for path in [
                task_path,
                summary_path,
                candidates_path,
                bootstrap_path,
                figure_path,
            ]
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("evals/biological_novelty/fixtures/engineering_smoke.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("preprint/results/temporal_novelty_smoke"),
    )
    args = parser.parse_args()
    tasks = load_tasks(args.fixtures)
    manifest = run_benchmark(tasks, args.output_dir, args.fixtures)
    print(json.dumps(manifest["condition_summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
