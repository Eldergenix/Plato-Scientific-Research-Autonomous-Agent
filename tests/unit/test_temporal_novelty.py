"""Contract tests for evidence-grounded temporal novelty scoring."""

from __future__ import annotations

from datetime import date

import pytest

from plato.novelty.temporal import (
    CandidateStatus,
    FrozenLiteratureRecord,
    TemporalNoveltyTask,
    extract_concepts,
    score_temporal_task,
)


def _record(
    record_id: str,
    concepts: tuple[str, ...],
    *,
    published_at: date | None = date(1999, 1, 1),
    doi: str | None = None,
    injection_signals: tuple[str, ...] = (),
) -> FrozenLiteratureRecord:
    return FrozenLiteratureRecord(
        record_id=record_id,
        title=" ".join(concepts),
        abstract="Evidence record.",
        published_at=published_at,
        source_url=f"https://example.invalid/{record_id}",
        concepts=concepts,
        doi=doi,
        injection_signals=injection_signals,
    )


def _task(records: list[FrozenLiteratureRecord]) -> TemporalNoveltyTask:
    return TemporalNoveltyTask(
        id="demo",
        biological_area="molecular biology",
        cutoff=date(2000, 1, 1),
        anchor_concept="anchor",
        target_concept="target",
        target_relation="may be biologically connected to",
        candidate_concepts=("target", "known", "unsupported"),
        validation_id="PMID:later",
        validation_published_at=date(2001, 1, 1),
        records=tuple(records),
        synthetic=True,
    )


def test_independent_bridge_ranks_target_and_marks_direct_prior_known():
    task = _task(
        [
            _record("ab", ("anchor", "bridge")),
            _record("bc", ("bridge", "target")),
            _record("ak", ("anchor", "known")),
            _record("u", ("unsupported",)),
        ]
    )

    ranked, quarantined = score_temporal_task(task)
    by_concept = {candidate.concept: candidate for candidate in ranked}

    assert quarantined == ()
    assert ranked[0].concept == "target"
    assert by_concept["target"].status is CandidateStatus.TEMPORALLY_NOVEL_CANDIDATE
    assert by_concept["target"].independent_bridge_pairs == 1
    assert by_concept["known"].status is CandidateStatus.KNOWN_PRE_CUTOFF
    assert by_concept["unsupported"].status is CandidateStatus.UNSUPPORTED


def test_same_source_does_not_form_independent_bridge():
    task = _task([_record("one", ("anchor", "bridge", "target"))])

    ranked, _ = score_temporal_task(task, condition="abc_bridge")
    target = next(candidate for candidate in ranked if candidate.concept == "target")

    assert target.status is CandidateStatus.KNOWN_PRE_CUTOFF
    assert target.independent_bridge_pairs == 0


def test_temporal_leakage_and_unknown_dates_fail_closed():
    with pytest.raises(ValueError, match="temporal leakage"):
        score_temporal_task(
            _task([_record("late", ("anchor",), published_at=date(2000, 1, 1))])
        )

    with pytest.raises(ValueError, match="unknown publication date"):
        score_temporal_task(_task([_record("unknown", ("anchor",), published_at=None)]))


def test_duplicate_doi_does_not_inflate_bridge_support():
    task = _task(
        [
            _record("ab-1", ("anchor", "bridge"), doi="10.1/duplicate"),
            _record("ab-2", ("anchor", "bridge"), doi="10.1/duplicate"),
            _record("bc", ("bridge", "target")),
        ]
    )

    ranked, _ = score_temporal_task(task)
    target = next(candidate for candidate in ranked if candidate.concept == "target")

    assert target.independent_bridge_pairs == 1


def test_injection_signals_quarantine_record_and_persist_id():
    task = _task(
        [
            _record(
                "poison",
                ("anchor", "target"),
                injection_signals=("ignore prior instructions",),
            ),
            _record("ab", ("anchor", "bridge")),
            _record("bc", ("bridge", "target")),
        ]
    )

    ranked, quarantined = score_temporal_task(task)

    assert quarantined == ("poison",)
    assert ranked[0].concept == "target"
    assert ranked[0].status is CandidateStatus.TEMPORALLY_NOVEL_CANDIDATE


def test_alias_matching_uses_token_boundaries():
    aliases = {"akt": ("AKT",), "akt1": ("AKT1",)}

    assert extract_concepts("AKT1 signaling", aliases) == ("akt1",)
