"""Known-answer tasks: synthetic data where the true answer is fixed by construction.

Every generator is deterministic (fixed numpy seed) and writes a training file
``train.csv`` and a held-out file ``holdout.csv`` drawn from the same process, so the
pipeline's held-out re-test is exercised too. ``truth`` is ``effect`` when the question's
effect exists in the generating process and ``null`` when it does not; ``answer`` states the
truth for the judge. Null tasks outnumber effect tasks on purpose: false positives are the
failure an autonomous scientist must not make.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np

Truth = Literal["effect", "null"]


@dataclass(frozen=True)
class Task:
    id: str
    question: str
    truth: Truth
    answer: str
    make: Callable[[np.random.Generator, int], dict[str, list]]
    n_train: int
    n_holdout: int
    seed: int

    def files(self) -> dict[str, bytes]:
        rng = np.random.default_rng(self.seed)
        return {
            "train.csv": _csv(self.make(rng, self.n_train)),
            "holdout.csv": _csv(self.make(rng, self.n_holdout)),
        }


def _csv(columns: dict[str, list]) -> bytes:
    names = list(columns)
    out = io.StringIO()
    out.write(",".join(names) + "\n")
    for row in zip(*(columns[n] for n in names), strict=True):
        out.write(
            ",".join(f"{v:.6g}" if isinstance(v, float) else str(v) for v in row) + "\n"
        )
    return out.getvalue().encode()


def _groups(effect: float, noise: Callable[[np.random.Generator, int], np.ndarray]):
    def make(rng: np.random.Generator, n: int) -> dict[str, list]:
        g = np.repeat(["A", "B"], n // 2)
        y = noise(rng, len(g)) + np.where(g == "B", effect, 0.0)
        return {"group": g.tolist(), "y": y.round(4).tolist()}

    return make


def _normal(rng: np.random.Generator, n: int) -> np.ndarray:
    return rng.normal(10.0, 1.0, n)


def _heavy(rng: np.random.Generator, n: int) -> np.ndarray:
    return 10.0 + rng.standard_t(1.5, n)


def _correlation(rho: float):
    def make(rng: np.random.Generator, n: int) -> dict[str, list]:
        x = rng.normal(0, 1, n)
        y = rho * x + np.sqrt(1 - rho**2) * rng.normal(0, 1, n)
        return {"x": x.round(4).tolist(), "y": y.round(4).tolist()}

    return make


def _proportions(p_a: float, p_b: float):
    def make(rng: np.random.Generator, n: int) -> dict[str, list]:
        arm = np.repeat(["control", "treated"], n // 2)
        p = np.where(arm == "treated", p_b, p_a)
        return {"arm": arm.tolist(), "response": rng.binomial(1, p).tolist()}

    return make


def _confounded(rng: np.random.Generator, n: int) -> dict[str, list]:
    z = rng.normal(0, 1, n)
    x = 0.8 * z + 0.6 * rng.normal(0, 1, n)
    y = 1.5 * z + rng.normal(0, 1, n)  # x has no effect once z is known
    return {
        "x": x.round(4).tolist(),
        "z": z.round(4).tolist(),
        "y": y.round(4).tolist(),
    }


def _subgroups(rng: np.random.Generator, n: int) -> dict[str, list]:
    site = rng.integers(1, 11, n)
    treated = rng.integers(0, 2, n)
    y = rng.normal(50.0, 8.0, n)  # treatment does nothing at any site
    return {
        "site": site.tolist(),
        "treated": treated.tolist(),
        "y": y.round(3).tolist(),
    }


def _interaction(rng: np.random.Generator, n: int) -> dict[str, list]:
    sex = rng.choice(["F", "M"], n)
    treated = rng.integers(0, 2, n)
    y = rng.normal(20.0, 3.0, n) + np.where((sex == "F") & (treated == 1), 2.0, 0.0)
    return {
        "sex": sex.tolist(),
        "treated": treated.tolist(),
        "y": y.round(3).tolist(),
    }


def _simpson(rng: np.random.Generator, n: int) -> dict[str, list]:
    # Group F applies mostly to the selective department; within each department the
    # admission probability does not depend on group.
    group = rng.choice(["F", "M"], n)
    dept = np.where(
        group == "F",
        rng.choice(["easy", "hard"], n, p=[0.2, 0.8]),
        rng.choice(["easy", "hard"], n, p=[0.8, 0.2]),
    )
    admitted = rng.binomial(1, np.where(dept == "easy", 0.6, 0.2))
    return {
        "group": group.tolist(),
        "department": dept.tolist(),
        "admitted": admitted.tolist(),
    }


def _assays(rng: np.random.Generator, n: int) -> dict[str, list]:
    truth = rng.normal(100.0, 10.0, n)
    a = truth + rng.normal(0, 0.35, n)
    b = truth + 0.01 + rng.normal(0, 0.35, n)
    return {
        "sample": list(range(n)),
        "assay_a": a.round(4).tolist(),
        "assay_b": b.round(4).tolist(),
    }


TASKS: tuple[Task, ...] = (
    Task(
        "two_groups_effect",
        "In the provided dataset, does the mean of y differ between group A and group B?",
        "effect",
        "Group B's mean of y is higher than group A's by 0.5 (half a standard deviation).",
        _groups(0.5, _normal),
        400,
        200,
        101,
    ),
    Task(
        "two_groups_null",
        "In the provided dataset, does the mean of y differ between group A and group B?",
        "null",
        "There is no difference: y has the same distribution in groups A and B.",
        _groups(0.0, _normal),
        400,
        200,
        119,
    ),
    Task(
        "correlation_effect",
        "Are x and y correlated in the provided dataset, and in which direction?",
        "effect",
        "x and y are positively correlated with Pearson r = 0.3.",
        _correlation(0.3),
        300,
        150,
        103,
    ),
    Task(
        "correlation_null",
        "Are x and y correlated in the provided dataset, and in which direction?",
        "null",
        "x and y are independent: there is no correlation.",
        _correlation(0.0),
        300,
        150,
        104,
    ),
    Task(
        "proportions_effect",
        "Does the treated arm have a different response rate than the control arm?",
        "effect",
        "The treated arm's response rate (40%) is higher than control's (30%).",
        _proportions(0.30, 0.40),
        1000,
        500,
        122,
    ),
    Task(
        "heavy_tails_null",
        "Does the location (centre) of y differ between group A and group B?",
        "null",
        "No: both groups have identical heavy-tailed (t, 1.5 df) distributions centred on "
        "10; extreme outliers occur in both.",
        _groups(0.0, _heavy),
        300,
        150,
        106,
    ),
    Task(
        "subgroups_null",
        "At which of the ten sites does treatment change the outcome y?",
        "null",
        "At none: treatment has no effect on y at any site.",
        _subgroups,
        1500,
        700,
        107,
    ),
    Task(
        "confounded_null",
        "Does x affect y once z is taken into account?",
        "null",
        "No: y depends only on z. x is associated with y marginally only because x is "
        "correlated with z; adjusting for z, x has no association with y.",
        _confounded,
        500,
        250,
        142,
    ),
    Task(
        "assay_equivalence",
        "Do assay A and assay B give equivalent measurements within a margin of 0.2 units?",
        "effect",
        "Yes: the paired difference between assays is 0.01 on average, well inside the "
        "plus or minus 0.2 margin, so the assays are equivalent.",
        _assays,
        400,
        200,
        109,
    ),
    Task(
        "interaction_effect",
        "Does the effect of treatment on y differ between sexes?",
        "effect",
        "Yes: treatment raises y by 2 in females and has no effect in males.",
        _interaction,
        1200,
        600,
        110,
    ),
    Task(
        "simpsons_null",
        "Is group F less likely to be admitted than group M once department is accounted for?",
        "null",
        "No: within each department admission does not depend on group. The crude "
        "admission rate of F is lower only because F applies mostly to the selective "
        "department.",
        _simpson,
        1200,
        600,
        111,
    ),
    Task(
        "small_sample_null",
        "In the provided dataset, does the mean of y differ between group A and group B?",
        "null",
        "There is no difference: y has the same distribution in groups A and B.",
        _groups(0.0, _normal),
        24,
        24,
        112,
    ),
)


def by_id(ids: list[str] | None) -> list[Task]:
    if not ids:
        return list(TASKS)
    known = {t.id: t for t in TASKS}
    missing = sorted(set(ids) - set(known))
    if missing:
        raise SystemExit(f"unknown task ids: {missing}; known: {sorted(known)}")
    return [known[i] for i in ids]
