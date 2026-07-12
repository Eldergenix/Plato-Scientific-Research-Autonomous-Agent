"""Task-level metrics for temporal rediscovery experiments."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

from plato.novelty.temporal import TemporalCandidate


def target_rank(candidates: Sequence[TemporalCandidate], target: str) -> int | None:
    """Return the one-based target rank, or ``None`` when absent."""

    return next(
        (candidate.rank for candidate in candidates if candidate.concept == target),
        None,
    )


def mean_reciprocal_rank(ranks: Sequence[int | None]) -> float:
    if not ranks:
        return 0.0
    return float(np.mean([0.0 if rank is None else 1.0 / rank for rank in ranks]))


def recall_at_k(ranks: Sequence[int | None], k: int) -> float:
    if not ranks:
        return 0.0
    if k < 1:
        raise ValueError("k must be positive")
    return float(np.mean([rank is not None and rank <= k for rank in ranks]))


def bootstrap_interval(
    values: Sequence[float],
    statistic: Callable[[np.ndarray], float],
    *,
    replicates: int = 10_000,
    seed: int = 20260711,
) -> tuple[float, float]:
    """Percentile bootstrap interval with the task as the sampling unit."""

    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or not array.size:
        raise ValueError("bootstrap requires at least one task-level value")
    if replicates < 100:
        raise ValueError("bootstrap requires at least 100 replicates")
    rng = np.random.default_rng(seed)
    estimates = np.empty(replicates, dtype=float)
    for index in range(replicates):
        sample = rng.choice(array, size=array.size, replace=True)
        estimates[index] = statistic(sample)
    low, high = np.quantile(estimates, [0.025, 0.975])
    return float(low), float(high)
