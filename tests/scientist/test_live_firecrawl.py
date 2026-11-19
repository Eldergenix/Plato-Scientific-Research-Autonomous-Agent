"""Live checks against the real Firecrawl API (opt-in: PLATO_LIVE=1 and FIRECRAWL_API_KEY).

    PLATO_LIVE=1 FIRECRAWL_API_KEY=... PYTHONPATH=. pytest tests/scientist/test_live_firecrawl.py \
        -q -s --confcutdir=tests/scientist

Checks that every endpoint the scientist uses answers in the shape the client expects, and
measures what each group costs from the team's remaining credits (Firecrawl may settle
usage with a delay, so the free-endpoint check reads the balance after a pause).
"""

from __future__ import annotations

import asyncio
import os

import pytest

from plato.retrieval.firecrawl import FirecrawlClient
from plato.retrieval.sources.firecrawl_research import FirecrawlResearchAdapter

pytestmark = pytest.mark.skipif(
    not (os.environ.get("PLATO_LIVE") and os.environ.get("FIRECRAWL_API_KEY")),
    reason="set PLATO_LIVE=1 and FIRECRAWL_API_KEY",
)


async def remaining(fc: FirecrawlClient) -> float:
    body = await fc._request("GET", "/team/credit-usage")
    data = body.get("data") or body
    return float(data.get("remainingCredits", data.get("remaining_credits")))


async def test_research_index_endpoints_are_live_and_free():
    async with FirecrawlClient() as fc:
        before = await remaining(fc)
        papers = await fc.search_papers("tau aggregation inhibitors Alzheimer", k=3)
        assert papers and all(p["title"] and p["abstract"] for p in papers)
        pid = papers[0]["paperId"]
        meta = await fc.get_paper(pid)
        assert meta["paper"]["title"]
        read = await fc.get_paper(pid, query="primary outcome", k=2)
        assert isinstance(read["passages"], list)
        related = await fc.related_papers(pid, "replication in larger cohorts", k=3)
        assert isinstance(related["results"], list)
        protein = await fc.protein("RPUSD3", organism="9606")
        assert protein["match"] in ("found", "ambiguous", "not_found")
        sources = await FirecrawlResearchAdapter(client=fc).search(
            "single-cell eQTL age interaction", 3
        )
        assert sources and all(s.abstract for s in sources)
        await asyncio.sleep(20)
        after = await remaining(fc)
    print(
        f"\nResearch Index: {len(papers)} papers, protein {protein['match']}, "
        f"credits {before} -> {after}"
    )
    assert after == before


async def test_billed_endpoints_report_their_cost():
    async with FirecrawlClient() as fc:
        before = await remaining(fc)
        web = await fc.search("Braak stage prevalence by age brain bank", limit=3)
        assert web.body["data"]["web"]
        page = await fc.scrape(web.body["data"]["web"][0]["url"])
        assert page.body["data"].get("markdown") is not None
        dev = await fc.developer_search("statsmodels mixedlm interaction term", k=2)
        assert isinstance(dev["results"], list)
        tools = await fc.search(
            "US population by age", limit=3, sources=["alexandria"], tool_detail="full"
        )
        await asyncio.sleep(20)
        after = await remaining(fc)
    print(
        f"\nweb search credits={web.credits} (reported={web.reported}); scrape "
        f"credits={page.credits} (reported={page.reported}); developer creditsUsed="
        f"{dev.get('creditsUsed')}; alexandria tools={len(tools.body['data'].get('tools') or [])} "
        f"creditsUsed={tools.body.get('creditsUsed')}; balance {before} -> {after} "
        f"(delta {before - after})"
    )


class _Ledger:
    """Budget stand-in: records reservations and settlements instead of using Postgres."""

    def __init__(self):
        self.reserved = 0
        self.settled = 0

    async def reserve_tokens(self, campaign_id, tokens, *, keep_free=0):
        self.reserved += tokens

    async def settle_tokens(self, campaign_id, reserved, actual):
        self.settled += actual


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY"
)
async def test_live_deep_research_session_with_haiku():
    """The real sub-agent (Claude Haiku 5.5) on a real need, against the real Firecrawl."""
    import uuid

    from plato.scientist.deep_research import (
        SYSTEM,
        CreditMeter,
        ResearchLimits,
        ResearchTools,
        run_research,
    )
    from plato.scientist.guard import framing_instructions, new_nonce
    from plato.scientist.llm import AnthropicScientistModel

    ledger = _Ledger()
    model = AnthropicScientistModel(ledger, writing_reserve_tokens=0)
    cid = uuid.uuid4()
    limits = ResearchLimits(max_turns=8, max_credits=6)
    nonce = new_nonce()
    async with FirecrawlClient() as fc:
        meter = CreditMeter(
            ledger, cid, tokens_per_credit=50_000, cap=limits.max_credits
        )
        tools = ResearchTools(fc, meter, limits)
        outcome = await run_research(
            model=model,
            campaign_id=cid,
            task=(
                "Planned experiment: simulate 400 brain donors (ages top-coded at 90) where "
                "a binary neuropathology covariate becomes more prevalent with age.\n"
                "Find: 1. the prevalence of Alzheimer's disease neuropathologic change by age "
                "decade in brain-bank or community autopsy cohorts; 2. typical post-mortem "
                "interval (PMI) ranges in brain banks."
            ),
            tools=tools,
            nonce=nonce,
            system=framing_instructions(nonce) + " " + SYSTEM,
            limits=limits,
        )
    print(
        f"\nend={outcome.reason} turns={outcome.turns} credits={outcome.credits} "
        f"model tokens settled={ledger.settled - meter.tokens(outcome.credits)} "
        f"signals={sorted(set(outcome.signals))}"
    )
    if outcome.brief:
        print(outcome.brief.model_dump_json(indent=2))
        print({k: (v.kind, v.title, v.url) for k, v in outcome.cited().items()})
    assert outcome.reason == "finished" and outcome.brief is not None
    assert outcome.brief.findings and all(f.sources for f in outcome.brief.findings)
    assert outcome.credits <= limits.max_credits
