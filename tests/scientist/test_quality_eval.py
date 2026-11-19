"""The known-answer research quality eval (evals/scientist): its ground truth and scoring.

The nightly run itself needs real models; these tests pin down what it relies on: every
task's data really has (or really lacks) the effect its answer states, in the training
and the held-out file alike, and the scoring and threshold logic.
"""

from __future__ import annotations

import io
import json
import uuid

import pandas as pd
import pytest
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.stats.multitest import multipletests

from evals.scientist.score import Judgement, TaskResult, aggregate, breaches, markdown
from evals.scientist.tasks import TASKS, by_id


def _p(task_id: str, d: pd.DataFrame) -> float:
    """p-value of the analysis that answers each question correctly."""
    if task_id.startswith(("two_groups", "small_sample")):
        return stats.ttest_ind(d[d.group == "A"].y, d[d.group == "B"].y).pvalue
    if task_id == "heavy_tails_null":
        return stats.mannwhitneyu(d[d.group == "A"].y, d[d.group == "B"].y).pvalue
    if task_id.startswith("correlation"):
        return stats.pearsonr(d.x, d.y).pvalue
    if task_id == "proportions_effect":
        return smf.logit("response ~ C(arm)", d).fit(disp=0).pvalues.iloc[1]
    if task_id == "subgroups_null":
        ps = [
            stats.ttest_ind(g[g.treated == 1].y, g[g.treated == 0].y).pvalue
            for _, g in d.groupby("site")
        ]
        return multipletests(ps, method="fdr_bh")[1].min()
    if task_id == "confounded_null":
        return smf.ols("y ~ x + z", d).fit().pvalues["x"]
    if task_id == "assay_equivalence":  # TOST against the +-0.2 margin
        diff = d.assay_b - d.assay_a
        se, m, df = diff.std(ddof=1) / len(diff) ** 0.5, diff.mean(), len(diff) - 1
        return max(stats.t.sf((m + 0.2) / se, df), stats.t.cdf((m - 0.2) / se, df))
    if task_id == "interaction_effect":
        return smf.ols("y ~ treated * C(sex)", d).fit().pvalues["treated:C(sex)[T.M]"]
    if task_id == "simpsons_null":
        fit = smf.logit("admitted ~ C(group) + C(department)", d).fit(disp=0)
        return fit.pvalues["C(group)[T.M]"]
    raise AssertionError(task_id)


@pytest.mark.parametrize("task", TASKS, ids=[t.id for t in TASKS])
def test_each_task_has_the_answer_it_states(task):
    files = task.files()
    assert files == task.files()  # deterministic
    for name in ("train.csv", "holdout.csv"):
        p = _p(task.id, pd.read_csv(io.BytesIO(files[name])))
        if task.truth == "effect":
            assert p < 0.01, (task.id, name, p)
        else:
            assert p > 0.3, (task.id, name, p)


def test_traps_in_the_null_tasks_are_real():
    """The null tasks are hard on purpose: the naive analysis finds an effect."""
    conf = pd.read_csv(io.BytesIO(by_id(["confounded_null"])[0].files()["train.csv"]))
    assert smf.ols("y ~ x", conf).fit().pvalues["x"] < 1e-6  # marginal association
    simp = pd.read_csv(io.BytesIO(by_id(["simpsons_null"])[0].files()["train.csv"]))
    assert smf.logit("admitted ~ C(group)", simp).fit(disp=0).pvalues.iloc[1] < 1e-6
    assert sum(t.truth == "null" for t in TASKS) > sum(
        t.truth == "effect" for t in TASKS
    )
    with pytest.raises(SystemExit):
        by_id(["nope"])


def _result(task, truth, verdicts, **kw):
    return TaskResult(
        task=task,
        truth=truth,
        status=kw.pop("status", "completed"),
        judgements=[{"finding": i, "verdict": v} for i, v in enumerate(verdicts)],
        **kw,
    )


def test_aggregate_breaches_and_report():
    results = [
        _result("e1", "effect", ["correct", "irrelevant"], allowance_tokens=400_000),
        _result("e2", "effect", [], unsupported_claim_rate=0.1),
        _result("n1", "null", ["incorrect"], unsupported_claim_rate=0.0),
        _result("n2", "null", [], status="halted"),
    ]
    s = aggregate(results, 0.5 / 1_000_000)
    assert s["finding_precision"] == 0.5 and s["verified_findings"] == 3
    assert s["effect_recall"] == 0.5 and s["null_false_positive_rate"] == 0.5
    assert s["false_positive_tasks"] == ["n1"] and s["completion_rate"] == 0.75
    assert s["mean_unsupported_claim_rate"] == 0.05 and s["cost_usd_upper_bound"] == 0.2
    problems = breaches(
        s,
        {
            "_comment": "ignored",
            "min_finding_precision": 0.8,
            "max_null_false_positive_rate": 0.5,
            "min_effect_recall": 0.5,
        },
    )
    assert problems == ["finding_precision = 0.5 is below 0.8"]
    # A metric that cannot be computed fails its threshold instead of passing silently.
    empty = aggregate([_result("n", "null", [])], 1e-6)
    assert empty["finding_precision"] is None
    assert "could not be computed" in breaches(empty, {"min_finding_precision": 0.8})[0]
    md = markdown(s, results, problems)
    assert "| n1 | null | completed | 0 / 1 / 0 |" in md and "below 0.8" in md


async def test_runner_scores_a_real_campaign_with_a_scripted_model(store):
    """run_task drives the real graph (fake model, real sandbox) and judges its findings."""
    from test_end_to_end import FakeModel, fake_checker, fake_retriever

    from evals.scientist import run as runner
    from plato.scientist.nodes import ScientistContext

    def make_context(s):
        return ScientistContext(
            store=s,
            model=FakeModel(s),
            retriever=fake_retriever,
            citation_checker=fake_checker,
        )

    class Judge:
        def __init__(self):
            self.prompts: list[str] = []

        async def structured(self, *, prompt, schema, **_):
            assert schema is Judgement
            self.prompts.append(prompt)
            return Judgement(
                judgements=[
                    {"finding_index": 0, "verdict": "correct", "rationale": "r"}
                ]
            )

    judge = Judge()
    task = by_id(["correlation_effect"])[
        0
    ]  # numeric x,y columns, as the fake code reads
    result = await runner.run_task(
        store,
        task,
        budget=1_000_000,
        rounds=1,
        workers=2,
        timeout=300,
        judge=judge,
        judge_campaign=uuid.uuid4(),
        make_context=make_context,
    )
    assert result.status == "completed", result
    assert result.findings and result.verdicts[0] == "correct"
    assert all(j["verdict"] == "incorrect" for j in result.judgements[1:])
    assert task.answer in judge.prompts[0]
    assert result.allowance_tokens > 0 and result.unsupported_claim_rate == 0.0
    json.dumps(result.__dict__, default=str)
