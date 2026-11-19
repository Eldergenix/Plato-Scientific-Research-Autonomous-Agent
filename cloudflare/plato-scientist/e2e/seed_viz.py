#!/usr/bin/env python3
"""Seed a finished campaign whose experiments carry the real plato-lab outputs in
``e2e/fixtures/viz`` (made by ``scripts/e2b_viz_samples.py``), for the data viewer test.

It goes through the scientist's own store and the production ``store_outputs`` (the code
that records a run's files), so what the UI reads is exactly what a campaign would write:

    python e2e/seed_viz.py --dsn postgresql://postgres:postgres@127.0.0.1:5432/postgres --email ada@example.com

Prints the campaign id and the experiment ids as JSON. Local databases only.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from plato.scientist.db.store import DualGraphStore
from plato.scientist.nodes import recipe_as_patch, store_outputs

FIXTURES = HERE / "fixtures" / "viz"


def _recipes() -> dict[str, dict[str, str]]:
    spec = importlib.util.spec_from_file_location(
        "viz_samples", ROOT / "scripts" / "e2b_viz_samples.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.RECIPES


# recipe -> (experiment title, spec, claim title, primary metric, gates, finding title or None)
PLAN = {
    "proteomics": (
        "Which proteins does linear Ubi4 enrich over control in label-free pull-downs?",
        {
            "hypothesis": "Linear tetra-ubiquitin (Ubi4) pulls down ubiquitin-binding proteins that the control does not.",
            "protocol": "Welch t-tests on log2 LFQ intensities (UbiLength, 3 replicates each), Benjamini-Hochberg FDR; volcano table and plot.",
            "primary_metric": "n_significant",
            "test_kind": "difference",
            "success_criterion": "At least one protein significant at 5% FDR with |log2FC| > 1.",
        },
        "Four proteins, led by SQSTM1, are enriched by Ubi4 at 5% FDR",
        "n_significant",
        {"replicated": True, "stats_ok": True, "figures_ok": True, "skeptic": True},
        "SQSTM1 is the strongest Ubi4 interactor (log2FC 4.44)",
    ),
    "pathways": (
        "Are cell-cycle programmes over-represented among the strongly changed breast-cancer genes?",
        {
            "hypothesis": "Genes with |log2FC| > 2 in DOSE's breast-cancer list are enriched for chromosome segregation and cell-cycle terms.",
            "protocol": "clusterProfiler enrichGO (BP, org.Hs.eg.db, BH) and the KEGG hsa04110 pathway coloured by fold change.",
            "primary_metric": "go_terms",
            "test_kind": "difference",
            "success_criterion": "Adjusted p < 0.01 for at least one cell-cycle term.",
        },
        "Chromosome segregation terms dominate the enrichment (adjusted p 2.9e-21)",
        "go_terms",
        {"replicated": True, "stats_ok": True, "figures_ok": True, "skeptic": True},
        "Strongly changed genes are enriched for nuclear chromosome segregation",
    ),
    "structures": (
        "How compact is ubiquitin compared with its Calpha contact density?",
        {
            "hypothesis": "Ubiquitin (1UBQ) is a compact globule with a radius of gyration near 11.5 A.",
            "protocol": "Biopython on RCSB 1UBQ and 4HHB: clean structures, radius of gyration, Calpha contacts under 8 A.",
            "primary_metric": "radius_of_gyration",
            "test_kind": "equivalence",
            "success_criterion": "Radius of gyration within 0.5 A of 11.5 A.",
        },
        "Ubiquitin's radius of gyration is 11.49 A with 177 Calpha contacts",
        "radius_of_gyration",
        {"replicated": True, "stats_ok": False, "figures_ok": True, "skeptic": True},
        None,
    ),
    "ligands": (
        "Do aspirin, ibuprofen and caffeine all fall inside Lipinski's rule of five?",
        {
            "hypothesis": "All three molecules satisfy the rule of five (MW < 500, logP < 5, HBD <= 5, HBA <= 10).",
            "protocol": "RDKit 3D embedding with MMFF optimisation; descriptors per molecule.",
            "primary_metric": "mean_mol_weight",
            "test_kind": "difference",
            "success_criterion": "Every molecule passes all four rules.",
        },
        "All three molecules pass the rule of five (mean MW 193.5)",
        "mean_mol_weight",
        None,
        None,
    ),
}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True)
    ap.add_argument(
        "--email",
        required=True,
        help="the account that owns the campaign (sign up first)",
    )
    args = ap.parse_args()
    store = await DualGraphStore.connect(args.dsn, max_size=4)
    recipes = _recipes()
    try:
        account = await store._pool.fetchval(
            "SELECT id FROM plato.accounts WHERE lower(email) = lower($1)", args.email
        )
        if account is None:
            raise SystemExit(f"no account {args.email}: sign up first")
        program = await store.ensure_program("default", "Plato", "biology")
        cid = await store.create_campaign(
            program,
            "What do real proteomics, pathway, structure and ligand analyses show when run in the lab sandbox?",
            token_budget_max=2_000_000,
            config={
                "model": "claude-haiku-5-5",
                "workers": 4,
                "max_rounds": 1,
                "executor": "e2b",
                "domain": "biology",
            },
            account_id=account,
        )
        root = await store.create_node(
            cid, "goal", "Research question", "", dedup_key="root-goal"
        )
        out = {"campaign": str(cid), "experiments": {}, "files": {}}
        for name, (title, spec, claim, pk, gates, finding_title) in PLAN.items():
            manifest = json.loads((FIXTURES / name / "manifest.json").read_text())
            intent = await store.create_node(
                cid,
                "intent",
                title,
                json.dumps(spec),
                dedup_key=f"viz-{name}",
                priority=1.0,
            )
            await store.add_edge(cid, root.id, intent.id, "spawns", "planned")
            worker = f"seed-{uuid.uuid4().hex[:6]}"
            claimed = await store.claim_next_intent(cid, worker)
            assert claimed and claimed["id"] == intent.id, (
                "seed expects to claim the intent it just made"
            )
            metrics = {
                **manifest["metrics"],
                "seed": 1,
                "primary_metric": pk,
                "test_kind": spec["test_kind"],
                "runtime_seconds": manifest["seconds"],
                "network_isolated": manifest["network_isolated"],
                "executor": "e2b",
            }
            if gates is not None:
                metrics["gates"] = gates
                metrics["replication"] = {pk: manifest["metrics"][pk]}
            fact = await store.record_fact(
                cid,
                intent.id,
                worker,
                title=claim,
                observation=manifest["stdout_tail"].strip().splitlines()[0],
                metrics=metrics,
                confidence_score=0.9 if gates and all(gates.values()) else 0.6,
            )
            r = recipes[name]
            await store.add_evidence(
                fact,
                "git_patch",
                recipe_as_patch(r["code"], r["setup"]),
                approval_actor="model",
            )
            await store.add_evidence(
                fact, "stdout_log", manifest["stdout_tail"], approval_actor="system"
            )
            files = {
                p.name: p.read_bytes()
                for p in sorted((FIXTURES / name).iterdir())
                if p.name != "manifest.json"
            }
            await store_outputs(store, fact, files)
            await store.complete_intent(
                intent.id, worker, "verified", metrics={"fact_id": str(fact)}
            )
            if gates is not None:
                ok = all(gates.values())
                await store.set_node_status(fact, "verified" if ok else "refuted")
                if ok and finding_title:
                    f = await store.create_node(
                        cid,
                        "finding",
                        finding_title,
                        claim,
                        metrics={**gates, "primary_metric": pk},
                        confidence_score=0.9,
                        status="verified",
                    )
                    await store.add_edge(cid, fact, f.id, "proves", "all checks passed")
            out["experiments"][name] = str(intent.id)
        # one experiment still running and one that ran out of attempts, for the workflow states
        run = await store.create_node(
            cid,
            "intent",
            "Does SQSTM1 binding depend on chain length?",
            json.dumps(
                {
                    "hypothesis": "Longer linear chains bind SQSTM1 more strongly.",
                    "primary_metric": "log2fc_slope",
                    "test_kind": "difference",
                }
            ),
            dedup_key="viz-running",
            priority=0.5,
        )
        await store.add_edge(cid, root.id, run.id, "spawns", "planned")
        await store.claim_next_intent(cid, "seed-running")
        dead = await store.create_node(
            cid,
            "intent",
            "Dock caffeine into the adenosine A2A receptor",
            json.dumps(
                {
                    "hypothesis": "Caffeine docks into A2A with a score below -7 kcal/mol.",
                    "primary_metric": "dock_score",
                    "test_kind": "difference",
                }
            ),
            dedup_key="viz-dead",
            status="exhausted",
            metrics={"error": "no successful run", "attempts": 3},
        )
        await store.add_edge(cid, root.id, dead.id, "spawns", "planned")
        # a queued experiment stored with the exact text of a real intent the app once showed
        # as raw JSON (tests/scientist/fixtures/intent_design.json)
        design = await store.create_node(
            cid,
            "intent",
            "Does omitting pathology bias the age interaction?",
            (ROOT / "tests" / "scientist" / "fixtures" / "intent_design.json")
            .read_text()
            .strip(),
            dedup_key="viz-design",
            priority=0.1,
        )
        await store.add_edge(cid, root.id, design.id, "spawns", "planned")
        out["experiments"]["design"] = str(design.id)
        for status in (
            "investigating",
            "ablating",
            "sealed_eval",
            "writing",
            "completed",
        ):
            await store.transition_campaign(cid, status)
        rows = await store._pool.fetch(
            "SELECT e.id, e.file_name, e.artifact_type FROM plato.evidence_artifacts e JOIN plato.exploration_nodes n ON n.id = e.node_id"
            " WHERE n.campaign_id = $1 AND e.artifact_type IN ('plot_png', 'data_file') ORDER BY e.file_name",
            cid,
        )
        out["files"] = {r["file_name"]: str(r["id"]) for r in rows}
        print(json.dumps(out))
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(main())
