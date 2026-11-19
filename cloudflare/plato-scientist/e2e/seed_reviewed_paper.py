"""Local tests only: a finished research thread whose paper, claim-by-claim review and
revision check read like a real one (scripted model, no API calls). Prints its id.

Run: PLATO_DATABASE_URL=... python cloudflare/plato-scientist/e2e/seed_reviewed_paper.py <account id>
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tests" / "scientist")]
from test_end_to_end import FakeModel, fake_retriever

from plato.scientist.db.store import DualGraphStore
from plato.scientist.graph import run_campaign
from plato.scientist.nodes import ScientistContext
from plato.scientist.schemas import ClaimAssessment as A
from plato.scientist.schemas import Manuscript, PeerReview, RevisionCheck
from plato.scientist.schemas import RevisionOutcome as O

INTRO = (
    "Ordinary least squares (OLS) slope intervals assume homoscedastic Gaussian errors \\cite{%s}. "
    "When the error variance grows with the regressor, the nominal 95\\%% interval is known to under-cover. "
    "We ask how large that shortfall is at moderate sample sizes, and whether heteroscedasticity-consistent (HC3) "
    "standard errors restore coverage."
)
METHODS = (
    "We simulated $n \\in \\{50, 200, 1000\\}$ observations from $y = 1 + 2x + \\varepsilon$ with $x \\sim U(0, 1)$. "
    "Errors were either homoscedastic, $\\varepsilon \\sim N(0, 1)$, or heteroscedastic with standard deviation $0.5 + 2x$. "
    "Each configuration ran 20{,}000 replications across two independent seeds. "
    "Coverage is the fraction of replications whose 95\\% interval contains the true slope; equivalence to 0.95 was tested with TOST at a margin of 0.01."
)
RESULTS1 = (
    "Under homoscedastic errors the classical interval covered the true slope in 94.9\\% of replications (SE 0.0015, $n = 200$), "
    "statistically equivalent to the nominal level (TOST $p < 0.001$). "
    "Under heteroscedastic errors coverage fell to 91.2\\% (SE 0.0020) at $n = 200$, a shortfall of 3.8 percentage points that replicated across seeds. "
    "HC3 standard errors restored coverage to 94.7\\% (SE 0.0016). "
    "The shortfall did not shrink with sample size, which proves that the classical interval is never safe under heteroscedasticity."
)
RESULTS2 = RESULTS1.replace(
    "which proves that the classical interval is never safe under heteroscedasticity.",
    "so in these simulations larger samples did not remove the bias of the classical interval.",
)
DISC = (
    "Classical OLS intervals are reliable when the error variance is constant and should be replaced by HC3 intervals otherwise. "
    "HC3 is cheap to compute and lost no coverage in the homoscedastic case."
)
LIM = (
    "All experiments are computational and automated. We studied one data-generating process with a single linear heteroscedastic pattern; "
    "heavier tails, clustered errors and small samples below 50 were not examined."
)


class RichModel(FakeModel):
    revised = False

    async def structured(self, *, campaign_id, purpose, system, prompt, schema, **kw):
        if schema is Manuscript:
            await super().structured(
                campaign_id=campaign_id,
                purpose=purpose,
                system=system,
                prompt=prompt,
                schema=schema,
                **kw,
            )
            key = self.bib_keys[-1]
            rev = purpose == "manuscript_revision"
            return Manuscript(
                title="Heteroscedasticity and the coverage of OLS slope confidence intervals",
                abstract=(
                    "We measure how often the nominal 95\\% OLS slope interval contains the true slope when error variance grows with the regressor. "
                    "Coverage fell to 91.2\\% at $n = 200$ and HC3 standard errors restored it to 94.7\\%."
                    + (
                        ""
                        if rev
                        else " Our results show HC3 is optimal for every regression problem."
                    )
                ),
                introduction=INTRO % key,
                methods=METHODS,
                results=RESULTS2 if rev else RESULTS1,
                discussion=DISC,
                limitations=LIM,
            )
        if schema is PeerReview:
            await super().structured(
                campaign_id=campaign_id,
                purpose=purpose,
                system=system,
                prompt=prompt,
                schema=schema,
                **kw,
            )
            return PeerReview(
                summary="A clean, well-replicated simulation showing that classical OLS slope intervals under-cover under linear heteroscedasticity and that HC3 fixes it. Two conclusions overreach the single data-generating process studied.",
                strengths=[
                    "Pre-registered coverage metric with TOST equivalence testing at a stated margin.",
                    "Two independent seeds with 20,000 replications each; standard errors reported for every coverage estimate.",
                    "Negative result for the homoscedastic case reported alongside the positive one.",
                ],
                assessments=[
                    A(
                        section="results",
                        quote="Under heteroscedastic errors coverage fell to 91.2\\% (SE 0.0020) at $n = 200$, a shortfall of 3.8 percentage points that replicated across seeds.",
                        category="result",
                        verdict="approved",
                        severity="minor",
                        evidence="Verified finding: coverage_hetero = 0.912 (SE 0.0020), seed-2 replication 0.910, within 3 combined SE; skeptic confidence 0.92.",
                        critique="Number, uncertainty and replication all match the verified finding.",
                        fix="",
                    ),
                    A(
                        section="results",
                        quote="HC3 standard errors restored coverage to 94.7\\% (SE 0.0016).",
                        category="result",
                        verdict="approved",
                        severity="minor",
                        evidence="Verified finding: coverage_hc3 = 0.947 (SE 0.0016), replicated 0.948.",
                        critique="Matches the evidence.",
                        fix="",
                    ),
                    A(
                        section="results",
                        quote="Under homoscedastic errors the classical interval covered the true slope in 94.9\\% of replications (SE 0.0015, $n = 200$), statistically equivalent to the nominal level (TOST $p < 0.001$).",
                        category="statistics",
                        verdict="approved",
                        severity="minor",
                        evidence="Equivalence claim with TOST p = 0.0004 at margin 0.01; coverage_homo = 0.949.",
                        critique="Equivalence is shown with the right test, not inferred from a large p-value.",
                        fix="",
                    ),
                    A(
                        section="results",
                        quote="The shortfall did not shrink with sample size, which proves that the classical interval is never safe under heteroscedasticity.",
                        category="interpretation",
                        verdict="rejected",
                        severity="major",
                        evidence="Only n = 50, 200, 1000 and one variance pattern (sd = 0.5 + 2x) were simulated; shortfall 3.6, 3.8, 3.7 points.",
                        critique="Three sample sizes and one heteroscedastic pattern cannot prove a universal statement; 'proves' and 'never' are not supported.",
                        fix="Restrict the claim to the simulated designs and drop 'proves' and 'never'.",
                    ),
                    A(
                        section="abstract",
                        quote="Our results show HC3 is optimal for every regression problem.",
                        category="interpretation",
                        verdict="rejected",
                        severity="critical",
                        evidence="No other estimator (HC0-HC2, wild bootstrap) was compared and only one data-generating process was studied.",
                        critique="Optimality was never tested; the abstract claims far more than the experiments show.",
                        fix="Remove the sentence or replace it with the measured HC3 coverage.",
                    ),
                    A(
                        section="discussion",
                        quote="Classical OLS intervals are reliable when the error variance is constant and should be replaced by HC3 intervals otherwise.",
                        category="interpretation",
                        verdict="needs_revision",
                        severity="minor",
                        evidence="Supported for the simulated designs (coverage 94.9% vs 91.2%); untested for heavy tails or clustering, which the Limitations section notes.",
                        critique="Reasonable recommendation but stated without the scope of the evidence.",
                        fix="Add 'in the designs we simulated' and point to the Limitations.",
                    ),
                    A(
                        section="methods",
                        quote="Each configuration ran 20{,}000 replications across two independent seeds.",
                        category="reproducibility",
                        verdict="approved",
                        severity="minor",
                        evidence="Run logs show 2 x 10,000 replications per configuration; code and seeds are recorded.",
                        critique="Enough replications for a coverage SE near 0.0015.",
                        fix="",
                    ),
                ],
                soundness=3,
                presentation=3,
                contribution=2,
                decision="major_revision",
                required_changes=[
                    "Remove the claim that HC3 is optimal for every regression problem.",
                    "Replace 'proves ... never safe' with a statement limited to the simulated designs.",
                    "Scope the discussion's recommendation to the designs simulated.",
                ],
            )
        if schema is RevisionCheck:
            await super().structured(
                campaign_id=campaign_id,
                purpose=purpose,
                system=system,
                prompt=prompt,
                schema=schema,
                **kw,
            )
            return RevisionCheck(
                outcomes=[
                    O(
                        assessment=0,
                        status="resolved",
                        final_quote="Under heteroscedastic errors coverage fell to 91.2\\% (SE 0.0020) at $n = 200$, a shortfall of 3.8 percentage points that replicated across seeds.",
                        note="Unchanged; still matches the evidence.",
                    ),
                    O(
                        assessment=1,
                        status="resolved",
                        final_quote="HC3 standard errors restored coverage to 94.7\\% (SE 0.0016).",
                        note="Unchanged.",
                    ),
                    O(
                        assessment=2,
                        status="resolved",
                        final_quote="Under homoscedastic errors the classical interval covered the true slope in 94.9\\% of replications (SE 0.0015, $n = 200$), statistically equivalent to the nominal level (TOST $p < 0.001$).",
                        note="Unchanged.",
                    ),
                    O(
                        assessment=3,
                        status="resolved",
                        final_quote="The shortfall did not shrink with sample size, so in these simulations larger samples did not remove the bias of the classical interval.",
                        note="Now limited to the simulated designs.",
                    ),
                    O(
                        assessment=4,
                        status="removed",
                        final_quote="",
                        note="The optimality sentence was deleted from the abstract.",
                    ),
                    O(
                        assessment=5,
                        status="unresolved",
                        final_quote="Classical OLS intervals are reliable when the error variance is constant and should be replaced by HC3 intervals otherwise.",
                        note="The recommendation is still unscoped.",
                    ),
                    O(
                        assessment=6,
                        status="resolved",
                        final_quote="Each configuration ran 20{,}000 replications across two independent seeds.",
                        note="Unchanged.",
                    ),
                ],
                final_summary="The overreaching claims were removed or scoped; one recommendation in the discussion still lacks the scope of the evidence.",
                final_decision="minor_revision",
            )
        return await super().structured(
            campaign_id=campaign_id,
            purpose=purpose,
            system=system,
            prompt=prompt,
            schema=schema,
            **kw,
        )


async def main(account):
    store = await DualGraphStore.connect(os.environ["PLATO_DATABASE_URL"], max_size=10)
    try:
        program = await store.ensure_program("e2e", "E2E", "statistics")
        cid = await store.create_campaign(
            program,
            "Do OLS slope confidence intervals keep 95% coverage under heteroscedastic errors?",
            token_budget_max=1_000_000,
            config={"workers": 3, "max_rounds": 2},
            account_id=account,
        )
        train = await store.put_dataset(program, "train.csv", b"x,y\n1,2\n2,3\n3,4\n")
        await store.set_scope(cid, train.id, "train_val")
        ctx = ScientistContext(
            store=store, model=RichModel(store), retriever=fake_retriever
        )
        summary = await run_campaign(ctx, cid)
        assert summary["campaign"]["status"] == "completed", summary["campaign"][
            "status"
        ]
        print(cid)
    finally:
        await store.close()


asyncio.run(main(uuid.UUID(sys.argv[1])))
