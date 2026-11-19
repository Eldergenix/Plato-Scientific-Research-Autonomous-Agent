"""Hypothesis tests the verifier computes itself, from the experiment's unit-level data.

An experiment script reports its own ``p_value``, but that script was written by the
model whose claim is being checked: it chooses the test, and nothing guaranteed the test
was appropriate (pseudo-replicated units, a one-sided test, a test picked after seeing the
data). So the script must also write the outcome of every independent unit to
:data:`UNITS_FILE`, and the verifier recomputes the test with a rule fixed in advance:

=================  ===================================  ==================================
Design             Difference claim                     Equivalence claim
=================  ===================================  ==================================
two groups         Welch two-sample t-test, two-sided   TOST on the Welch difference
matched pairs      paired t-test, two-sided             TOST on the paired differences
one sample         one-sample t-test vs the reference   TOST around the reference
=================  ===================================  ==================================

File format (CSV with a header row; extra columns are ignored):

* ``value`` (required): the outcome of one independent unit, a finite number;
* ``group`` (optional): ``control`` or ``treatment``; without it the rows are one sample
  compared with the reference value;
* ``pair`` (optional, with ``group``): matching id; each id has one control and one
  treatment row.

The effect is ``mean(treatment) - mean(control)`` (paired: the mean paired difference) or
``mean(value) - reference``. Equivalence tests ``|effect - reference| < tolerance`` for
one sample and ``|effect| < tolerance`` for two groups. Everything here is deterministic:
no model call, no randomness.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from typing import Any, Literal

from scipy import stats as _st

UNITS_FILE = "plato_units.csv"
SEALED_UNITS_FILE = "plato_sealed_units.csv"
# Bounds on what the verifier parses (the sandbox already caps a file at 1 MiB).
MAX_UNITS = 200_000
MIN_PER_GROUP = 2

Direction = Literal["increase", "decrease", "nonzero"]
Support = Literal["yes", "no", "inconclusive"]


class UnitDataError(ValueError):
    """The unit file is missing, malformed or cannot support the test."""


@dataclass(frozen=True)
class UnitTest:
    design: str  # two_sample | paired | one_sample
    test: str  # welch_t | paired_t | one_sample_t | tost_welch | tost_paired | tost_one_sample
    n: int  # independent units used
    effect: float
    se: float
    df: float
    p_value: float

    def metrics(self, prefix: str = "stats_") -> dict[str, Any]:
        return {
            f"{prefix}design": self.design,
            f"{prefix}test": self.test,
            f"{prefix}n": self.n,
            f"{prefix}effect": _round(self.effect),
            f"{prefix}se": _round(self.se),
            f"{prefix}df": _round(self.df),
        }


def _round(x: float) -> float:
    return float(f"{x:.6g}")


def _finite(raw: str, row: int) -> float:
    try:
        x = float(raw)
    except (TypeError, ValueError):
        raise UnitDataError(f"row {row}: value {raw!r} is not a number") from None
    if not math.isfinite(x):
        raise UnitDataError(f"row {row}: value {raw!r} is not finite")
    return x


def parse_units(
    data: bytes,
) -> tuple[list[float], list[float], list[tuple[float, float]] | None]:
    """(control, treatment, pairs). One-sample data comes back as ([], values, None)."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise UnitDataError("unit file is not UTF-8 text") from None
    reader = csv.DictReader(io.StringIO(text))
    fields = {(f or "").strip().lower(): f for f in reader.fieldnames or []}
    if "value" not in fields:
        raise UnitDataError("unit file has no 'value' column")
    has_group = "group" in fields
    has_pair = "pair" in fields
    if has_pair and not has_group:
        raise UnitDataError("a 'pair' column needs a 'group' column")
    control: list[float] = []
    treatment: list[float] = []
    by_pair: dict[str, dict[str, float]] = {}
    for i, row in enumerate(reader, start=2):
        if i - 1 > MAX_UNITS:
            raise UnitDataError(f"more than {MAX_UNITS} units")
        value = _finite(row.get(fields["value"]), i)
        if not has_group:
            treatment.append(value)
            continue
        group = (row.get(fields["group"]) or "").strip().lower()
        if group not in ("control", "treatment"):
            raise UnitDataError(
                f"row {i}: group must be 'control' or 'treatment', not {group!r}"
            )
        (control if group == "control" else treatment).append(value)
        if has_pair:
            pid = (row.get(fields["pair"]) or "").strip()
            if not pid:
                raise UnitDataError(f"row {i}: empty pair id")
            slot = by_pair.setdefault(pid, {})
            if group in slot:
                raise UnitDataError(f"pair {pid!r} has two {group} rows")
            slot[group] = value
    pairs = None
    if has_pair:
        incomplete = [p for p, s in by_pair.items() if len(s) != 2]
        if incomplete:
            raise UnitDataError(
                f"{len(incomplete)} pair(s) lack a control or treatment row"
            )
        pairs = [(s["control"], s["treatment"]) for s in by_pair.values()]
    return control, treatment, pairs


def _mean_var(xs: list[float]) -> tuple[float, float]:
    n = len(xs)
    m = math.fsum(xs) / n
    return m, math.fsum((x - m) ** 2 for x in xs) / (n - 1)


def _one_sample(xs: list[float]) -> tuple[float, float, float]:
    """(mean, se, df) of a single sample."""
    if len(xs) < MIN_PER_GROUP:
        raise UnitDataError(f"need at least {MIN_PER_GROUP} units, got {len(xs)}")
    m, v = _mean_var(xs)
    return m, math.sqrt(v / len(xs)), len(xs) - 1.0


def _welch(control: list[float], treatment: list[float]) -> tuple[float, float, float]:
    """(difference of means, se, Welch-Satterthwaite df)."""
    for name, xs in (("control", control), ("treatment", treatment)):
        if len(xs) < MIN_PER_GROUP:
            raise UnitDataError(
                f"need at least {MIN_PER_GROUP} {name} units, got {len(xs)}"
            )
    mc, vc = _mean_var(control)
    mt, vt = _mean_var(treatment)
    a, b = vc / len(control), vt / len(treatment)
    se = math.sqrt(a + b)
    df = (
        (a + b) ** 2
        / (
            (a**2 / (len(control) - 1) if a else 0.0)
            + (b**2 / (len(treatment) - 1) if b else 0.0)
        )
        if a + b > 0
        else float("nan")
    )
    return mt - mc, se, df


def _two_sided(t: float, df: float) -> float:
    return float(min(1.0, 2.0 * _st.t.sf(abs(t), df)))


def _tost(estimate: float, center: float, tolerance: float, se: float, df: float):
    """p of H0: |estimate - center| >= tolerance (max of the two one-sided tests)."""
    lower = _st.t.sf((estimate - (center - tolerance)) / se, df)
    upper = _st.t.cdf((estimate - (center + tolerance)) / se, df)
    return float(max(lower, upper))


def compute_test(
    data: bytes,
    *,
    test_kind: str,
    reference: float | None,
    tolerance: float | None,
) -> UnitTest:
    """Recompute the claim's hypothesis test from the unit file (see module docstring)."""
    control, treatment, pairs = parse_units(data)
    if pairs is not None:
        design = "paired"
        diffs = [t - c for c, t in pairs]
        effect, se, df = _one_sample(diffs)
        n = len(pairs)
        center = 0.0
    elif control:
        design = "two_sample"
        effect, se, df = _welch(control, treatment)
        n = len(control) + len(treatment)
        center = 0.0
    else:
        design = "one_sample"
        if reference is None:
            raise UnitDataError(
                "one-sample data needs a reference value (the planned reference_value)"
            )
        mean, se, df = _one_sample(treatment)
        effect = mean - reference
        n = len(treatment)
        center = 0.0
    if not (se > 0 and math.isfinite(se) and df > 0 and math.isfinite(df)):
        raise UnitDataError(
            "the units show no variation, so no test can be computed (report the "
            "outcome of each independent replicate, not a constant)"
        )
    if test_kind == "equivalence":
        if tolerance is None or not (tolerance > 0 and math.isfinite(tolerance)):
            raise UnitDataError("an equivalence test needs a positive tolerance")
        p = _tost(effect, center, tolerance, se, df)
        test = {
            "paired": "tost_paired",
            "two_sample": "tost_welch",
            "one_sample": "tost_one_sample",
        }[design]
    else:
        p = _two_sided((effect - center) / se, df)
        test = {
            "paired": "paired_t",
            "two_sample": "welch_t",
            "one_sample": "one_sample_t",
        }[design]
    return UnitTest(design, test, n, effect, se, df, p)


def supports_hypothesis(
    test_kind: str, direction: str | None, effect: float, p: float, alpha: float
) -> Support:
    """Does the recomputed test support the hypothesis? A rule, not a judgement.

    Equivalence: shown (p < alpha) is "yes", otherwise "inconclusive" (failing to show
    agreement is not evidence of disagreement). Difference: p >= alpha is "inconclusive";
    a significant effect is "yes" when its sign is the predicted one (any sign for
    "nonzero") and "no" when it is the opposite."""
    if p >= alpha:
        return "inconclusive"
    if test_kind == "equivalence":
        return "yes"
    if direction == "increase":
        return "yes" if effect > 0 else "no"
    if direction == "decrease":
        return "yes" if effect < 0 else "no"
    return "yes"


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def recompute(
    spec: dict[str, Any],
    metrics: dict[str, Any],
    files: dict[str, bytes],
    alpha: float,
) -> tuple[dict[str, Any], Support | None]:
    """Fact metrics from the unit file, and the rule-based support verdict.

    The reported ``p_value`` is kept as ``p_value_reported``; with valid unit data,
    ``p_value`` becomes the recomputed one and ``stats_source`` is ``"unit_data"``.
    Otherwise ``stats_source`` is ``"reported"`` (the script's own test is used, as
    before) with the reason in ``stats_note``, and the support verdict is None so the
    caller falls back to the analyst's reading. Reference and tolerance come from the
    plan (pre-registered) and, failing that, from the script's metrics."""
    out: dict[str, Any] = {"p_value_reported": metrics.get("p_value")}
    reference = _num(spec.get("reference_value"))
    tolerance = _num(spec.get("tolerance"))
    if reference is None:
        reference = _num(metrics.get("reference_value"))
    if tolerance is None:
        tolerance = _num(metrics.get("tolerance"))
    data = files.get(UNITS_FILE)
    if data is None:
        return {
            **out,
            "stats_source": "reported",
            "stats_note": f"no {UNITS_FILE} written",
        }, None
    test_kind = spec.get("test_kind", "difference")
    try:
        res = compute_test(
            data, test_kind=test_kind, reference=reference, tolerance=tolerance
        )
    except UnitDataError as exc:
        return {**out, "stats_source": "reported", "stats_note": str(exc)[:300]}, None
    out.update(res.metrics())
    if res.design == "one_sample":
        out["stats_reference"] = reference
    if test_kind == "equivalence" and tolerance is not None:
        out["stats_tolerance"] = tolerance
    out["p_value"] = _round(res.p_value)
    out["stats_source"] = "unit_data"
    return out, supports_hypothesis(
        test_kind, spec.get("expected_direction"), res.effect, res.p_value, alpha
    )


def recompute_sealed(
    fact_metrics: dict[str, Any], files: dict[str, bytes]
) -> dict[str, Any]:
    """Held-out metrics recomputed from :data:`SEALED_UNITS_FILE` with the fact's own
    test settings: ``sealed_p_value`` (the reported one kept as
    ``sealed_p_value_reported``) and ``sealed_stats_effect``. Empty when the fact was not
    tested from unit data or the held-out unit file is missing or invalid."""
    data = files.get(SEALED_UNITS_FILE)
    if data is None or fact_metrics.get("stats_source") != "unit_data":
        return {}
    try:
        res = compute_test(
            data,
            test_kind=fact_metrics.get("test_kind", "difference"),
            reference=_num(fact_metrics.get("stats_reference")),
            tolerance=_num(fact_metrics.get("stats_tolerance")),
        )
    except UnitDataError:
        return {}
    return {
        "sealed_p_value": _round(res.p_value),
        "sealed_stats_effect": _round(res.effect),
        "sealed_stats_n": res.n,
    }
