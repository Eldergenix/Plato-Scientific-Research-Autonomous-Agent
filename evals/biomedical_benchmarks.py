"""Pinned external biomedical benchmark catalogs.

This module imports benchmark *task metadata* without claiming that Plato has
solved the tasks.  The separation matters: catalog coverage is an input to an
evaluation, while agent performance requires executable runs and scored
outputs.

CompBioBench v1 is pinned to an immutable Hugging Face revision and verified
with SHA-256 before parsing.  Its task metadata is CC BY 4.0 licensed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class PinnedBenchmark:
    """Immutable external benchmark source description."""

    name: str
    version: str
    revision: str
    url: str
    sha256: str
    license: str
    citation_url: str


COMPBIOBENCH_V1 = PinnedBenchmark(
    name="CompBioBench",
    version="v1",
    revision="c673f0855fce09d320f1677f168f7864eec52c1a",
    url=(
        "https://huggingface.co/datasets/Genentech/compbiobench-data-v1/"
        "resolve/c673f0855fce09d320f1677f168f7864eec52c1a/"
        "compbiobench.v1.tsv"
    ),
    sha256="ac8a5dcf813e9e89556701648140a84b2757fe449e35650168de54baed75ce1c",
    license="CC BY 4.0",
    citation_url="https://www.biorxiv.org/content/10.64898/2026.04.06.716850v2",
)


@dataclass(frozen=True)
class BiomedicalBenchmarkTask:
    """Normalized task metadata shared across external benchmark sources."""

    question_id: str
    curator_name: str
    domain: str
    question_style: str
    skills_tested: tuple[str, ...]
    question: str
    internet_required: bool
    gpu_preferred: bool
    file_paths: tuple[str, ...]


def _parse_bool(value: str, *, field: str, question_id: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"{question_id}: {field} must be True or False, got {value!r}")


def _split_list(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def parse_compbiobench_tsv(payload: bytes) -> list[BiomedicalBenchmarkTask]:
    """Parse CompBioBench task metadata and enforce its public contract."""

    text = payload.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    expected = {
        "question_id",
        "curator_name",
        "domain",
        "question_style",
        "skills_tested",
        "question",
        "internet_required",
        "gpu_preferred",
        "file_paths",
    }
    if set(reader.fieldnames or ()) != expected:
        raise ValueError(
            "Unexpected CompBioBench columns: "
            f"{sorted(reader.fieldnames or ())}; expected {sorted(expected)}"
        )

    tasks: list[BiomedicalBenchmarkTask] = []
    seen: set[str] = set()
    for row in reader:
        question_id = (row["question_id"] or "").strip()
        if not question_id:
            raise ValueError("CompBioBench row is missing question_id")
        if question_id in seen:
            raise ValueError(f"Duplicate CompBioBench question_id: {question_id}")
        seen.add(question_id)
        question = (row["question"] or "").strip()
        if not question:
            raise ValueError(f"{question_id}: question is empty")
        tasks.append(
            BiomedicalBenchmarkTask(
                question_id=question_id,
                curator_name=(row["curator_name"] or "").strip(),
                domain=(row["domain"] or "").strip(),
                question_style=(row["question_style"] or "").strip(),
                skills_tested=_split_list(row["skills_tested"] or ""),
                question=question,
                internet_required=_parse_bool(
                    row["internet_required"] or "",
                    field="internet_required",
                    question_id=question_id,
                ),
                gpu_preferred=_parse_bool(
                    row["gpu_preferred"] or "",
                    field="gpu_preferred",
                    question_id=question_id,
                ),
                file_paths=_split_list(row["file_paths"] or ""),
            )
        )
    if not tasks:
        raise ValueError("CompBioBench catalog contains no tasks")
    return tasks


def validate_payload(payload: bytes, benchmark: PinnedBenchmark) -> str:
    """Return the payload digest after checking the pinned source hash."""

    digest = hashlib.sha256(payload).hexdigest()
    if digest != benchmark.sha256:
        raise ValueError(
            f"{benchmark.name} payload hash mismatch: {digest} != {benchmark.sha256}"
        )
    return digest


def download_pinned_benchmark(
    benchmark: PinnedBenchmark = COMPBIOBENCH_V1,
    *,
    opener: Callable[..., object] = urllib.request.urlopen,
) -> bytes:
    """Download and validate an immutable benchmark catalog."""

    request = urllib.request.Request(
        benchmark.url,
        headers={"User-Agent": "Plato-Bio-Benchmark/1.0"},
    )
    with opener(request, timeout=60) as response:  # type: ignore[attr-defined]
        payload = response.read()  # type: ignore[attr-defined]
    validate_payload(payload, benchmark)
    return payload


def summarize_tasks(tasks: list[BiomedicalBenchmarkTask]) -> dict[str, object]:
    """Produce auditable coverage counts without scoring agent performance."""

    return {
        "task_count": len(tasks),
        "domain_counts": dict(sorted(Counter(task.domain for task in tasks).items())),
        "question_style_counts": dict(
            sorted(Counter(task.question_style for task in tasks).items())
        ),
        "skill_counts": dict(
            sorted(
                Counter(skill for task in tasks for skill in task.skills_tested).items()
            )
        ),
        "internet_required_count": sum(task.internet_required for task in tasks),
        "gpu_preferred_count": sum(task.gpu_preferred for task in tasks),
        "tasks_with_files_count": sum(bool(task.file_paths) for task in tasks),
    }


def write_catalog(
    output_dir: Path,
    payload: bytes,
    tasks: list[BiomedicalBenchmarkTask],
    benchmark: PinnedBenchmark = COMPBIOBENCH_V1,
) -> None:
    """Persist the exact catalog, normalized tasks, summary, and provenance."""

    output_dir.mkdir(parents=True, exist_ok=True)
    digest = validate_payload(payload, benchmark)
    (output_dir / "source.tsv").write_bytes(payload)
    (output_dir / "tasks.json").write_text(
        json.dumps([asdict(task) for task in tasks], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    summary = summarize_tasks(tasks)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "benchmark": asdict(benchmark),
        "download_sha256": digest,
        "task_count": len(tasks),
        "performance_results_included": False,
        "interpretation": (
            "This artifact proves catalog ingestion and coverage only; it does not "
            "contain Plato agent performance results."
        ),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("preprint/results/compbiobench_catalog"),
    )
    args = parser.parse_args()
    payload = download_pinned_benchmark()
    tasks = parse_compbiobench_tsv(payload)
    write_catalog(args.output_dir, payload, tasks)
    print(json.dumps(summarize_tasks(tasks), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
