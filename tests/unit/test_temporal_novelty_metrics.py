from __future__ import annotations

import numpy as np

from evals.biological_novelty.metrics import (
    bootstrap_interval,
    mean_reciprocal_rank,
    recall_at_k,
)


def test_rank_metrics_use_tasks_as_units():
    ranks = [1, 2, None, 10]

    assert mean_reciprocal_rank(ranks) == (1 + 0.5 + 0 + 0.1) / 4
    assert recall_at_k(ranks, 1) == 0.25
    assert recall_at_k(ranks, 10) == 0.75


def test_bootstrap_interval_is_reproducible():
    values = [1.0, 0.5, 0.0, 0.25]

    first = bootstrap_interval(values, np.mean, replicates=500, seed=9)
    second = bootstrap_interval(values, np.mean, replicates=500, seed=9)

    assert first == second
    assert first[0] <= np.mean(values) <= first[1]
