"""Deterministic temporal rediscovery and evidence-bridge scoring.

The scorer asks a bounded retrospective question: using only records available
before a cutoff, can an A-B / B-C evidence graph rank a later-reported A-C
relationship? Outputs are candidate rankings, never declarations of truth or
prospective discovery.
"""

from __future__ import annotations

import itertools
import math
import re
from collections import defaultdict
from datetime import date
from enum import StrEnum

import numpy as np
from pydantic import BaseModel, Field
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class CandidateStatus(StrEnum):
    TEMPORALLY_NOVEL_CANDIDATE = "temporally_novel_candidate"
    KNOWN_PRE_CUTOFF = "known_pre_cutoff"
    UNSUPPORTED = "unsupported"


class FrozenLiteratureRecord(BaseModel):
    """One frozen source record with exact temporal provenance."""

    record_id: str
    title: str
    abstract: str = ""
    published_at: date | None
    source_url: str
    concepts: tuple[str, ...] = ()
    doi: str | None = None
    pmid: str | None = None
    injection_signals: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        return f"{self.title} {self.abstract}".strip()

    @property
    def source_key(self) -> str:
        return (self.doi or self.pmid or self.record_id).strip().lower()


class TemporalNoveltyTask(BaseModel):
    """Frozen retrospective task with a hidden, later-validated target."""

    id: str
    biological_area: str
    cutoff: date
    anchor_concept: str
    target_concept: str
    target_relation: str
    candidate_concepts: tuple[str, ...]
    concept_aliases: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    validation_id: str
    validation_published_at: date
    records: tuple[FrozenLiteratureRecord, ...]
    safety_class: str = "public_nonclinical_literature"
    synthetic: bool = False


class EvidencePath(BaseModel):
    bridge_concept: str
    anchor_record_ids: tuple[str, ...]
    candidate_record_ids: tuple[str, ...]
    independent_source_pairs: int


class TemporalCandidate(BaseModel):
    concept: str
    status: CandidateStatus
    score: float
    rank: int = 0
    direct_prior_record_ids: tuple[str, ...] = ()
    evidence_paths: tuple[EvidencePath, ...] = ()
    independent_bridge_pairs: int = 0
    bridge_concept_count: int = 0
    tfidf_relevance: float = 0.0
    source_diversity: int = 0
    provenance_completeness: float = 0.0
    abstain_reason: str | None = None


def extract_concepts(
    text: str,
    aliases: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    """Match declared aliases with token boundaries and no substring leakage."""

    matched: list[str] = []
    for concept, terms in aliases.items():
        candidates = (concept, *terms)
        if any(
            re.search(
                rf"(?<!\w){re.escape(term)}(?!\w)",
                text,
                flags=re.IGNORECASE,
            )
            for term in candidates
            if term.strip()
        ):
            matched.append(concept)
    return tuple(sorted(set(matched)))


def _validate_and_prepare(
    task: TemporalNoveltyTask,
) -> tuple[list[FrozenLiteratureRecord], list[FrozenLiteratureRecord]]:
    if task.validation_published_at <= task.cutoff:
        raise ValueError(f"{task.id}: validation publication must be after cutoff")
    seen: set[str] = set()
    usable: list[FrozenLiteratureRecord] = []
    quarantined: list[FrozenLiteratureRecord] = []
    for record in task.records:
        if record.published_at is None:
            raise ValueError(
                f"{task.id}: {record.record_id} has unknown publication date"
            )
        if record.published_at >= task.cutoff:
            raise ValueError(
                f"{task.id}: temporal leakage from {record.record_id} "
                f"({record.published_at} >= {task.cutoff})"
            )
        if record.source_key in seen:
            continue
        seen.add(record.source_key)
        if record.injection_signals:
            quarantined.append(record)
            continue
        concepts = record.concepts or extract_concepts(
            record.text,
            task.concept_aliases,
        )
        usable.append(
            record.model_copy(update={"concepts": tuple(sorted(set(concepts)))})
        )
    return usable, quarantined


def _edge_index(
    records: list[FrozenLiteratureRecord],
) -> dict[frozenset[str], set[str]]:
    edges: dict[frozenset[str], set[str]] = defaultdict(set)
    for record in records:
        for left, right in itertools.combinations(sorted(set(record.concepts)), 2):
            edges[frozenset((left, right))].add(record.record_id)
    return edges


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    low, high = min(values), max(values)
    if math.isclose(low, high):
        return [1.0 if high > 0 else 0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def _candidate_features(
    task: TemporalNoveltyTask,
    records: list[FrozenLiteratureRecord],
) -> list[dict[str, object]]:
    edges = _edge_index(records)
    records_by_id = {record.record_id: record for record in records}
    corpus_text = [record.text for record in records]
    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=1,
    )
    corpus_matrix = vectorizer.fit_transform(corpus_text)

    features: list[dict[str, object]] = []
    all_concepts = set(
        itertools.chain.from_iterable(record.concepts for record in records)
    )
    for candidate in task.candidate_concepts:
        if candidate == task.anchor_concept:
            continue
        direct_ids = edges.get(frozenset((task.anchor_concept, candidate)), set())
        paths: list[EvidencePath] = []
        evidence_ids: set[str] = set(direct_ids)
        for bridge in sorted(all_concepts - {task.anchor_concept, candidate}):
            anchor_ids = edges.get(frozenset((task.anchor_concept, bridge)), set())
            candidate_ids = edges.get(frozenset((bridge, candidate)), set())
            independent_pairs = sum(
                left != right for left in anchor_ids for right in candidate_ids
            )
            if independent_pairs:
                paths.append(
                    EvidencePath(
                        bridge_concept=bridge,
                        anchor_record_ids=tuple(sorted(anchor_ids)),
                        candidate_record_ids=tuple(sorted(candidate_ids)),
                        independent_source_pairs=independent_pairs,
                    )
                )
                evidence_ids.update(anchor_ids)
                evidence_ids.update(candidate_ids)

        evidence_indices = [
            index
            for index, record in enumerate(records)
            if record.record_id in evidence_ids
        ]
        query = f"{task.anchor_concept} {candidate} {task.target_relation}"
        query_vector = vectorizer.transform([query])
        relevance = (
            float(
                np.mean(
                    cosine_similarity(
                        query_vector,
                        corpus_matrix[evidence_indices],
                    )
                )
            )
            if evidence_indices
            else 0.0
        )
        provenance = [
            bool(records_by_id[record_id].source_url)
            and records_by_id[record_id].published_at is not None
            for record_id in evidence_ids
        ]
        features.append(
            {
                "concept": candidate,
                "direct_ids": tuple(sorted(direct_ids)),
                "paths": tuple(paths),
                "bridge_pairs": sum(path.independent_source_pairs for path in paths),
                "bridge_count": len(paths),
                "tfidf": relevance,
                "source_diversity": len(evidence_ids),
                "provenance": float(np.mean(provenance)) if provenance else 0.0,
                "frequency": sum(candidate in record.concepts for record in records),
            }
        )
    return features


def score_temporal_task(
    task: TemporalNoveltyTask,
    *,
    condition: str = "evidence_aware",
) -> tuple[list[TemporalCandidate], tuple[str, ...]]:
    """Rank candidates under a declared baseline or evidence-aware condition."""

    allowed = {"frequency", "tfidf", "abc_bridge", "evidence_aware"}
    if condition not in allowed:
        raise ValueError(f"Unknown temporal novelty condition: {condition}")
    records, quarantined = _validate_and_prepare(task)
    if not records:
        return [], tuple(record.record_id for record in quarantined)
    features = _candidate_features(task, records)
    bridge_norm = _minmax([float(item["bridge_pairs"]) for item in features])
    frequency_norm = _minmax([float(item["frequency"]) for item in features])
    diversity_norm = _minmax([float(item["source_diversity"]) for item in features])

    candidates: list[TemporalCandidate] = []
    for item, bridge_scaled, frequency_scaled, diversity_scaled in zip(
        features,
        bridge_norm,
        frequency_norm,
        diversity_norm,
        strict=True,
    ):
        direct_ids = tuple(item["direct_ids"])
        bridge_pairs = int(item["bridge_pairs"])
        if direct_ids:
            status = CandidateStatus.KNOWN_PRE_CUTOFF
        elif bridge_pairs:
            status = CandidateStatus.TEMPORALLY_NOVEL_CANDIDATE
        else:
            status = CandidateStatus.UNSUPPORTED

        if condition == "frequency":
            score = frequency_scaled
        elif condition == "tfidf":
            score = float(item["tfidf"])
        elif condition == "abc_bridge":
            score = bridge_scaled
        else:
            score = (
                0.45 * bridge_scaled
                + 0.25 * float(item["tfidf"])
                + 0.20 * diversity_scaled
                + 0.10 * float(item["provenance"])
                - (1.0 if direct_ids else 0.0)
            )
        candidates.append(
            TemporalCandidate(
                concept=str(item["concept"]),
                status=status,
                score=float(score),
                direct_prior_record_ids=direct_ids,
                evidence_paths=tuple(item["paths"]),
                independent_bridge_pairs=bridge_pairs,
                bridge_concept_count=int(item["bridge_count"]),
                tfidf_relevance=float(item["tfidf"]),
                source_diversity=int(item["source_diversity"]),
                provenance_completeness=float(item["provenance"]),
                abstain_reason=(
                    "No independent A-B / B-C evidence path"
                    if status is CandidateStatus.UNSUPPORTED
                    else None
                ),
            )
        )

    candidates.sort(key=lambda candidate: (-candidate.score, candidate.concept))
    ranked = [
        candidate.model_copy(update={"rank": rank})
        for rank, candidate in enumerate(candidates, 1)
    ]
    return ranked, tuple(record.record_id for record in quarantined)


__all__ = [
    "CandidateStatus",
    "EvidencePath",
    "FrozenLiteratureRecord",
    "TemporalCandidate",
    "TemporalNoveltyTask",
    "extract_concepts",
    "score_temporal_task",
]
