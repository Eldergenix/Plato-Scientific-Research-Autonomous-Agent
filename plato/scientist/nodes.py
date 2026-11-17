"""Graph-driven scientist nodes.

Each node reads and writes the dual graph in Postgres; LangGraph state carries only the
campaign id and loop counters. That makes every node resumable: if a container dies, the
next run re-derives where it was from the campaign status and node statuses.

Edge direction convention: edges always point from ancestor to descendant
(``goal -spawns-> intent``, ``hint -derived_from-> intent``, ``intent -yields-> fact``,
``fact -proves-> finding``), so provenance is a backwards walk over ``target_node_id``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import socket
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .db.store import (
    BudgetExceeded,
    DualGraphStore,
    LeaseLost,
    paper_dedup_key,
    sha256_hex,
    spec_dedup_key,
)
from .guard import SandboxLimits, SandboxResult, frame_untrusted, framing_instructions, new_nonce, run_python
from .llm import ModelOutputError, ModelRefusal, ScientistModel
from .schemas import (
    ExperimentCode,
    FigureCritique,
    IntentBatch,
    LiteratureHints,
    Manuscript,
    Observation,
    PeerReview,
    ResearchPlan,
    SkepticVerdict,
)

logger = logging.getLogger(__name__)

METRICS_MARKER = "PLATO_METRICS"
SEED_FILE = "plato_seed.txt"
SEALED_MANIFEST = "plato_sealed.json"
ROOT_GOAL_KEY = "root-goal"

Retriever = Callable[[str, int], Awaitable[list[Any]]]


async def default_retriever(query: str, limit: int) -> list[Any]:
    from plato.retrieval.orchestrator import retrieve

    return await retrieve(query, limit, adapter_names=["arxiv", "openalex", "semantic_scholar"])


@dataclass
class ScientistConfig:
    workers: int = 4
    max_rounds: int = 3
    intents_per_round: int = 4
    papers_per_query: int = 6
    max_code_attempts: int = 3
    lease_seconds: int = 900
    max_claim_attempts: int = 3
    replication_rel_tolerance: float = 0.10
    min_promote_confidence: float = 0.6
    min_figure_score: float = 0.5
    require_network_isolation: bool = False
    sandbox: SandboxLimits = field(default_factory=SandboxLimits)

    @classmethod
    def from_campaign(cls, config: dict[str, Any] | None) -> "ScientistConfig":
        cfg = cls()
        for key, value in (config or {}).items():
            if key != "sandbox" and hasattr(cfg, key):
                setattr(cfg, key, type(getattr(cfg, key))(value))
        return cfg


@dataclass
class ScientistContext:
    store: DualGraphStore
    model: ScientistModel
    config: ScientistConfig = field(default_factory=ScientistConfig)
    retriever: Retriever = default_retriever
    worker_prefix: str = field(default_factory=lambda: f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_metrics(stdout: str) -> dict[str, Any] | None:
    """Metrics are reported by the experiment, never inferred by the model: the last line
    starting with ``PLATO_METRICS`` must carry a JSON object of numbers."""
    for line in reversed(stdout.splitlines()):
        if line.startswith(METRICS_MARKER):
            try:
                value = json.loads(line[len(METRICS_MARKER):].strip())
            except json.JSONDecodeError:
                return None
            if isinstance(value, dict) and value and all(
                isinstance(v, (int, float)) and not isinstance(v, bool) for v in value.values()
            ):
                return value
            return None
    return None


def code_as_patch(code: str) -> str:
    lines = code.splitlines()
    body = "\n".join(f"+{line}" for line in lines)
    return f"--- /dev/null\n+++ b/experiment.py\n@@ -0,0 +1,{len(lines)} @@\n{body}\n"


def code_from_patch(patch: str) -> str:
    return "\n".join(line[1:] for line in patch.splitlines()[3:] if line.startswith("+"))


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def metrics_agree(a: float, b: float, rel_tol: float) -> bool:
    if a == b:
        return True
    scale = max(abs(a), abs(b))
    return scale > 0 and abs(a - b) / scale <= rel_tol


async def _guarded(ctx: ScientistContext, campaign_id: uuid.UUID, framed_sources: list) -> None:
    """Record any prompt-injection signals seen in untrusted text (allowed but flagged)."""
    for framed in framed_sources:
        if framed.injection_signals:
            await ctx.store.record_guard_event(
                campaign_id, "injection", "allow",
                {"signals": list(framed.injection_signals), "note": "framed as untrusted"},
            )


def _system(role: str, nonce: str) -> str:
    return (
        f"You are the {role} in an autonomous research team. Be precise, quantitative and honest "
        "about uncertainty; never invent results, citations or numbers. "
        + framing_instructions(nonce)
    )


async def _root_goal(ctx: ScientistContext, campaign_id: uuid.UUID) -> uuid.UUID:
    campaign = await ctx.store.get_campaign(campaign_id)
    root = await ctx.store.create_node(
        campaign_id, "goal", "Research question", campaign["research_question"],
        dedup_key=ROOT_GOAL_KEY, priority=1.0,
    )
    return root.id


# ---------------------------------------------------------------------------
# 1. Literature scout: question -> goals, papers (knowledge assets), hints
# ---------------------------------------------------------------------------

async def literature_scout(ctx: ScientistContext, campaign_id: uuid.UUID) -> None:
    store = ctx.store
    campaign = await store.get_campaign(campaign_id)
    if campaign["status"] != "ideation":
        return
    nonce = new_nonce()
    root_id = await _root_goal(ctx, campaign_id)
    question = frame_untrusted(campaign["research_question"], source="operator_topic", nonce=nonce)

    plan = await ctx.model.structured(
        campaign_id=campaign_id, purpose="plan", schema=ResearchPlan, effort="medium",
        system=_system("principal investigator", nonce),
        prompt=(
            "Turn this topic into a precise research plan that can be investigated with "
            "computational experiments (simulation, analysis of provided data, or "
            "re-implementation of published methods) inside an offline Python sandbox.\n\n"
            f"{question.text}"
        ),
    )
    await store.set_node_status(root_id, "open", metrics={"refined_question": plan.refined_question,
                                                         "domain": plan.domain})
    goal_ids = []
    for goal in plan.goals[:4]:
        node = await store.create_node(campaign_id, "goal", goal.title, goal.objective,
                                       dedup_key=spec_dedup_key(goal.title), priority=0.8)
        await store.add_edge(campaign_id, root_id, node.id, "spawns", "plan decomposition")
        goal_ids.append(node.id)

    # Literature -> knowledge assets (deduplicated across all campaigns of the program).
    domain_asset = await store.upsert_asset(campaign["program_id"], "corpus_domain",
                                            f"domain:{plan.domain}", plan.domain)
    papers: list[tuple[uuid.UUID, Any]] = []
    seen: set[uuid.UUID] = set()
    for query in plan.search_queries[:4]:
        try:
            results = await ctx.retriever(query, ctx.config.papers_per_query)
        except Exception as exc:  # one failed source must not stop the campaign
            logger.warning("retrieval failed for %r: %s", query, exc)
            results = []
        for src in results:
            try:
                key = paper_dedup_key(doi=src.doi, arxiv_id=src.arxiv_id, title=src.title, year=src.year)
            except ValueError:
                continue
            asset = await store.upsert_asset(
                campaign["program_id"], "paper", key, src.title[:500],
                uri_or_commit=src.url or (f"https://doi.org/{src.doi}" if src.doi else None),
                parent_id=domain_asset.id,
                metadata={"title": src.title, "authors": list(src.authors)[:20], "year": src.year,
                          "venue": src.venue, "doi": src.doi, "arxiv_id": src.arxiv_id,
                          "abstract": (src.abstract or "")[:3000], "query": query},
            )
            if asset.id not in seen:
                seen.add(asset.id)
                papers.append((asset.id, src))
                await store.set_scope(campaign_id, asset.id, "read_only")
    await store.set_node_status(root_id, "open", metrics={"papers_found": len(papers)})

    framed_papers = [
        frame_untrusted(f"[{i}] {src.title} ({src.year})\n{(src.abstract or '')[:1500]}",
                        source=f"paper_{i}", nonce=nonce)
        for i, (_, src) in enumerate(papers)
    ]
    await _guarded(ctx, campaign_id, framed_papers)
    literature = "\n".join(f.text for f in framed_papers) or "(no literature could be retrieved)"
    hints = await ctx.model.structured(
        campaign_id=campaign_id, purpose="hints", schema=LiteratureHints, effort="medium",
        system=_system("literature analyst", nonce),
        prompt=(
            f"Research question: {plan.refined_question}\n\nPapers:\n{literature}\n\n"
            "List up to 5 unexplored directions, gaps or contradictions that a computational "
            "experiment could test. Cite paper indices; use an empty list when none apply."
        ),
    )
    for hint in hints.hints[:5]:
        node = await store.create_node(campaign_id, "hint", hint.title, hint.rationale,
                                       dedup_key=spec_dedup_key(hint.title), priority=0.5)
        await store.add_edge(campaign_id, root_id, node.id, "spawns", "literature gap")
        for idx in hint.cited_papers:
            if 0 <= idx < len(papers):
                await store.link_anchor(node.id, papers[idx][0], "cited_prior_work")
    await store.transition_campaign(campaign_id, "investigating", from_statuses=["ideation"])


# ---------------------------------------------------------------------------
# 2. Experiment planner: uncovered scope + hints + facts -> intents (tree expansion)
# ---------------------------------------------------------------------------

async def experiment_planner(ctx: ScientistContext, campaign_id: uuid.UUID, round_no: int) -> int:
    store = ctx.store
    campaign = await store.get_campaign(campaign_id)
    nonce = new_nonce()
    goals = [g for g in await store.nodes(campaign_id, node_type="goal") if g["dedup_key"] != ROOT_GOAL_KEY]
    hints = await store.nodes(campaign_id, node_type="hint", status="open")
    facts = await store.nodes(campaign_id, node_type="fact")
    existing = await store.nodes(campaign_id, node_type="intent")
    datasets = await store.visible_assets(campaign_id, asset_types=["dataset"])
    uncovered = await store.query_uncovered_scope(campaign_id)

    framed = [frame_untrusted(f"[{i}] {h['title']}: {h['hypothesis_or_spec']}", source=f"hint_{i}", nonce=nonce)
              for i, h in enumerate(hints)]
    fact_lines = "\n".join(
        f"- ({f['status']}) {f['title']}: {json.dumps(f['metrics'])[:300]}" for f in facts[-20:]
    ) or "(none yet)"
    prompt = (
        f"Research question: {campaign['research_question']}\n"
        f"Round {round_no + 1} of {ctx.config.max_rounds}.\n\n"
        "Goals:\n" + "\n".join(f"[{i}] {g['title']}: {g['hypothesis_or_spec']}" for i, g in enumerate(goals))
        + "\n\nOpen hints:\n" + ("\n".join(f.text for f in framed) or "(none)")
        + f"\n\nFacts so far:\n{fact_lines}\n\n"
        + "Experiments already planned (do not repeat):\n"
        + ("\n".join(f"- {i['title']}" for i in existing) or "(none)")
        + "\n\nDatasets available in the sandbox:\n"
        + ("\n".join(f"- {d['metadata'].get('file_name')}: {d['metadata'].get('description', '')}" for d in datasets)
           or "(none: design simulations or analyses that generate their own data)")
        + f"\n\nPapers not yet used by any experiment: {len(uncovered)}\n\n"
        f"Propose up to {ctx.config.intents_per_round} new, independent computational experiments. "
        "Prefer experiments that resolve open hints or follow up surprising facts. Each must run "
        "offline in under two minutes with numpy/scipy/pandas/scikit-learn/matplotlib."
    )
    await _guarded(ctx, campaign_id, framed)
    batch = await ctx.model.structured(
        campaign_id=campaign_id, purpose="plan_intents", schema=IntentBatch, effort="medium",
        system=_system("experiment planner", nonce), prompt=prompt,
    )
    created = 0
    for spec in batch.intents[: ctx.config.intents_per_round]:
        # Progressive tree search: follow-ups of observed facts rank above fresh ideas.
        bonus = 0.2 if spec.source_hint_index is not None else 0.0
        priority = _clamp01(spec.priority) + bonus
        node = await store.create_node(
            campaign_id, "intent", spec.title,
            json.dumps({"hypothesis": spec.hypothesis, "protocol": spec.protocol,
                        "primary_metric": spec.primary_metric,
                        "success_criterion": spec.success_criterion}),
            dedup_key=spec_dedup_key(spec.hypothesis, spec.protocol), priority=priority,
            turn_budget_max=ctx.config.max_code_attempts * 2,
        )
        if not node.created:
            continue
        created += 1
        if 0 <= spec.goal_index < len(goals):
            await store.add_edge(campaign_id, goals[spec.goal_index]["id"], node.id, "spawns")
        if spec.source_hint_index is not None and 0 <= spec.source_hint_index < len(hints):
            hint = hints[spec.source_hint_index]
            await store.add_edge(campaign_id, hint["id"], node.id, "derived_from")
            await store.set_node_status(hint["id"], "exhausted")
        for d in datasets:
            await store.link_anchor(node.id, d["id"], "dataset_input")
    return created


# ---------------------------------------------------------------------------
# 3. Sandboxed experimenter swarm
# ---------------------------------------------------------------------------

_CODE_RULES = (
    "Rules for the script: it runs offline with numpy, scipy, pandas, scikit-learn and "
    f"matplotlib; it must read an integer seed from the file '{SEED_FILE}' and seed every RNG "
    "with it; it may read the provided dataset files from the working directory; it may save "
    "figures as PNG in the working directory; it must finish in under two minutes; its last "
    f"line of output must be '{METRICS_MARKER} ' followed by a JSON object of numeric metrics "
    "that includes the primary metric (and p_value when a statistical test is performed). "
    f"If a file named '{SEALED_MANIFEST}' exists, it lists held-out evaluation files: evaluate "
    "the final method on them and report those metrics with the prefix 'sealed_'."
)


async def _run_code(ctx: ScientistContext, campaign_id: uuid.UUID, code: str, seed: int,
                    datasets: dict[str, bytes], extra: dict[str, bytes] | None = None) -> SandboxResult:
    seconds = int(ctx.config.sandbox.wall_seconds)
    await ctx.store.reserve_gpu_seconds(campaign_id, seconds)
    result = None
    try:
        result = await run_python(
            code, inputs={**datasets, **(extra or {}), SEED_FILE: str(seed).encode()},
            limits=ctx.config.sandbox, require_network_isolation=ctx.config.require_network_isolation,
        )
        return result
    finally:
        used = int(round(result.duration_seconds)) if result else 0
        await ctx.store.settle_gpu_seconds(campaign_id, seconds, used)


async def execute_intent(ctx: ScientistContext, campaign_id: uuid.UUID, intent: dict[str, Any],
                         worker_id: str) -> None:
    store = ctx.store
    spec = json.loads(intent["hypothesis_or_spec"])
    await store.heartbeat(intent["id"], worker_id, lease_seconds=ctx.config.lease_seconds)
    dataset_assets, datasets = await store.dataset_inputs(campaign_id)
    nonce = new_nonce()
    feedback = ""
    result: SandboxResult | None = None
    code = ""
    metrics: dict[str, Any] | None = None
    for attempt in range(ctx.config.max_code_attempts):
        await store.use_turn(intent["id"], worker_id)
        draft = await ctx.model.structured(
            campaign_id=campaign_id, purpose="write_experiment", schema=ExperimentCode, effort="medium",
            max_tokens=12000, system=_system("research engineer", nonce),
            prompt=(
                f"Hypothesis: {spec['hypothesis']}\nProtocol: {spec['protocol']}\n"
                f"Primary metric: {spec['primary_metric']}\nSuccess criterion: {spec['success_criterion']}\n"
                f"Dataset files: {sorted(datasets) or 'none'}\n\n{_CODE_RULES}\n\n{feedback}"
                "Write the complete script."
            ),
        )
        code = draft.code
        await store.heartbeat(intent["id"], worker_id, lease_seconds=ctx.config.lease_seconds)
        result = await _run_code(ctx, campaign_id, code, seed=1, datasets=datasets)
        if result.rejected:
            await store.record_guard_event(campaign_id, "command", "deny",
                                           {"reason": result.rejected, "attempt": attempt}, node_id=intent["id"])
            feedback = f"The previous script was rejected by the sandbox policy: {result.rejected}\n\n"
            continue
        if not result.network_isolated:
            await store.record_guard_event(campaign_id, "scope", "allow",
                                           {"note": "network namespace unavailable on host"}, node_id=intent["id"])
        metrics = parse_metrics(result.stdout) if result.ok else None
        if metrics is not None:
            break
        err = frame_untrusted((result.stderr or result.stdout)[-6000:], source="sandbox_output", nonce=nonce)
        reason = "timed out" if result.timed_out else (
            f"exited with code {result.exit_code}" if not result.ok else f"did not print a valid {METRICS_MARKER} line")
        feedback = f"The previous script {reason}. Output:\n{err.text}\nFix the script.\n\n"

    if metrics is None:  # also covers result is None
        if result is not None and not result.rejected:
            await store.add_evidence(intent["id"], "stdout_log",
                                     f"STDOUT\n{result.stdout}\n\nSTDERR\n{result.stderr}", approval_actor="system")
        await store.complete_intent(intent["id"], worker_id, "exhausted",
                                    metrics={"error": "no successful run", "attempts": ctx.config.max_code_attempts})
        return

    out = frame_untrusted(result.stdout[-8000:], source="experiment_stdout", nonce=nonce)
    obs = await ctx.model.structured(
        campaign_id=campaign_id, purpose="observe", schema=Observation, effort="low",
        system=_system("experiment analyst", nonce),
        prompt=(f"Hypothesis: {spec['hypothesis']}\nSuccess criterion: {spec['success_criterion']}\n"
                f"Measured metrics (authoritative): {json.dumps(metrics)}\n\nRun output:\n{out.text}\n\n"
                "State what was observed. Use only the measured numbers."),
    )
    fact_metrics = {**metrics, "seed": 1, "primary_metric": spec["primary_metric"],
                    "supports_hypothesis": obs.supports_hypothesis,
                    "runtime_seconds": round(result.duration_seconds, 3),
                    "network_isolated": result.network_isolated,
                    "code_sha256": sha256_hex(code)}
    fact_id = await store.record_fact(
        campaign_id, intent["id"], worker_id, title=obs.title, observation=obs.observation,
        metrics=fact_metrics, anchors=[(d["id"], "dataset_input") for d in dataset_assets],
    )
    await store.add_evidence(fact_id, "git_patch", code_as_patch(code), approval_actor="model")
    await store.add_evidence(fact_id, "stdout_log", result.stdout, approval_actor="system")
    for name, data in result.files.items():
        if name.endswith(".png"):
            await store.add_evidence(fact_id, "plot_png", data, approval_actor="model")
    for text in obs.follow_up_hints[:2]:
        hint = await store.create_node(campaign_id, "hint", text[:200], text,
                                       dedup_key=spec_dedup_key(text), priority=0.6)
        await store.add_edge(campaign_id, intent["id"], hint.id, "yields", "follow-up from observation")
    await store.complete_intent(intent["id"], worker_id, "verified", metrics={"fact_id": str(fact_id)})


async def run_worker(ctx: ScientistContext, campaign_id: uuid.UUID, worker_id: str) -> int:
    """One swarm member: claim, execute, repeat until the queue is empty."""
    done = 0
    while True:
        intent = await ctx.store.claim_next_intent(
            campaign_id, worker_id, lease_seconds=ctx.config.lease_seconds,
            max_attempts=ctx.config.max_claim_attempts,
        )
        if intent is None:
            return done
        try:
            await execute_intent(ctx, campaign_id, intent, worker_id)
            done += 1
        except LeaseLost:
            logger.warning("%s lost lease on %s; another worker owns it now", worker_id, intent["id"])
        except BudgetExceeded:
            # Hand the intent back so a later (re-budgeted) run can take it, then stop.
            try:
                await ctx.store.complete_intent(intent["id"], worker_id, "open")
            except LeaseLost:
                pass
            raise
        except (ModelRefusal, ModelOutputError) as exc:
            logger.warning("%s: intent %s failed: %s", worker_id, intent["id"], exc)
            try:
                await ctx.store.complete_intent(intent["id"], worker_id, "exhausted", metrics={"error": str(exc)[:500]})
            except LeaseLost:
                pass


async def experiment_swarm(ctx: ScientistContext, campaign_id: uuid.UUID) -> int:
    workers = [f"{ctx.worker_prefix}-w{i}" for i in range(ctx.config.workers)]
    results = await asyncio.gather(*(run_worker(ctx, campaign_id, w) for w in workers), return_exceptions=True)
    await ctx.store.exhaust_dead_intents(campaign_id, max_attempts=ctx.config.max_claim_attempts)
    for r in results:
        if isinstance(r, BaseException):
            raise r
    return sum(results)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 4. Skeptic + replication + figure critique: fact -> finding (proves) or refuted
# ---------------------------------------------------------------------------

async def rounds_completed(ctx: ScientistContext, campaign_id: uuid.UUID) -> int:
    root = await ctx.store.get_node(await _root_goal(ctx, campaign_id))
    return int(root["metrics"].get("rounds_completed", 0))


async def verifier(ctx: ScientistContext, campaign_id: uuid.UUID) -> dict[str, int]:
    store = ctx.store
    await store.transition_campaign(campaign_id, "ablating", from_statuses=["investigating"])
    datasets = await store.dataset_files(campaign_id)
    stats = {"promoted": 0, "refuted": 0}
    for fact in await store.nodes(campaign_id, node_type="fact", status="open"):
        patches = await store.evidence_contents(fact["id"], "git_patch")
        if not patches:
            continue
        code = code_from_patch(patches[0].decode("utf-8"))
        primary = fact["metrics"].get("primary_metric")
        original = fact["metrics"].get(primary) if primary else None

        # Replication with a different seed (ablation of randomness).
        rep = await _run_code(ctx, campaign_id, code, seed=2, datasets=datasets)
        rep_metrics = parse_metrics(rep.stdout) if rep.ok else None
        replicated = (
            rep_metrics is not None and isinstance(original, (int, float)) and primary in rep_metrics
            and metrics_agree(float(original), float(rep_metrics[primary]), ctx.config.replication_rel_tolerance)
        )
        await store.add_evidence(fact["id"], "stdout_log", f"REPLICATION seed=2\n{rep.stdout}\n{rep.stderr}")

        # Figure critique with the vision model.
        figure_scores = []
        for png in (await store.evidence_contents(fact["id"], "plot_png"))[:2]:
            critique = await ctx.model.structured(
                campaign_id=campaign_id, purpose="figure_critique", schema=FigureCritique, effort="low",
                system=_system("figure reviewer", new_nonce()), images=[png],
                prompt=f"Critique this figure for the claim: {fact['title']}. Metrics: {json.dumps(fact['metrics'])[:500]}",
            )
            score = _clamp01(critique.quality_score)
            figure_scores.append(score)
            await store.add_evidence(fact["id"], "vlm_critique", critique.model_dump_json(), approval_actor="model",
                                     vlm_quality_score=round(score, 2))

        p_value = fact["metrics"].get("p_value")
        stats_ok = p_value is None or float(p_value) < 0.05
        nonce = new_nonce()
        log = await store.evidence_contents(fact["id"], "stdout_log")
        framed_log = frame_untrusted(log[0].decode("utf-8", "replace")[-5000:] if log else "", source="stdout", nonce=nonce)
        verdict = await ctx.model.structured(
            campaign_id=campaign_id, purpose="skeptic", schema=SkepticVerdict, effort="high",
            system=_system("skeptical reviewer", nonce),
            prompt=(f"Candidate fact: {fact['title']}\n{fact['hypothesis_or_spec']}\n"
                    f"Metrics (seed 1): {json.dumps(fact['metrics'])}\n"
                    f"Replication (seed 2): {json.dumps(rep_metrics)} -> replicated={replicated}\n"
                    f"Statistical gate (p < 0.05 when reported): {stats_ok}\n"
                    f"Figure scores: {figure_scores}\nRun log:\n{framed_log.text}\n\n"
                    "Decide whether this is a reliable finding worth reporting. Reject anything "
                    "that does not replicate, overstates the numbers, or could be an artefact."),
        )
        gates = {
            "replicated": replicated,
            "stats_ok": stats_ok,
            "figures_ok": not figure_scores or sum(figure_scores) / len(figure_scores) >= ctx.config.min_figure_score,
            "skeptic": verdict.decision == "promote" and verdict.confidence >= ctx.config.min_promote_confidence,
        }
        confidence = _clamp01(verdict.confidence)
        if all(gates.values()):
            finding = await store.create_node(
                campaign_id, "finding", verdict.finding_title, verdict.finding_statement,
                dedup_key=spec_dedup_key(verdict.finding_title), status="verified",
                confidence_score=round(confidence, 3),
                metrics={"primary_metric": primary, primary: original, "replication": rep_metrics, **gates}
                if primary else gates,
            )
            await store.add_edge(campaign_id, fact["id"], finding.id, "proves", verdict.rationale[:2000])
            await store.set_node_status(fact["id"], "verified", confidence_score=round(confidence, 3),
                                        metrics={"gates": gates})
            stats["promoted"] += 1
        else:
            await store.set_node_status(fact["id"], "refuted", confidence_score=round(confidence, 3),
                                        metrics={"gates": gates, "skeptic_rationale": verdict.rationale[:1000]})
            stats["refuted"] += 1
    rounds = await rounds_completed(ctx, campaign_id) + 1
    await store.set_node_status(await _root_goal(ctx, campaign_id), "open", metrics={"rounds_completed": rounds})
    await store.transition_campaign(campaign_id, "investigating", from_statuses=["ablating"])
    return {**stats, "rounds_completed": rounds}


# ---------------------------------------------------------------------------
# 5. Sealed evaluation, then grounded manuscript + peer review
# ---------------------------------------------------------------------------

async def sealed_evaluation(ctx: ScientistContext, campaign_id: uuid.UUID) -> int:
    store = ctx.store
    await store.transition_campaign(campaign_id, "sealed_eval", from_statuses=["investigating", "ablating"])
    sealed = [a for a in await store.visible_assets(campaign_id, asset_types=["dataset"]) if a["is_sealed_eval"]
              or a["access_mode"] == "sealed_eval_only"]
    if not sealed:
        return 0
    datasets = await store.dataset_files(campaign_id)  # now includes held-out files
    manifest = json.dumps({"held_out_files": [a["metadata"].get("file_name") for a in sealed]}).encode()
    evaluated = 0
    for finding in await store.nodes(campaign_id, node_type="finding", status="verified"):
        trace = await store.trace_provenance(finding["id"], max_depth=2)
        facts = [n for n in trace["nodes"] if n["node_type"] == "fact"]
        if not facts:
            continue
        patches = await store.evidence_contents(facts[0]["id"], "git_patch")
        if not patches:
            continue
        run = await _run_code(ctx, campaign_id, code_from_patch(patches[0].decode()), seed=1,
                              datasets=datasets, extra={SEALED_MANIFEST: manifest})
        sealed_metrics = {k: v for k, v in (parse_metrics(run.stdout) or {}).items() if k.startswith("sealed_")}
        await store.add_evidence(finding["id"], "sealed_eval_json",
                                 json.dumps({"ok": run.ok, "metrics": sealed_metrics}, sort_keys=True))
        for asset in sealed:
            await store.link_anchor(finding["id"], asset["id"], "target_benchmark")
        await store.set_node_status(finding["id"], "verified", metrics={"sealed_eval": sealed_metrics or None})
        evaluated += 1
    return evaluated


_LATEX_ESCAPES = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
                  "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "\\": r"\textbackslash{}"}


def latex_escape(text: str) -> str:
    return "".join(_LATEX_ESCAPES.get(ch, ch) for ch in text)


def _bib_key(asset: dict[str, Any]) -> str:
    return "ref_" + re.sub(r"[^a-z0-9]", "", asset["dedup_key"].lower())[-24:]


def build_bibtex(papers: list[dict[str, Any]]) -> str:
    entries = []
    for p in papers:
        meta = p["metadata"]
        fields = {
            "title": "{" + latex_escape(meta.get("title") or p["canonical_name"]) + "}",
            "author": " and ".join(latex_escape(a) for a in (meta.get("authors") or [])[:10]) or "Unknown",
            "year": str(meta.get("year") or ""),
            "doi": meta.get("doi") or "",
            "eprint": meta.get("arxiv_id") or "",
            "url": p.get("uri_or_commit") or "",
        }
        body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields.items() if v)
        entries.append(f"@misc{{{_bib_key(p)},\n{body}\n}}")
    return "\n\n".join(entries) + ("\n" if entries else "")


_CITE_RE = re.compile(r"\\cite[pt]?\{([^}]*)\}")


def _filter_citations(text: str, allowed: set[str]) -> tuple[str, list[str]]:
    dropped: list[str] = []

    def repl(m: re.Match[str]) -> str:
        keys = [k.strip() for k in m.group(1).split(",")]
        ok = [k for k in keys if k in allowed]
        dropped.extend(k for k in keys if k not in allowed)
        return f"\\cite{{{','.join(ok)}}}" if ok else ""

    return _CITE_RE.sub(repl, text), dropped


def assemble_latex(ms: Manuscript, findings: list[dict[str, Any]]) -> str:
    rows = "\n".join(
        f"{latex_escape(f['title'])} & {f['confidence_score'] if f['confidence_score'] is not None else '--'} \\\\"
        for f in findings
    )
    return (
        "\\documentclass{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage{hyperref}\n"
        f"\\title{{{latex_escape(ms.title)}}}\n\\author{{Plato autonomous research swarm}}\n"
        "\\begin{document}\n\\maketitle\n"
        f"\\begin{{abstract}}\n{ms.abstract}\n\\end{{abstract}}\n"
        f"\\section{{Introduction}}\n{ms.introduction}\n"
        f"\\section{{Methods}}\n{ms.methods}\n"
        f"\\section{{Results}}\n{ms.results}\n"
        "\\begin{table}[h]\\centering\n\\begin{tabular}{lr}\nFinding & Confidence \\\\\n\\hline\n"
        f"{rows}\n\\end{{tabular}}\n\\caption{{Verified findings with skeptic confidence.}}\n\\end{{table}}\n"
        f"\\section{{Discussion}}\n{ms.discussion}\n"
        f"\\section{{Limitations}}\n{ms.limitations}\n"
        "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n"
    )


async def write_manuscript(ctx: ScientistContext, campaign_id: uuid.UUID) -> dict[str, Any]:
    store = ctx.store
    await store.transition_campaign(campaign_id, "writing", from_statuses=["sealed_eval", "investigating", "ablating"])
    campaign = await store.get_campaign(campaign_id)
    root_id = await _root_goal(ctx, campaign_id)
    findings = await store.nodes(campaign_id, node_type="finding", status="verified")
    refuted = await store.nodes(campaign_id, node_type="fact", status="refuted")

    # Ground the paper in provenance: only papers anchored somewhere in the graph are citable.
    papers = {a["id"]: a for a in await store.visible_assets(campaign_id, asset_types=["paper"])}
    hints = await store.nodes(campaign_id, node_type="hint")
    anchored = (await store.anchored_asset_ids([f["id"] for f in findings])
                | await store.anchored_asset_ids([h["id"] for h in hints], max_depth=0))
    citable = [p for i, p in papers.items() if i in anchored] or list(papers.values())[:10]
    keys = {_bib_key(p): p for p in citable}
    bib = build_bibtex(citable)

    nonce = new_nonce()
    finding_text = "\n".join(
        f"- {f['title']}: {f['hypothesis_or_spec']} (confidence {f['confidence_score']}, metrics {json.dumps(f['metrics'])[:400]})"
        for f in findings) or "(no finding passed verification)"
    refs = "\n".join(frame_untrusted(f"{k}: {p['canonical_name']} ({p['metadata'].get('year')})", source=k, nonce=nonce).text
                     for k, p in keys.items())
    base_prompt = (
        f"Research question: {campaign['research_question']}\n\nVerified findings (the only results you may report):\n"
        f"{finding_text}\n\nRefuted or non-replicating observations: {len(refuted)}\n\n"
        f"Citable references (use \\cite{{key}} with these keys only):\n{refs}\n\n"
        "Write each section as LaTeX body text (no preamble). Report numbers exactly as given; state "
        "clearly that experiments are computational and automated, and what was not established."
    )
    ms = await ctx.model.structured(campaign_id=campaign_id, purpose="manuscript", schema=Manuscript,
                                    effort="high", max_tokens=16000, system=_system("scientific writer", nonce),
                                    prompt=base_prompt)
    review = await ctx.model.structured(
        campaign_id=campaign_id, purpose="peer_review", schema=PeerReview, effort="high",
        system=_system("peer reviewer for a top venue", nonce),
        prompt=f"Review this manuscript against the evidence.\n\nEvidence:\n{finding_text}\n\nManuscript:\n{ms.model_dump_json()}",
    )
    revised = False
    if review.decision in ("major_revision", "reject") and review.required_changes:
        ms = await ctx.model.structured(
            campaign_id=campaign_id, purpose="manuscript_revision", schema=Manuscript, effort="high",
            max_tokens=16000, system=_system("scientific writer", nonce),
            prompt=base_prompt + "\n\nRevise the manuscript to address:\n" + "\n".join(f"- {c}" for c in review.required_changes),
        )
        revised = True

    dropped: list[str] = []
    cleaned = {}
    for name in Manuscript.model_fields.keys() - {"title"}:
        cleaned[name], bad = _filter_citations(getattr(ms, name), set(keys))
        dropped += bad
    ms = ms.model_copy(update=cleaned)
    if dropped:
        await store.record_guard_event(campaign_id, "scope", "deny",
                                       {"note": "removed citations not grounded in the graph", "keys": sorted(set(dropped))})
    tex = assemble_latex(ms, findings)
    await store.add_evidence(root_id, "latex_section", tex, approval_actor="model")
    await store.add_evidence(root_id, "bibtex", bib, approval_actor="system")
    await store.add_evidence(root_id, "peer_review", review.model_dump_json(), approval_actor="model")
    await store.set_node_status(root_id, "verified", metrics={
        "findings": len(findings), "review_decision": review.decision, "revised": revised})
    await store.transition_campaign(campaign_id, "completed", from_statuses=["writing"])
    return {"findings": len(findings), "review": review.decision, "revised": revised}
