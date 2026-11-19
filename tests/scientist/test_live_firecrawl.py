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
