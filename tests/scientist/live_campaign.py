"""Run one real campaign end to end and report what each library tool did.

Real Claude Haiku calls, real literature APIs, real Crossref/doi.org/arXiv checks and the
real sandbox. Needs ANTHROPIC_API_KEY and a Postgres DSN that may create databases::

    PLATO_TEST_POSTGRES_DSN=postgresql://postgres:pw@127.0.0.1:5432/postgres \\
      python -m tests.scientist.live_campaign --domain biology

Exits non-zero if the campaign does not complete or a library tool left no receipt.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import json
import os
import sys
import uuid
from urllib.parse import urlsplit, urlunsplit

import asyncpg

from plato.scientist.db.store import DualGraphStore
from plato.scientist.graph import run_campaign
from plato.scientist.llm import AnthropicScientistModel
from plato.scientist.nodes import ScientistContext

QUESTIONS = {
    "biology": (
        "In a simulated RNA-seq differential expression study with 2000 genes, 10% truly "
        "differentially expressed and 4 samples per group, does the Benjamini-Hochberg "
        "procedure applied to Welch t-test p-values keep the false discovery rate at or "
        "below the nominal 5%?"
    ),
    "general": (
        "Do HC3 heteroskedasticity-robust 95% confidence intervals for an OLS slope keep "
        "their nominal coverage at n=30 when the noise variance grows with x?"
    ),
    "astro": (
        "How does the detection rate of a box least squares search for simulated exoplanet "
        "transits fall as transit depth approaches the photometric noise level?"
    ),
}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="biology", choices=sorted(QUESTIONS))
    ap.add_argument("--budget", type=int, default=900_000)
    ap.add_argument("--keep-db", action="store_true")
    args = ap.parse_args()

    admin_dsn = os.environ["PLATO_TEST_POSTGRES_DSN"]
    name = f"plato_live_{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(admin_dsn)
    await admin.execute(f'CREATE DATABASE "{name}"')
    await admin.close()
    parts = urlsplit(admin_dsn)
    dsn = urlunsplit(
        (parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment)
    )
    store = await DualGraphStore.connect(dsn, max_size=12)
    try:
        program = await store.ensure_program(f"live-{args.domain}", "Live", "general")
        cid = await store.create_campaign(
            program,
            QUESTIONS[args.domain],
            token_budget_max=args.budget,
            gpu_seconds_max=3600,
            # The agent passes the domain like this; the program's own domain is "general".
            config={"workers": 2, "max_rounds": 1, "domain": args.domain},
        )
        ctx = ScientistContext(store=store, model=AnthropicScientistModel(store))
        summary = await run_campaign(ctx, cid)
        campaign = summary["campaign"]
        root = next(
            g
            for g in await store.nodes(cid, node_type="goal")
            if g["dedup_key"] == "root-goal"
        )
        receipts = {
            e["artifact_type"]: e for e in await store.evidence_for([root["id"]])
        }

        async def receipt(kind: str):
            if kind not in receipts:
                return None
            return json.loads(await store.evidence_content(receipts[kind]["id"]))

        papers = await store.pool.fetch(
            "SELECT metadata FROM plato.knowledge_assets WHERE program_id=$1 AND asset_type='paper'",
            program,
        )
        metas = [
            json.loads(p["metadata"])
            if isinstance(p["metadata"], str)
            else p["metadata"]
            for p in papers
        ]
        matrix, panel, report = (
            await receipt("evidence_matrix"),
            await receipt("review_panel"),
            await receipt("citation_report"),
        )
        review = await receipt("peer_review")
        out = {
            "status": campaign["status"],
            "halted_reason": campaign.get("halted_reason"),
            "tokens_used": campaign["tokens_used"],
            "profile": root["metrics"].get("profile"),
            "sources_searched": root["metrics"].get("retrieval_sources"),
            "papers_by_source": dict(
                collections.Counter(m.get("retrieved_via") for m in metas)
            ),
            "citation_checks": root["metrics"].get("citation_checks"),
            "papers_excluded": root["metrics"].get("papers_excluded"),
            "findings": root["metrics"].get("findings"),
            "review_decision": review and review.get("decision"),
            "revised": root["metrics"].get("revised"),
            "panel": panel
            and {
                a: r.get("severity", r.get("error"))
                for a, r in panel["reviewers"].items()
            },
            "matrix": matrix
            and {
                "claims": len(matrix["claims"]),
                "supported": matrix["supported_claims"],
                "unsupported_claim_rate": matrix["unsupported_claim_rate"],
                "example": matrix["claims"][0] if matrix["claims"] else None,
            },
            "citation_report": report
            and {
                "cited_by_status": report["cited_by_status"],
                "cited": len(report["cited"]),
            },
            "receipts": sorted(receipts),
        }
        print(json.dumps(out, indent=2, default=str))
        missing = {
            "latex_section",
            "evidence_matrix",
            "review_panel",
            "citation_report",
        } - set(receipts)
        ok = campaign["status"] == "completed" and not missing
        if missing:
            print("MISSING RECEIPTS:", sorted(missing), file=sys.stderr)
        return 0 if ok else 1
    finally:
        await store.close()
        if not args.keep_db:
            admin = await asyncpg.connect(admin_dsn)
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            await admin.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
