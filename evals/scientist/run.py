"""Run the known-answer tasks through the real scientist and score them.

Real Claude calls (sub-agents on the configured models, Haiku 5.5 by default), real
literature APIs, the real sandbox, verification and review. Needs ``ANTHROPIC_API_KEY`` and
a Postgres DSN that may create databases; each run uses a fresh database::

    PLATO_TEST_POSTGRES_DSN=postgresql://postgres:pw@127.0.0.1:5432/postgres \\
      python -m evals.scientist.run --out evals/results/scientist

Writes ``summary.json``, ``results.json`` and ``summary.md`` to ``--out`` and exits 1 when
a threshold in ``thresholds.json`` is breached (``--no-fail`` reports only).
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg

from plato.scientist.db.store import DualGraphStore
from plato.scientist.graph import run_campaign
from plato.scientist.llm import AnthropicScientistModel
from plato.scientist.nodes import ScientistContext

from .score import (
    JUDGE_SYSTEM,
    Judgement,
    TaskResult,
    aggregate,
    breaches,
    judge_prompt,
    markdown,
)
from .tasks import Task, by_id

HERE = Path(__file__).parent
# Allowance tokens are Haiku 5.5-priced tokens ($0.10 in / $0.50 out per MTok, see
# plato/scientist/models.py); pricing all of them at the output rate bounds the cost.
USD_PER_ALLOWANCE_TOKEN = 0.50 / 1_000_000


def _production_context(store: DualGraphStore) -> ScientistContext:
    return ScientistContext(store=store, model=AnthropicScientistModel(store))


async def run_task(
    store: DualGraphStore,
    task: Task,
    *,
    budget: int,
    rounds: int,
    workers: int,
    timeout: float,
    judge: AnthropicScientistModel,
    judge_campaign: uuid.UUID,
    make_context: Callable[[DualGraphStore], ScientistContext] | None = None,
) -> TaskResult:
    started = time.monotonic()
    program = await store.ensure_program(f"eval-{task.id}", task.id, "statistics")
    cid = await store.create_campaign(
        program,
        task.question,
        token_budget_max=budget,
        gpu_seconds_max=7200,
        config={"workers": workers, "max_rounds": rounds, "domain": "general"},
    )
    files = task.files()
    train = await store.put_dataset(program, "train.csv", files["train.csv"])
    held = await store.put_dataset(
        program, "holdout.csv", files["holdout.csv"], is_sealed_eval=True
    )
    await store.set_scope(cid, train.id, "train_val")
    await store.set_scope(cid, held.id, "sealed_eval_only")
    result = TaskResult(task=task.id, truth=task.truth, status="error")
    try:
        ctx = (make_context or _production_context)(store)
        await asyncio.wait_for(run_campaign(ctx, cid), timeout)
    except TimeoutError:
        result.error = f"timed out after {timeout:.0f} s"
    except Exception as exc:  # noqa: BLE001 - one task's crash is a result, not the run's
        result.error = f"{type(exc).__name__}: {exc}"[:500]
    summary = await store.campaign_summary(cid)
    campaign = summary["campaign"]
    result.status = (
        campaign["status"] if result.error is None else f"{campaign['status']} (error)"
    )
    result.allowance_tokens = int(campaign["tokens_used"])
    result.facts = summary["nodes"].get("fact", {})
    result.findings = [
        {
            "title": f["title"],
            "statement": f["hypothesis_or_spec"],
            "metrics": f["metrics"],
        }
        for f in await store.nodes(cid, node_type="finding", status="verified")
    ]
    root = next(
        (
            g
            for g in await store.nodes(cid, node_type="goal")
            if g["dedup_key"] == "root-goal"
        ),
        None,
    )
    if root is not None:
        m = root["metrics"] or {}
        result.unsupported_claim_rate = m.get("unsupported_claim_rate")
        result.unsupported_claim_rate_before_removal = m.get(
            "unsupported_claim_rate_before_removal"
        )
        result.citations_removed = int(m.get("citations_removed") or 0)
        result.review_decision = m.get("review_decision")
    if result.findings:
        out = await judge.structured(
            campaign_id=judge_campaign,
            purpose="eval_judge",
            system=JUDGE_SYSTEM,
            prompt=judge_prompt(task, result.findings),
            schema=Judgement,
            effort="medium",
            max_tokens=4000,
        )
        by_index = {j.finding_index: j for j in out.judgements}
        # A finding the judge skipped counts as incorrect: unjudged is not a pass.
        result.judgements = [
            {
                "finding": i,
                "verdict": by_index[i].verdict if i in by_index else "incorrect",
                "rationale": by_index[i].rationale if i in by_index else "not judged",
            }
            for i in range(len(result.findings))
        ]
    result.seconds = round(time.monotonic() - started, 1)
    return result


def write_outputs(
    out: Path, summary: dict, results: list[TaskResult], problems: list[str]
) -> str:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out / "results.json").write_text(
        json.dumps([dataclasses.asdict(r) for r in results], indent=2, default=str)
        + "\n"
    )
    report = markdown(summary, results, problems)
    (out / "summary.md").write_text(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(report)
    return report


async def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tasks", nargs="*", help="task ids (default: all)")
    ap.add_argument(
        "--budget", type=int, default=600_000, help="allowance tokens per task"
    )
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--timeout-minutes", type=float, default=45)
    ap.add_argument(
        "--judge-model",
        default=os.environ.get("PLATO_EVAL_JUDGE_MODEL", "claude-sonnet-5-5"),
    )
    ap.add_argument("--thresholds", type=Path, default=HERE / "thresholds.json")
    ap.add_argument("--out", type=Path, default=Path("evals/results/scientist"))
    ap.add_argument("--no-fail", action="store_true")
    ap.add_argument("--keep-db", action="store_true")
    args = ap.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set", file=sys.stderr)
        return 2
    admin_dsn = os.environ.get("PLATO_TEST_POSTGRES_DSN") or os.environ.get(
        "PLATO_POSTGRES_DSN"
    )
    if not admin_dsn:
        print("PLATO_TEST_POSTGRES_DSN is not set", file=sys.stderr)
        return 2
    tasks = by_id(args.tasks)
    name = f"plato_eval_{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(admin_dsn)
    await admin.execute(f'CREATE DATABASE "{name}"')
    await admin.close()
    parts = urlsplit(admin_dsn)
    dsn = urlunsplit(
        (parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment)
    )
    store = await DualGraphStore.connect(dsn, max_size=10 + 4 * args.concurrency)
    try:
        judge_program = await store.ensure_program("eval-judge", "Judge", "general")
        judge_campaign = await store.create_campaign(
            judge_program,
            "Grade findings against known answers",
            token_budget_max=50_000_000,
        )
        judge = AnthropicScientistModel(
            store, model=args.judge_model, writing_reserve_tokens=0
        )
        sem = asyncio.Semaphore(args.concurrency)

        async def one(task: Task) -> TaskResult:
            async with sem:
                print(f"[eval] {task.id}: started", flush=True)
                r = await run_task(
                    store,
                    task,
                    budget=args.budget,
                    rounds=args.rounds,
                    workers=args.workers,
                    timeout=args.timeout_minutes * 60,
                    judge=judge,
                    judge_campaign=judge_campaign,
                )
                print(
                    f"[eval] {task.id}: {r.status}, verdicts {r.verdicts}", flush=True
                )
                return r

        results = list(await asyncio.gather(*(one(t) for t in tasks)))
        judge_tokens = int((await store.get_campaign(judge_campaign))["tokens_used"])
    finally:
        await store.close()
        if not args.keep_db:
            admin = await asyncpg.connect(admin_dsn)
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            await admin.close()

    summary = aggregate(results, USD_PER_ALLOWANCE_TOKEN)
    summary["judge_model"] = args.judge_model
    summary["judge_allowance_tokens"] = judge_tokens
    problems = breaches(summary, json.loads(args.thresholds.read_text()))
    summary["thresholds_breached"] = problems
    print(write_outputs(args.out, summary, results, problems))
    return 1 if problems and not args.no_fail else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
