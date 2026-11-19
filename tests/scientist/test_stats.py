"""The verifier's own hypothesis tests (plato.scientist.stats), checked against SciPy."""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import stats as st

from plato.scientist.stats import (
    SEALED_UNITS_FILE,
    UNITS_FILE,
    UnitDataError,
    compute_test,
    parse_units,
    recompute,
    recompute_sealed,
    supports_hypothesis,
)


def _csv(control=None, treatment=None, pairs=None, one=None) -> bytes:
    if one is not None:
        rows = ["unit,value"] + [f"u{i},{float(v)!r}" for i, v in enumerate(one)]
    elif pairs is not None:
        rows = ["unit,pair,group,value"]
        for i, (c, t) in enumerate(pairs):
            rows += [
                f"c{i},p{i},control,{float(c)!r}",
                f"t{i},p{i},treatment,{float(t)!r}",
            ]
    else:
        rows = ["unit,group,value"]
        rows += [f"c{i},control,{float(v)!r}" for i, v in enumerate(control)]
        rows += [f"t{i},treatment,{float(v)!r}" for i, v in enumerate(treatment)]
    return ("\n".join(rows) + "\n").encode()


RNG = np.random.default_rng(7)
CTRL = list(RNG.normal(0.0, 1.0, 30))
TRT = list(RNG.normal(0.6, 2.0, 45))


def test_welch_matches_scipy():
    res = compute_test(
        _csv(CTRL, TRT), test_kind="difference", reference=None, tolerance=None
    )
    ref = st.ttest_ind(TRT, CTRL, equal_var=False)
    assert res.design == "two_sample" and res.test == "welch_t" and res.n == 75
    assert res.p_value == pytest.approx(ref.pvalue, rel=1e-9)
    assert res.effect == pytest.approx(np.mean(TRT) - np.mean(CTRL))
    assert res.df == pytest.approx(ref.df, rel=1e-9)


def test_paired_matches_scipy():
    pairs = list(zip(CTRL, [c + 0.3 + 0.5 * d for c, d in zip(CTRL, TRT)]))
    res = compute_test(
        _csv(pairs=pairs), test_kind="difference", reference=None, tolerance=None
    )
    ref = st.ttest_rel([t for _, t in pairs], [c for c, _ in pairs])
    assert res.test == "paired_t" and res.n == len(pairs)
    assert res.p_value == pytest.approx(ref.pvalue, rel=1e-9)


def test_one_sample_against_the_reference_matches_scipy():
    res = compute_test(
        _csv(one=TRT), test_kind="difference", reference=2.0, tolerance=None
    )
    ref = st.ttest_1samp(TRT, 2.0)
    assert res.test == "one_sample_t"
    assert res.p_value == pytest.approx(ref.pvalue, rel=1e-9)
    assert res.effect == pytest.approx(np.mean(TRT) - 2.0)


def test_one_sample_without_a_reference_is_refused():
    # Defaulting the null to 0 would turn "mean(y) > 2" into "mean(y) != 0".
    with pytest.raises(UnitDataError, match="reference"):
        compute_test(
            _csv(one=TRT), test_kind="difference", reference=None, tolerance=None
        )


def test_tost_is_the_larger_one_sided_p():
    xs = list(np.linspace(0.94, 0.96, 50))
    res = compute_test(
        _csv(one=xs), test_kind="equivalence", reference=0.95, tolerance=0.01
    )
    n, m, s = len(xs), np.mean(xs), np.std(xs, ddof=1) / math.sqrt(len(xs))
    lower = st.t.sf((m - 0.94) / s, n - 1)
    upper = st.t.cdf((m - 0.96) / s, n - 1)
    assert res.test == "tost_one_sample"
    assert res.p_value == pytest.approx(max(lower, upper), rel=1e-9)
    assert res.p_value < 1e-6  # agreement is shown
    # Same data, margin far smaller than the noise: agreement is not shown.
    tight = compute_test(
        _csv(one=xs), test_kind="equivalence", reference=0.95, tolerance=1e-4
    )
    assert tight.p_value > 0.4


def test_equivalence_needs_a_positive_tolerance():
    for tol in (None, 0.0, -1.0, float("inf")):
        with pytest.raises(UnitDataError, match="tolerance"):
            compute_test(
                _csv(CTRL, TRT), test_kind="equivalence", reference=None, tolerance=tol
            )


@pytest.mark.parametrize(
    ("data", "match"),
    [
        (b"unit,group,y\n1,control,1\n", "no 'value' column"),
        (b"unit,group,value\n1,control,abc\n", "not a number"),
        (b"unit,group,value\n1,control,nan\n", "not finite"),
        (b"unit,group,value\n1,placebo,1\n", "control' or 'treatment"),
        (b"unit,pair,value\n1,a,1\n", "needs a 'group' column"),
        (b"unit,pair,group,value\n1,a,control,1\n2,a,control,2\n", "two control rows"),
        (b"unit,pair,group,value\n1,a,control,1\n", "lack a control or treatment"),
        (b"\xff\xfe", "UTF-8"),
    ],
)
def test_malformed_unit_files_are_rejected(data, match):
    with pytest.raises(UnitDataError, match=match):
        parse_units(data)


def test_too_few_units_or_no_variation_is_rejected():
    with pytest.raises(UnitDataError, match="at least 2 control"):
        compute_test(
            _csv([1.0], [1.0, 2.0]),
            test_kind="difference",
            reference=None,
            tolerance=None,
        )
    with pytest.raises(UnitDataError, match="no variation"):
        compute_test(
            _csv([1.0, 1.0], [2.0, 2.0]),
            test_kind="difference",
            reference=None,
            tolerance=None,
        )


def test_support_is_a_rule():
    assert supports_hypothesis("difference", "increase", 0.4, 0.01, 0.05) == "yes"
    assert supports_hypothesis("difference", "increase", -0.4, 0.01, 0.05) == "no"
    assert supports_hypothesis("difference", "decrease", -0.4, 0.01, 0.05) == "yes"
    assert supports_hypothesis("difference", "decrease", 0.4, 0.01, 0.05) == "no"
    assert supports_hypothesis("difference", "nonzero", -0.4, 0.01, 0.05) == "yes"
    assert supports_hypothesis("difference", None, 0.4, 0.01, 0.05) == "yes"
    # Not significant: absence of evidence, never a refutation.
    assert (
        supports_hypothesis("difference", "increase", -0.4, 0.2, 0.05) == "inconclusive"
    )
    assert supports_hypothesis("equivalence", None, 0.0, 0.01, 0.05) == "yes"
    assert supports_hypothesis("equivalence", None, 0.0, 0.2, 0.05) == "inconclusive"


def test_recompute_replaces_a_reported_p_that_the_data_do_not_support():
    null = list(np.linspace(-1, 1, 40))
    spec = {"test_kind": "difference", "expected_direction": "increase"}
    metrics = {"effect": 0.0, "p_value": 0.001}
    out, support = recompute(spec, metrics, {UNITS_FILE: _csv(null, null[::-1])}, 0.05)
    assert out["stats_source"] == "unit_data"
    assert out["p_value_reported"] == 0.001 and out["p_value"] > 0.9
    assert support == "inconclusive"


def test_recompute_falls_back_to_the_reported_p_with_a_reason():
    spec = {"test_kind": "difference"}
    out, support = recompute(spec, {"p_value": 0.01}, {}, 0.05)
    assert out == {
        "p_value_reported": 0.01,
        "stats_source": "reported",
        "stats_note": f"no {UNITS_FILE} written",
    }
    assert support is None
    out, support = recompute(spec, {"p_value": 0.01}, {UNITS_FILE: b"a,b\n1,2\n"}, 0.05)
    assert out["stats_source"] == "reported" and "value" in out["stats_note"]
    assert "p_value" not in out and support is None


def test_reference_and_tolerance_prefer_the_plan_over_the_script():
    xs = list(np.linspace(1.9, 2.1, 30))
    spec = {"test_kind": "equivalence", "reference_value": 2.0, "tolerance": 0.05}
    metrics = {"p_value": 0.5, "reference_value": 0.0, "tolerance": 100.0}
    out, support = recompute(spec, metrics, {UNITS_FILE: _csv(one=xs)}, 0.05)
    assert out["stats_reference"] == 2.0 and out["stats_tolerance"] == 0.05
    assert out["p_value"] < 0.05 and support == "yes"
    # Without a plan value the script's own is used.
    out, _ = recompute(
        {"test_kind": "equivalence"}, metrics, {UNITS_FILE: _csv(one=xs)}, 0.05
    )
    assert out["stats_reference"] == 0.0 and out["stats_tolerance"] == 100.0


def test_held_out_test_is_recomputed_with_the_facts_settings():
    fact, _ = recompute(
        {"test_kind": "difference"},
        {"p_value": 0.01},
        {UNITS_FILE: _csv(CTRL, TRT)},
        0.05,
    )
    sealed = recompute_sealed(fact, {SEALED_UNITS_FILE: _csv(TRT, CTRL)})
    assert sealed["sealed_p_value"] == pytest.approx(
        st.ttest_ind(CTRL, TRT, equal_var=False).pvalue, rel=1e-5
    )
    assert sealed["sealed_stats_effect"] < 0  # the held-out effect points the other way
    assert recompute_sealed(fact, {}) == {}
    assert (
        recompute_sealed(
            {"stats_source": "reported"}, {SEALED_UNITS_FILE: _csv(CTRL, TRT)}
        )
        == {}
    )


async def test_bounded_gather_caps_concurrency_and_finishes_every_item():
    import asyncio

    from plato.scientist.nodes import bounded_gather

    running = peak = 0
    finished: list[int] = []

    async def work(i: int) -> int:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        if i == 1:
            raise RuntimeError("boom")
        finished.append(i)
        return i * 10

    assert await bounded_gather(3, [0, 2, 3, 4, 5, 6], work) == [0, 20, 30, 40, 50, 60]
    assert peak == 3
    finished.clear()
    with pytest.raises(RuntimeError, match="boom"):
        await bounded_gather(2, [0, 1, 2, 3], work)
    # The failure is re-raised only after the other items ran to completion.
    assert sorted(finished) == [0, 2, 3]
