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
import math
import os
import re
import socket
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from .citations import (
    check_sources,
    exclusion_reason,
    fetch_missing_abstracts,
    has_abstract,
)
from .db.store import (
    BudgetExceeded,
    DualGraphStore,
    LeaseLost,
    paper_dedup_key,
    sha256_hex,
    spec_dedup_key,
    valid_file_name,
)
from .executors import run_experiment
from .guard import (
    SandboxLimits,
    SandboxResult,
    frame_untrusted,
    framing_instructions,
    new_nonce,
)
from .llm import ModelOutputError, ModelRefusal, ScientistModel
from .profiles import ScientistProfile, get_profile, resolve_profile
from .review import (
    apply_revision,
    build_evidence_matrix,
    check_revision,
    matrix_digest,
    matrix_required_changes,
    panel_digest,
    review_record,
    run_review_panel,
    strip_unsupported_citations,
)
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
    decode_intent_spec,
    encode_intent_spec,
)

logger = logging.getLogger(__name__)

METRICS_MARKER = "PLATO_METRICS"
# Thinking plus the LaTeX body of one manuscript call (Haiku 5.5 allows 128k output).
MANUSCRIPT_MAX_TOKENS = 48_000
PLAN_MAX_TOKENS = 16_000
SEED_FILE = "plato_seed.txt"
SEALED_MANIFEST = "plato_sealed.json"
# Present only in the verifier's replication run: the script must draw a bootstrap resample
# of its independent units with the given seed before computing any metric.
REPLICATE_FILE = "plato_replicate.json"
ROOT_GOAL_KEY = "root-goal"

# (query, limit, *, sources) -> papers. ``sources`` names the retrieval adapters to use.
Retriever = Callable[..., Awaitable[list[Any]]]
# Seconds one literature source may take (its retries included) before it is skipped.
ADAPTER_TIMEOUT_SECONDS = 60.0


async def default_retriever(
    query: str, limit: int, *, sources: list[str] | None = None
) -> list[Any]:
    from plato.retrieval.orchestrator import retrieve

    return await retrieve(
        query,
        limit,
        adapter_names=list(sources or get_profile("general").retrieval_sources),
        rerank_fallback="fused",
        adapter_timeout=ADAPTER_TIMEOUT_SECONDS,
        drop_supplementary=True,
    )


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
    # Significance level of every hypothesis test (difference, TOST, held-out re-test).
    alpha: float = 0.05
    # Correction across every hypothesis a campaign tests: "bh" (Benjamini-Hochberg false
    # discovery rate), "holm" (Holm-Bonferroni family-wise error rate) or "none".
    multiplicity: str = "bh"
    require_network_isolation: bool = False
    # Requested research domain (selects the literature sources and packages).
    domain: str = "general"
    # Where experiments run: "local" (this container's sandbox), "modal" (Modal Labs
    # sandbox, optionally with a GPU) or "e2b" (the research engineer gets a full E2B
    # workspace: shell, packages, dataset downloads, bio tools; each result is recorded by
    # re-running its recipe in a fresh sandbox).
    executor: str = "local"
    # Modal GPU type such as "T4", "L4" or "A100"; empty means CPU only.
    gpu: str = ""
    sandbox: SandboxLimits = field(default_factory=SandboxLimits)
    workspace_session_seconds: int = 2400
    workspace_max_turns: int = 40
    workspace_setup_seconds: int = 1200
    workspace_run_seconds: int = 1200

    @classmethod
    def from_campaign(cls, config: dict[str, Any] | None) -> ScientistConfig:
        cfg = cls()
        config = config or {}
        for key, value in config.items():
            if key != "sandbox" and hasattr(cfg, key):
                setattr(cfg, key, type(getattr(cfg, key))(value))
        if "executor" not in config:
            from .workspace.runtime import e2b_configured

            default = os.environ.get("PLATO_DEFAULT_EXECUTOR", cfg.executor)
            # A deployment default of e2b without a key falls back to the container sandbox;
            # a campaign that names e2b explicitly fails loudly instead.
            cfg.executor = (
                "local" if default == "e2b" and not e2b_configured() else default
            )
        if cfg.executor == "modal" and cfg.gpu:
            # GPU experiments (training) get ten minutes on a larger machine.
            cfg.sandbox = SandboxLimits(
                wall_seconds=600.0, cpu_seconds=600, memory_bytes=16 * 1024**3
            )
        return cfg


@dataclass
class ScientistContext:
    store: DualGraphStore
    model: ScientistModel
    config: ScientistConfig = field(default_factory=ScientistConfig)
    retriever: Retriever = default_retriever
    # (sources) -> one citation-check summary per source, in order (never raises).
    citation_checker: Callable[[list[Any]], Awaitable[list[dict[str, Any]]]] = (
        check_sources
    )
    # (sources) -> an abstract for each source that lacks one, or None (never raises).
    abstract_fetcher: Callable[[list[Any]], Awaitable[list[str | None]]] = (
        fetch_missing_abstracts
    )
    worker_prefix: str = field(
        default_factory=lambda: f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
    )
    # Creates workspace sandboxes for executor "e2b" (None: E2B from the environment).
    backend_factory: Any = None

    def workspace_backends(self):
        if self.backend_factory is None:
            from .workspace import default_backend_factory

            self.backend_factory = default_backend_factory()
        return self.backend_factory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_metrics(stdout: str) -> dict[str, Any] | None:
    """Metrics are reported by the experiment, never inferred by the model: the last line
    starting with ``PLATO_METRICS`` must carry a JSON object of numbers."""
    for line in reversed(stdout.splitlines()):
        if line.startswith(METRICS_MARKER):
            try:
                value = json.loads(line[len(METRICS_MARKER) :].strip())
            except json.JSONDecodeError:
                return None
            if (
                isinstance(value, dict)
                and value
                and all(
                    isinstance(v, (int, float)) and not isinstance(v, bool)
                    for v in value.values()
                )
            ):
                return value
            return None
    return None


def metric_key(name: str) -> str:
    """Normalise a planner's metric name to the snake_case key the script must print.

    Planners sometimes describe the metric ("Empirical 95% CI coverage") instead of naming
    it; the key is what replication and the paper look up, so it must be deterministic."""
    key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:48].strip("_")
    return (
        key if key and not key[0].isdigit() else f"m_{key}" if key else "primary_value"
    )


def missing_required_metrics(
    metrics: dict[str, Any], spec: dict[str, Any]
) -> list[str]:
    """Keys the verifier needs but the run did not print. Every claim is a hypothesis
    test, so a p_value is always required: without one nothing can be verified."""
    required = [spec["primary_metric"], "p_value"]
    return [k for k in required if k not in metrics]


def code_as_patch(code: str) -> str:
    lines = code.splitlines()
    body = "\n".join(f"+{line}" for line in lines)
    return f"--- /dev/null\n+++ b/experiment.py\n@@ -0,0 +1,{len(lines)} @@\n{body}\n"


def recipe_as_patch(code: str, setup: str | None) -> str:
    """Experiment plus (optionally) its environment recipe as one new-files patch."""
    patch = code_as_patch(code)
    if not setup:
        return patch
    lines = setup.splitlines()
    body = "\n".join(f"+{line}" for line in lines)
    return f"--- /dev/null\n+++ b/setup.sh\n@@ -0,0 +1,{len(lines)} @@\n{body}\n{patch}"


def files_from_patch(patch: str) -> dict[str, str]:
    """Parse a new-files patch by its hunk line counts (bodies may contain diff-like text)."""
    lines = patch.splitlines()
    files: dict[str, str] = {}
    i = 0
    while i + 2 < len(lines):
        m = re.match(r"^@@ -0,0 \+1,(\d+) @@$", lines[i + 2])
        if lines[i] == "--- /dev/null" and lines[i + 1].startswith("+++ b/") and m:
            n = int(m.group(1))
            body = lines[i + 3 : i + 3 + n]
            files[lines[i + 1][6:]] = "\n".join(b[1:] for b in body)
            i += 3 + n
        else:
            i += 1
    return files


def recipe_from_patch(patch: str) -> tuple[str, str | None]:
    files = files_from_patch(patch)
    if "experiment.py" not in files:  # legacy or hand-made patch: every added line
        return code_from_patch(patch), None
    return files["experiment.py"], files.get("setup.sh")


def code_from_patch(patch: str) -> str:
    files = files_from_patch(patch)
    if "experiment.py" in files:
        return files["experiment.py"]
    return "\n".join(
        line[1:] for line in patch.splitlines()[3:] if line.startswith("+")
    )


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def metrics_agree(a: float, b: float, rel_tol: float) -> bool:
    if a == b:
        return True
    scale = max(abs(a), abs(b))
    return scale > 0 and abs(a - b) / scale <= rel_tol


def replicates(
    key: str, original: dict[str, Any], replica: dict[str, Any] | None, rel_tol: float
) -> bool:
    """Does the seed-2 run reproduce the seed-1 primary metric?

    With standard errors reported (``<key>_se``) the two runs are independent estimates,
    so they agree when their difference is within 3 combined SEs; this is the only sound
    test for near-zero quantities such as bias, whose sign flips between seeds. Without
    SEs, fall back to a relative tolerance."""
    if replica is None:
        return False
    a, b = original.get(key), replica.get(key)
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (a, b)):
        return False
    se_a, se_b = original.get(f"{key}_se"), replica.get(f"{key}_se")
    if all(isinstance(v, (int, float)) and v >= 0 for v in (se_a, se_b)):
        return abs(a - b) <= 3 * (se_a**2 + se_b**2) ** 0.5 or metrics_agree(
            float(a), float(b), rel_tol
        )
    return metrics_agree(float(a), float(b), rel_tol)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def replication_outcome(
    key: str,
    original: dict[str, Any],
    replica: dict[str, Any] | None,
    rel_tol: float,
) -> tuple[bool, str]:
    """Judge the replication run (new seed plus a bootstrap resample of the units).

    A replica that printed exactly the original numbers was not perturbed at all: the
    script ignored both the seed and the resample, so agreement would be a tautology and
    proves nothing. That is a failed replication, not a passed one."""
    if replica is None:
        return False, "replication run failed"
    shared = [
        k
        for k in replica
        if _number(replica.get(k)) is not None and _number(original.get(k)) is not None
    ]
    if key in shared and all(
        _number(replica[k]) == _number(original[k]) for k in shared
    ):
        return False, "replication printed identical numbers (resample ignored)"
    if replicates(key, original, replica, rel_tol):
        return True, "agrees"
    return False, "replication disagrees"


def adjusted_p_values(pvals: dict[Any, float], method: str) -> dict[Any, float]:
    """Multiplicity-adjusted p-values over one family of tests.

    ``bh``: Benjamini-Hochberg step-up (controls the false discovery rate);
    ``holm``: Holm-Bonferroni step-down (controls the family-wise error rate);
    ``none``: unadjusted. Adjusted values are capped at 1 and monotone in the raw p."""
    if method == "none" or not pvals:
        return dict(pvals)
    if method not in ("bh", "holm"):
        raise ValueError(f"unknown multiplicity method {method!r}")
    m = len(pvals)
    order = sorted(pvals, key=lambda k: pvals[k])
    adjusted: dict[Any, float] = {}
    if method == "holm":
        running = 0.0
        for i, k in enumerate(order):
            running = max(running, min(1.0, (m - i) * pvals[k]))
            adjusted[k] = running
    else:
        running = 1.0
        for i in range(m - 1, -1, -1):
            k = order[i]
            running = min(running, m * pvals[k] / (i + 1))
            adjusted[k] = min(1.0, running)
    return adjusted


def classify_fact(gates: dict[str, bool], supports_hypothesis: Any) -> str:
    """Status of a verified-or-not fact.

    ``verified`` needs every gate. ``refuted`` means the evidence contradicts the
    hypothesis: the result replicated and is statistically significant, and it goes
    against the hypothesis. Anything else that failed a gate (no replication, p above
    alpha, a weak figure, a sceptical review) is ``inconclusive``: absence of evidence is
    not evidence against, so it must never be written up as a negative result."""
    if all(gates.values()):
        return "verified"
    if (
        gates.get("replicated")
        and gates.get("stats_ok")
        and gates.get("multiplicity", True)
        and supports_hypothesis == "no"
    ):
        return "refuted"
    return "inconclusive"


def held_out_outcome(
    fact_metrics: dict[str, Any],
    run_ok: bool,
    sealed_metrics: dict[str, Any],
    alpha: float,
) -> tuple[bool, str]:
    """Does the held-out re-test confirm a finding? It must run, report the same
    hypothesis test as ``sealed_p_value`` below alpha and, for a difference claim, not
    point the other way."""
    if not run_ok:
        return False, "held-out run failed"
    p = _number(sealed_metrics.get("sealed_p_value"))
    if p is None:
        return False, "held-out test not reported (no sealed_p_value)"
    if p >= alpha:
        return False, f"held-out test not significant (p = {p:.3g})"
    primary = fact_metrics.get("primary_metric")
    trained = _number(fact_metrics.get(primary)) if primary else None
    held = _number(sealed_metrics.get(f"sealed_{primary}")) if primary else None
    if (
        fact_metrics.get("test_kind", "difference") == "difference"
        and trained
        and held
        and (trained > 0) != (held > 0)
    ):
        return False, "held-out effect points the other way"
    return True, "confirmed"


async def _guarded(
    ctx: ScientistContext, campaign_id: uuid.UUID, framed_sources: list
) -> None:
    """Record any prompt-injection signals seen in untrusted text (allowed but flagged)."""
    for framed in framed_sources:
        if framed.injection_signals:
            await ctx.store.record_guard_event(
                campaign_id,
                "injection",
                "allow",
                {
                    "signals": list(framed.injection_signals),
                    "note": "framed as untrusted",
                },
            )


def _system(role: str, nonce: str) -> str:
    return (
        f"You are the {role} in an autonomous research team. Be precise, quantitative and honest "
        "about uncertainty; never invent results, citations or numbers. "
        + framing_instructions(nonce)
    )


async def campaign_profile(
    ctx: ScientistContext, campaign_id: uuid.UUID
) -> ScientistProfile:
    """The domain profile the literature scout chose (stored on the root goal)."""
    root = await ctx.store.get_node(await _root_goal(ctx, campaign_id))
    return get_profile((root["metrics"] or {}).get("profile"))


def experiment_limits_text(config: ScientistConfig) -> str:
    seconds = int(config.sandbox.wall_seconds)
    where = (
        f"on a Modal {config.gpu} GPU machine"
        if config.executor == "modal" and config.gpu
        else "on a CPU"
    )
    return f"in under {seconds} seconds {where}"


async def _root_goal(ctx: ScientistContext, campaign_id: uuid.UUID) -> uuid.UUID:
    campaign = await ctx.store.get_campaign(campaign_id)
    root = await ctx.store.create_node(
        campaign_id,
        "goal",
        "Research question",
        campaign["research_question"],
        dedup_key=ROOT_GOAL_KEY,
        priority=1.0,
    )
    return root.id


# ---------------------------------------------------------------------------
# 1. Literature scout: question -> goals, papers (knowledge assets), hints
# ---------------------------------------------------------------------------


async def user_materials(
    store: DualGraphStore, campaign_id: uuid.UUID
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Reference papers and documents the researcher supplied with the campaign (imported
    from their library: .bib/.ris files, PDFs, Word documents, notes)."""
    papers = [
        a
        for a in await store.visible_assets(campaign_id, asset_types=["paper"])
        if (a["metadata"] or {}).get("user_supplied")
    ]
    docs = [
        a
        for a in await store.visible_assets(campaign_id, asset_types=["corpus_domain"])
        if (a["metadata"] or {}).get("user_document")
    ]
    return papers, docs


def _frame_documents(docs: list[dict[str, Any]], nonce: str, chars: int) -> list:
    return [
        frame_untrusted(
            f"{d['canonical_name']}\n{((d['metadata'] or {}).get('excerpt') or '')[:chars]}",
            source=f"document_{i}",
            nonce=nonce,
        )
        for i, d in enumerate(docs)
    ]


async def literature_scout(ctx: ScientistContext, campaign_id: uuid.UUID) -> None:
    store = ctx.store
    campaign = await store.get_campaign(campaign_id)
    if campaign["status"] != "ideation":
        return
    nonce = new_nonce()
    root_id = await _root_goal(ctx, campaign_id)
    question = frame_untrusted(
        campaign["research_question"], source="operator_topic", nonce=nonce
    )

    plan = await ctx.model.structured(
        campaign_id=campaign_id,
        purpose="plan",
        schema=ResearchPlan,
        effort="medium",
        system=_system("principal investigator", nonce),
        prompt=(
            "Turn this topic into a precise research plan that can be investigated with "
            "computational experiments (simulation, analysis of provided data, or "
            "re-implementation of published methods) inside an offline Python sandbox.\n\n"
            f"{question.text}"
        ),
    )
    # The requested domain wins; the plan's own label refines an unspecific one.
    profile = resolve_profile(
        ctx.config.domain, campaign.get("program_domain"), plan.domain
    )
    await store.set_node_status(
        root_id,
        "open",
        metrics={
            "refined_question": plan.refined_question,
            "domain": plan.domain,
            "profile": profile.name,
            "retrieval_sources": list(profile.retrieval_sources),
        },
    )
    goal_ids = []
    for goal in plan.goals[:4]:
        node = await store.create_node(
            campaign_id,
            "goal",
            goal.title,
            goal.objective,
            dedup_key=spec_dedup_key(goal.title),
            priority=0.8,
        )
        await store.add_edge(
            campaign_id, root_id, node.id, "spawns", "plan decomposition"
        )
        goal_ids.append(node.id)

    # Literature -> knowledge assets (deduplicated across all campaigns of the program).
    domain_asset = await store.upsert_asset(
        campaign["program_id"], "corpus_domain", f"domain:{plan.domain}", plan.domain
    )
    # 1) Search every query across the profile's sources, deduplicated by paper key.
    found: dict[str, tuple[str, Any]] = {}
    for query in plan.search_queries[:4]:
        try:
            results = await ctx.retriever(
                query,
                ctx.config.papers_per_query,
                sources=list(profile.retrieval_sources),
            )
        except Exception as exc:  # noqa: BLE001 - one failed source must not stop the campaign
            logger.warning("retrieval failed for %r: %s", query, exc)
            results = []
        for src in results:
            try:
                key = paper_dedup_key(
                    doi=src.doi, arxiv_id=src.arxiv_id, title=src.title, year=src.year
                )
            except ValueError:
                continue
            found.setdefault(key, (query, src))

    # 2) Citation and retraction checks: retracted papers, and papers whose identifier
    # resolves to a different work, are kept out of the campaign.
    keys = list(found)
    checks = await ctx.citation_checker([found[k][1] for k in keys])
    # Papers retrieved without an abstract get one from OpenAlex/arXiv where possible: a
    # paper is citable only with an abstract to check the citing claim against.
    filled = await ctx.abstract_fetcher([found[k][1] for k in keys])
    papers: list[tuple[uuid.UUID, Any]] = []
    excluded: list[dict[str, Any]] = []
    for key, check, extra_abstract in zip(keys, checks, filled, strict=True):
        query, src = found[key]
        abstract = (extra_abstract or src.abstract or "")[:3000]
        asset = await store.upsert_asset(
            campaign["program_id"],
            "paper",
            key,
            src.title[:500],
            uri_or_commit=src.url
            or (f"https://doi.org/{src.doi}" if src.doi else None),
            parent_id=domain_asset.id,
            metadata={
                "title": src.title,
                "authors": list(src.authors)[:20],
                "year": src.year,
                "venue": src.venue,
                "doi": src.doi,
                "arxiv_id": src.arxiv_id,
                # Never overwrite an abstract another campaign stored with an empty one.
                **({"abstract": abstract} if abstract.strip() else {}),
                "abstract_source": "openalex_or_arxiv"
                if extra_abstract
                else "retrieval"
                if abstract.strip()
                else None,
                "query": query,
                "retrieved_via": getattr(src, "retrieved_via", None),
                "citation_check": check,
            },
        )
        reason = exclusion_reason(check)
        if reason:
            await store.set_scope(campaign_id, asset.id, "excluded")
            excluded.append(
                {
                    "title": src.title[:300],
                    "doi": src.doi,
                    "arxiv_id": src.arxiv_id,
                    "reason": reason,
                }
            )
            continue
        papers.append(
            (
                asset.id,
                SimpleNamespace(title=src.title, year=src.year, abstract=abstract),
            )
        )
        await store.set_scope(campaign_id, asset.id, "read_only")
    # The researcher's own references join the search results (citable like any paper).
    user_papers, user_docs = await user_materials(store, campaign_id)
    known = {pid for pid, _ in papers}
    user_papers = [a for a in user_papers if a["id"] not in known]
    user_filled = await ctx.abstract_fetcher(
        [
            SimpleNamespace(
                doi=(a["metadata"] or {}).get("doi"),
                arxiv_id=(a["metadata"] or {}).get("arxiv_id"),
                abstract=(a["metadata"] or {}).get("abstract") or "",
            )
            for a in user_papers
        ]
    )
    for a, extra_abstract in zip(user_papers, user_filled, strict=True):
        if extra_abstract:
            await store.merge_asset_metadata(
                a["id"],
                {
                    "abstract": extra_abstract[:3000],
                    "abstract_source": "openalex_or_arxiv",
                },
            )
            a["metadata"] = {**(a["metadata"] or {}), "abstract": extra_abstract[:3000]}
        if a["id"] not in known:
            known.add(a["id"])
            meta = a["metadata"] or {}
            papers.append(
                (
                    a["id"],
                    SimpleNamespace(
                        title=meta.get("title") or a["canonical_name"],
                        year=meta.get("year"),
                        abstract=meta.get("abstract") or "",
                    ),
                )
            )
    if excluded:
        await store.record_guard_event(
            campaign_id,
            "scope",
            "deny",
            {"note": "papers excluded by citation checks", "papers": excluded},
        )
    statuses: dict[str, int] = {}
    for check in checks:
        statuses[check["status"]] = statuses.get(check["status"], 0) + 1
    await store.set_node_status(
        root_id,
        "open",
        metrics={
            "citation_checks": statuses,
            "papers_excluded": excluded,
        },
    )
    await store.set_node_status(root_id, "open", metrics={"papers_found": len(papers)})

    framed_papers = [
        frame_untrusted(
            f"[{i}] {src.title} ({src.year})\n{(src.abstract or '')[:1500]}",
            source=f"paper_{i}",
            nonce=nonce,
        )
        for i, (_, src) in enumerate(papers)
    ]
    framed_docs = _frame_documents(user_docs, nonce, 4000)
    await _guarded(ctx, campaign_id, framed_papers + framed_docs)
    literature = (
        "\n".join(f.text for f in framed_papers) or "(no literature could be retrieved)"
    )
    if framed_docs:
        literature += "\n\nDocuments provided by the researcher:\n" + "\n".join(
            f.text for f in framed_docs
        )
    hints = await ctx.model.structured(
        campaign_id=campaign_id,
        purpose="hints",
        schema=LiteratureHints,
        effort="medium",
        system=_system("literature analyst", nonce),
        prompt=(
            f"Research question: {plan.refined_question}\n\nPapers:\n{literature}\n\n"
            "List up to 5 unexplored directions, gaps or contradictions that a computational "
            "experiment could test. Cite paper indices; use an empty list when none apply."
        ),
    )
    for hint in hints.hints[:5]:
        node = await store.create_node(
            campaign_id,
            "hint",
            hint.title,
            hint.rationale,
            dedup_key=spec_dedup_key(hint.title),
            priority=0.5,
        )
        await store.add_edge(campaign_id, root_id, node.id, "spawns", "literature gap")
        for idx in hint.cited_papers:
            if 0 <= idx < len(papers):
                await store.link_anchor(node.id, papers[idx][0], "cited_prior_work")
    await store.transition_campaign(
        campaign_id, "investigating", from_statuses=["ideation"]
    )


# ---------------------------------------------------------------------------
# 2. Experiment planner: uncovered scope + hints + facts -> intents (tree expansion)
# ---------------------------------------------------------------------------


async def experiment_planner(
    ctx: ScientistContext, campaign_id: uuid.UUID, round_no: int
) -> int:
    store = ctx.store
    campaign = await store.get_campaign(campaign_id)
    nonce = new_nonce()
    goals = [
        g
        for g in await store.nodes(campaign_id, node_type="goal")
        if g["dedup_key"] != ROOT_GOAL_KEY
    ]
    hints = await store.nodes(campaign_id, node_type="hint", status="open")
    facts = await store.nodes(campaign_id, node_type="fact")
    existing = await store.nodes(campaign_id, node_type="intent")
    datasets = await store.visible_assets(campaign_id, asset_types=["dataset"])
    uncovered = await store.query_uncovered_scope(campaign_id)
    _, user_docs = await user_materials(store, campaign_id)
    framed_docs = _frame_documents(user_docs, nonce, 800)
    profile = await campaign_profile(ctx, campaign_id)

    framed = [
        frame_untrusted(
            f"[{i}] {h['title']}: {h['hypothesis_or_spec']}",
            source=f"hint_{i}",
            nonce=nonce,
        )
        for i, h in enumerate(hints)
    ]
    fact_lines = (
        "\n".join(
            f"- ({f['status']}) {f['title']}: {json.dumps(f['metrics'])[:300]}"
            for f in facts[-20:]
        )
        or "(none yet)"
    )
    prompt = (
        f"Research question: {campaign['research_question']}\n"
        f"Round {round_no + 1} of {ctx.config.max_rounds}.\n\n"
        "Goals:\n"
        + "\n".join(
            f"[{i}] {g['title']}: {g['hypothesis_or_spec']}"
            for i, g in enumerate(goals)
        )
        + "\n\nOpen hints:\n"
        + ("\n".join(f.text for f in framed) or "(none)")
        + f"\n\nFacts so far:\n{fact_lines}\n\n"
        + "Experiments already planned (do not repeat):\n"
        + ("\n".join(f"- {i['title']}" for i in existing) or "(none)")
        + "\n\nDatasets available in the sandbox:\n"
        + (
            "\n".join(
                f"- {d['metadata'].get('file_name')}: {d['metadata'].get('description', '')}"
                for d in datasets
            )
            or "(none: design simulations or analyses that generate their own data)"
        )
        + (
            "\n\nDocuments provided by the researcher (excerpts):\n"
            + "\n".join(f.text for f in framed_docs)
            if framed_docs
            else ""
        )
        + f"\n\nPapers not yet used by any experiment: {len(uncovered)}\n\n"
        f"Propose up to {ctx.config.intents_per_round} new, independent computational experiments "
        "(never more). Keep each protocol under 150 words: the research engineer designs the code. "
        "Prefer experiments that resolve open hints or follow up surprising facts. Each must run "
        f"offline {experiment_limits_text(ctx.config)} with {profile_tools(profile, ctx.config)}. "
        + (f"{profile.guidance} " if profile.guidance else "")
        # In a live sandbox the engineer installs tools and downloads public data before the
        # recorded run, so a protocol may call for the lab's own tools and for public data.
        + (
            f"{profile.workspace_guidance} "
            if profile.workspace_guidance and ctx.config.executor == "e2b"
            else ""
        )
        + "Derive any "
        "predicted value analytically before stating it, and set each success criterion relative to "
        "the standard error the protocol can resolve: a threshold below the sampling noise refutes "
        "true hypotheses. Mark claims of agreement with a reference value as 'equivalence' tests "
        "with a tolerance of at least 3 Monte Carlo standard errors."
    )
    await _guarded(ctx, campaign_id, framed + framed_docs)
    batch = await ctx.model.structured(
        campaign_id=campaign_id,
        purpose="plan_intents",
        schema=IntentBatch,
        effort="medium",
        # Thinking and up to intents_per_round full specs share this cap.
        max_tokens=PLAN_MAX_TOKENS,
        system=_system("experiment planner", nonce),
        prompt=prompt,
    )
    created = 0
    for spec in batch.intents[: ctx.config.intents_per_round]:
        # Progressive tree search: follow-ups of observed facts rank above fresh ideas.
        bonus = 0.2 if spec.source_hint_index is not None else 0.0
        priority = _clamp01(spec.priority) + bonus
        node = await store.create_node(
            campaign_id,
            "intent",
            spec.title,
            encode_intent_spec(spec, metric_key(spec.primary_metric)),
            dedup_key=spec_dedup_key(spec.hypothesis, spec.protocol),
            priority=priority,
            turn_budget_max=ctx.config.max_code_attempts * 2,
        )
        if not node.created:
            continue
        created += 1
        if 0 <= spec.goal_index < len(goals):
            await store.add_edge(
                campaign_id, goals[spec.goal_index]["id"], node.id, "spawns"
            )
        if spec.source_hint_index is not None and 0 <= spec.source_hint_index < len(
            hints
        ):
            hint = hints[spec.source_hint_index]
            await store.add_edge(campaign_id, hint["id"], node.id, "derived_from")
            await store.set_node_status(hint["id"], "exhausted")
        for d in datasets:
            await store.link_anchor(node.id, d["id"], "dataset_input")
    return created


# ---------------------------------------------------------------------------
# 3. Sandboxed experimenter swarm
# ---------------------------------------------------------------------------


# Readers explore these files in the app (charts and tables, 2D/3D structures, networks).
OUTPUT_FILES_RULE = (
    "Save outputs in the working directory under short descriptive file names: figures as "
    "PNG; tables as CSV or TSV with one header row (columns such as log2FC and p-values "
    "under their usual names); protein structures as PDB or mmCIF and small molecules as SDF; "
    "networks and pathways as SIF (source, interaction, target per line) or JSON "
    '{"nodes": [{"id": ...}], "edges": [{"source": ..., "target": ...}]}.'
)


# Plain names of the verifier's gates, for the writer and the guard log.
GATE_NAMES = {
    "replicated": "replication on a bootstrap resample",
    "stats_ok": "hypothesis test p < alpha",
    "figures_ok": "figure review",
    "skeptic": "sceptical review",
    "multiplicity": "multiple-testing correction",
    "held_out": "held-out re-test",
}

# Shared by both script contracts (sandbox and workspace): what the verifier relies on.
TEST_RULES = (
    "p_value is always required. For a 'difference' test it comes from a test of the null "
    "of no effect; for an 'equivalence' test it must come from a TOST equivalence test "
    "(H0: |estimate - reference| >= tolerance), so a small p_value means agreement is shown. "
    f"If a file named '{REPLICATE_FILE}' exists, it is a JSON object with an integer 'seed': "
    "before computing anything, draw a bootstrap resample (with replacement, same size) of "
    "the independent experimental units (rows, samples, patients, cells or simulation "
    "replicates) with a RNG seeded by it, then run the identical analysis on the resample; "
    "this is how the result is replicated, so never ignore the file. "
    f"If a file named '{SEALED_MANIFEST}' exists, it lists held-out evaluation files: repeat "
    "the same hypothesis test on them and report its metrics with the prefix 'sealed_', "
    "including 'sealed_<primary key>' and 'sealed_p_value'."
)


def profile_tools(profile: ScientistProfile, config: ScientistConfig) -> str:
    """What the planner may assume an experiment can use.

    The offline executors have exactly the profile's packages. An E2B session runs in the
    plato-lab template, where the engineer also has its command-line tools and may install
    more and download public data before the recorded (offline) run."""
    packages = "/".join(profile.packages)
    if config.executor != "e2b":
        return packages
    return (
        f"{packages} and the plato-lab sandbox toolset (samtools/bcftools/GATK and the "
        "sequencing tools, RDKit and Open Babel, HMMER, MMseqs2, Foldseek and DSSP, gseapy "
        "and igraph, AutoDock Vina, OpenMM, LAMMPS, xtb and Psi4, R with Bioconductor), "
        "plus anything the engineer installs or downloads from a public database before "
        "the recorded run"
    )


def code_rules(profile: ScientistProfile, config: ScientistConfig) -> str:
    packages = ", ".join(profile.packages)
    gpu = (
        " A CUDA GPU is available: torch is installed; move tensors to 'cuda' and fall back "
        "to CPU when torch.cuda.is_available() is false."
        if config.executor == "modal" and config.gpu
        else ""
    )
    return (
        f"Rules for the script: it runs offline with {packages} (nothing else is installed).{gpu} "
        f"It must read an integer seed from the file '{SEED_FILE}' and seed every RNG "
        "with it; it may read the provided dataset files from the working directory; "
        f"{OUTPUT_FILES_RULE} It must finish {experiment_limits_text(config)}; "
        f"its last line of output must be '{METRICS_MARKER} ' followed by a JSON object of numeric "
        "metrics that includes the primary metric under exactly its given key, and its standard "
        "error under '<key>_se' when the metric is a Monte Carlo or sample estimate. "
        f"{TEST_RULES}" + (f" {profile.guidance}" if profile.guidance else "")
    )


# Output files kept per experiment run beyond figures: tables, structures, networks and
# documents, so readers can chart, browse and view them in 2D/3D. Bounded per run so one
# chatty script cannot bloat the evidence store (each file is already at most 1 MiB).
DATA_FILE_SUFFIXES = (
    ".csv",
    ".tsv",
    ".json",
    ".txt",
    ".pdf",
    ".pdb",
    ".cif",
    ".mmcif",
    ".sdf",
    ".mol",
    ".mol2",
    ".xyz",
    ".sif",
    ".graphml",
)
MAX_DATA_FILES = 16
MAX_DATA_BYTES = 6 * 1_048_576
MAX_PLOTS = 12


async def store_outputs(
    store: Any, node_id: uuid.UUID, files: dict[str, bytes]
) -> None:
    """Record a run's figures as ``plot_png`` and its data outputs as ``data_file``.

    Figures come first (they feed the figure critique), then data files smallest first
    so a size budget keeps as many as possible; names are recorded with each file."""
    plots = [(n, d) for n, d in sorted(files.items()) if n.lower().endswith(".png")]
    for name, data in plots[:MAX_PLOTS]:
        await store.add_evidence(
            node_id, "plot_png", data, approval_actor="model", file_name=name
        )
    data_files = sorted(
        (
            (n, d)
            for n, d in files.items()
            if n.lower().endswith(DATA_FILE_SUFFIXES) and d and valid_file_name(n)
        ),
        key=lambda item: (len(item[1]), item[0]),
    )
    budget = MAX_DATA_BYTES
    for name, data in data_files[:MAX_DATA_FILES]:
        if len(data) > budget:
            break
        budget -= len(data)
        await store.add_evidence(
            node_id, "data_file", data, approval_actor="system", file_name=name
        )


async def _run_code(
    ctx: ScientistContext,
    campaign_id: uuid.UUID,
    code: str,
    seed: int,
    datasets: dict[str, bytes],
    extra: dict[str, bytes] | None = None,
    setup: str | None = None,
) -> SandboxResult:
    if ctx.config.executor == "e2b":
        return await _run_recipe(ctx, campaign_id, code, seed, datasets, extra, setup)
    seconds = int(ctx.config.sandbox.wall_seconds)
    await ctx.store.reserve_gpu_seconds(campaign_id, seconds)
    result = None
    try:
        result = await run_experiment(
            ctx.config,
            code,
            inputs={**datasets, **(extra or {}), SEED_FILE: str(seed).encode()},
        )
        return result
    finally:
        used = round(result.duration_seconds) if result else 0
        await ctx.store.settle_gpu_seconds(campaign_id, seconds, used)


async def _run_recipe(
    ctx: ScientistContext,
    campaign_id: uuid.UUID,
    code: str,
    seed: int,
    datasets: dict[str, bytes],
    extra: dict[str, bytes] | None,
    setup: str | None,
) -> SandboxResult:
    """Record-grade run in a fresh E2B sandbox: setup (online), then experiment (offline)."""
    from .workspace import run_recipe

    cfg = ctx.config
    reserved = cfg.workspace_setup_seconds + cfg.workspace_run_seconds
    await ctx.store.reserve_gpu_seconds(campaign_id, reserved)
    started = time.monotonic()
    try:
        return await run_recipe(
            ctx.workspace_backends(),
            code=code,
            setup=setup,
            inputs={**datasets, **(extra or {}), SEED_FILE: str(seed).encode()},
            setup_seconds=cfg.workspace_setup_seconds,
            run_seconds=cfg.workspace_run_seconds,
            metadata={"campaign": str(campaign_id), "seed": str(seed)},
        )
    finally:
        await ctx.store.settle_gpu_seconds(
            campaign_id, reserved, round(time.monotonic() - started)
        )


_WORKSPACE_RULES = (
    "The recorded experiment is one Python script run as 'python experiment.py' in a fresh "
    "sandbox with the network cut off, after setup.sh (your recorded installs and downloads) "
    "has rebuilt the environment with network access. It may call command-line tools through "
    f"subprocess and read the provided dataset files and downloaded data; it must read an "
    f"integer seed from '{SEED_FILE}' and seed every RNG (and any tool that takes a seed) with it; "
    f"{OUTPUT_FILES_RULE} Its last "
    f"line of output must be '{METRICS_MARKER} ' followed by a JSON object of numeric metrics "
    "that includes the primary metric under exactly its given key, and its standard error under "
    "'<key>_se' when the metric is a Monte Carlo or sample estimate. " + TEST_RULES
)


async def _workspace_attempt(
    ctx: ScientistContext,
    campaign_id: uuid.UUID,
    intent: dict[str, Any],
    worker_id: str,
    spec: dict[str, Any],
    datasets: dict[str, bytes],
    nonce: str,
) -> tuple[str, str | None, SandboxResult | None, dict[str, Any] | None]:
    """The research engineer works in a live E2B workspace until a submission (a fresh,
    offline re-run of its recipe) prints the required metrics."""
    from .workspace import SessionLimits, Workspace, run_session
    from .workspace.lab import LAB_SUMMARY

    store, cfg = ctx.store, ctx.config
    profile = await campaign_profile(ctx, campaign_id)
    state: dict[str, Any] = {"code": "", "setup": None, "result": None, "metrics": None}
    submissions = 0
    workspace: Workspace | None = None

    async def on_submit(code: str, setup: str) -> tuple[str, bool, Any]:
        nonlocal submissions
        if submissions >= cfg.max_code_attempts:
            return (
                "submission limit reached; no further runs will be recorded",
                False,
                None,
            )
        submissions += 1
        await store.use_turn(intent["id"], worker_id)
        result = await _run_code(ctx, campaign_id, code, 1, datasets, setup=setup)
        state.update(code=code, setup=setup, result=result)
        metrics = parse_metrics(result.stdout) if result.ok else None
        missing = missing_required_metrics(metrics, spec) if metrics is not None else []
        if metrics is not None and not missing:
            state["metrics"] = metrics
            return (f"Accepted. Recorded metrics: {json.dumps(metrics)}", True, True)
        if submissions >= cfg.max_code_attempts and workspace is not None:
            workspace.exhausted = True
        if missing:
            why = f"the {METRICS_MARKER} line lacks the required keys {missing}"
        elif result.timed_out:
            why = "it timed out"
        elif not result.ok:
            why = f"it exited with code {result.exit_code}"
        else:
            why = f"it did not print a valid {METRICS_MARKER} line"
        return (
            (
                f"Rejected ({submissions}/{cfg.max_code_attempts}): {why}.\n"
                f"stdout (end):\n{result.stdout[-4000:]}\nstderr (end):\n{result.stderr[-4000:]}"
            ),
            False,
            None,
        )

    await store.reserve_gpu_seconds(campaign_id, 60)  # fails fast when compute is spent
    started = time.monotonic()
    backend = await ctx.workspace_backends()(
        timeout_seconds=cfg.workspace_session_seconds,
        purpose="workspace",
        metadata={"campaign": str(campaign_id), "intent": str(intent["id"])},
    )
    lease_error: list[BaseException] = []

    async def keep_lease() -> None:
        while True:
            await asyncio.sleep(max(30, cfg.lease_seconds // 3))
            try:
                await store.heartbeat(
                    intent["id"], worker_id, lease_seconds=cfg.lease_seconds
                )
            # LeaseLost (or any heartbeat failure): stop the session at the next turn.
            except BaseException as exc:  # noqa: BLE001
                lease_error.append(exc)
                return

    async def on_turn(_turn: int) -> None:
        if lease_error:
            raise lease_error[0]

    heartbeat = asyncio.create_task(keep_lease())
    try:
        for name, data in {**datasets, SEED_FILE: b"1"}.items():
            await backend.write_bytes(name, data)
        workspace = Workspace(backend, on_submit=on_submit)
        task = (
            f"Hypothesis: {spec['hypothesis']}\nProtocol: {spec['protocol']}\n"
            f"Primary metric key: {spec['primary_metric']}\n"
            f"Test kind: {spec.get('test_kind', 'difference')}\n"
            f"Success criterion: {spec['success_criterion']}\n"
            f"Dataset files in the workspace root ({backend.workdir}): {sorted(datasets) or 'none'}\n\n"
            f"{LAB_SUMMARY}\n\n{_WORKSPACE_RULES}\n\n"
            + (
                f"{profile.workspace_guidance}\n\n"
                if profile.workspace_guidance
                else ""
            )
            + "Work like a careful computational scientist: inspect the data, install and download "
            "what you need (install_packages and download_file record it in setup.sh), test pieces "
            "with bash, use start_job for anything long, then write experiment.py and call "
            f"submit_experiment. You have at most {cfg.max_code_attempts} submissions and "
            f"{cfg.workspace_max_turns} turns."
        )
        outcome = await run_session(
            model=ctx.model,
            campaign_id=campaign_id,
            system=_system("research engineer", nonce),
            task=task,
            workspace=workspace,
            nonce=nonce,
            limits=SessionLimits(max_turns=cfg.workspace_max_turns),
            on_turn=on_turn,
        )
        if outcome.signals:
            await store.record_guard_event(
                campaign_id,
                "injection",
                "allow",
                {
                    "signals": sorted(set(outcome.signals))[:20],
                    "note": "workspace tool output",
                },
                node_id=intent["id"],
            )
        await store.add_evidence(
            intent["id"],
            "stdout_log",
            "WORKSPACE SESSION "
            + json.dumps(
                {
                    "sandbox": backend.sandbox_id,
                    "turns": outcome.turns,
                    "end": outcome.reason,
                    "submissions": submissions,
                    "actions": workspace.actions[-200:],
                },
                default=str,
            ),
            approval_actor="system",
        )
    finally:
        heartbeat.cancel()
        await backend.close()
        await store.settle_gpu_seconds(
            campaign_id, 60, round(time.monotonic() - started)
        )
    if lease_error:
        raise lease_error[0]
    return state["code"], state["setup"], state["result"], state["metrics"]


async def execute_intent(
    ctx: ScientistContext,
    campaign_id: uuid.UUID,
    intent: dict[str, Any],
    worker_id: str,
) -> None:
    store = ctx.store
    spec = decode_intent_spec(intent["hypothesis_or_spec"])
    await store.heartbeat(
        intent["id"], worker_id, lease_seconds=ctx.config.lease_seconds
    )
    dataset_assets, datasets = await store.dataset_inputs(campaign_id)
    rules = code_rules(await campaign_profile(ctx, campaign_id), ctx.config)
    nonce = new_nonce()
    feedback = ""
    result: SandboxResult | None = None
    code = ""
    metrics: dict[str, Any] | None = None
    setup: str | None = None
    if ctx.config.executor == "e2b":
        code, setup, result, metrics = await _workspace_attempt(
            ctx, campaign_id, intent, worker_id, spec, datasets, nonce
        )
    # The workspace session replaces the write-run-fix loop below (it has its own retries).
    for attempt in range(
        0 if ctx.config.executor == "e2b" else ctx.config.max_code_attempts
    ):
        await store.use_turn(intent["id"], worker_id)
        draft = await ctx.model.structured(
            campaign_id=campaign_id,
            purpose="write_experiment",
            schema=ExperimentCode,
            effort="medium",
            max_tokens=12000,
            system=_system("research engineer", nonce),
            prompt=(
                f"Hypothesis: {spec['hypothesis']}\nProtocol: {spec['protocol']}\n"
                f"Primary metric key: {spec['primary_metric']}\nTest kind: {spec.get('test_kind', 'difference')}\n"
                f"Success criterion: {spec['success_criterion']}\n"
                f"Dataset files: {sorted(datasets) or 'none'}\n\n{rules}\n\n{feedback}"
                "Write the complete script."
            ),
        )
        code = draft.code
        await store.heartbeat(
            intent["id"], worker_id, lease_seconds=ctx.config.lease_seconds
        )
        result = await _run_code(ctx, campaign_id, code, seed=1, datasets=datasets)
        if result.rejected:
            await store.record_guard_event(
                campaign_id,
                "command",
                "deny",
                {"reason": result.rejected, "attempt": attempt},
                node_id=intent["id"],
            )
            feedback = f"The previous script was rejected by the sandbox policy: {result.rejected}\n\n"
            continue
        if not result.network_isolated:
            await store.record_guard_event(
                campaign_id,
                "scope",
                "allow",
                {"note": "network namespace unavailable on host"},
                node_id=intent["id"],
            )
        metrics = parse_metrics(result.stdout) if result.ok else None
        missing = missing_required_metrics(metrics, spec) if metrics is not None else []
        if metrics is not None and not missing:
            break
        if missing:
            metrics = None
            feedback = (
                f"The previous script ran but its {METRICS_MARKER} line lacks the required "
                f"keys {missing}. Print them under exactly those names.\n\n"
            )
            continue
        err = frame_untrusted(
            (result.stderr or result.stdout)[-6000:],
            source="sandbox_output",
            nonce=nonce,
        )
        reason = (
            "timed out"
            if result.timed_out
            else (
                f"exited with code {result.exit_code}"
                if not result.ok
                else f"did not print a valid {METRICS_MARKER} line"
            )
        )
        feedback = (
            f"The previous script {reason}. Output:\n{err.text}\nFix the script.\n\n"
        )

    if metrics is None:  # also covers result is None
        if result is not None and not result.rejected:
            await store.add_evidence(
                intent["id"],
                "stdout_log",
                f"STDOUT\n{result.stdout}\n\nSTDERR\n{result.stderr}",
                approval_actor="system",
            )
        await store.complete_intent(
            intent["id"],
            worker_id,
            "exhausted",
            metrics={
                "error": "no successful run",
                "attempts": ctx.config.max_code_attempts,
            },
        )
        return

    out = frame_untrusted(
        result.stdout[-8000:], source="experiment_stdout", nonce=nonce
    )
    obs = await ctx.model.structured(
        campaign_id=campaign_id,
        purpose="observe",
        schema=Observation,
        effort="low",
        system=_system("experiment analyst", nonce),
        prompt=(
            f"Hypothesis: {spec['hypothesis']}\nSuccess criterion: {spec['success_criterion']}\n"
            f"Measured metrics (authoritative): {json.dumps(metrics)}\n\nRun output:\n{out.text}\n\n"
            "State what was observed. Use only the measured numbers."
        ),
    )
    fact_metrics = {
        **metrics,
        "seed": 1,
        "primary_metric": spec["primary_metric"],
        "test_kind": spec.get("test_kind", "difference"),
        "supports_hypothesis": obs.supports_hypothesis,
        "runtime_seconds": round(result.duration_seconds, 3),
        "network_isolated": result.network_isolated,
        "code_sha256": sha256_hex(code),
        "executor": ctx.config.executor,
    }
    fact_id = await store.record_fact(
        campaign_id,
        intent["id"],
        worker_id,
        title=obs.title,
        observation=obs.observation,
        metrics=fact_metrics,
        anchors=[(d["id"], "dataset_input") for d in dataset_assets],
    )
    await store.add_evidence(
        fact_id, "git_patch", recipe_as_patch(code, setup), approval_actor="model"
    )
    await store.add_evidence(
        fact_id, "stdout_log", result.stdout, approval_actor="system"
    )
    await store_outputs(store, fact_id, result.files)
    for text in obs.follow_up_hints[:2]:
        hint = await store.create_node(
            campaign_id,
            "hint",
            text[:200],
            text,
            dedup_key=spec_dedup_key(text),
            priority=0.6,
        )
        await store.add_edge(
            campaign_id, intent["id"], hint.id, "yields", "follow-up from observation"
        )
    await store.complete_intent(
        intent["id"], worker_id, "verified", metrics={"fact_id": str(fact_id)}
    )


async def run_worker(
    ctx: ScientistContext, campaign_id: uuid.UUID, worker_id: str
) -> int:
    """One swarm member: claim, execute, repeat until the queue is empty."""
    done = 0
    while True:
        intent = await ctx.store.claim_next_intent(
            campaign_id,
            worker_id,
            lease_seconds=ctx.config.lease_seconds,
            max_attempts=ctx.config.max_claim_attempts,
        )
        if intent is None:
            return done
        try:
            await execute_intent(ctx, campaign_id, intent, worker_id)
            done += 1
        except LeaseLost:
            logger.warning(
                "%s lost lease on %s; another worker owns it now",
                worker_id,
                intent["id"],
            )
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
                await ctx.store.complete_intent(
                    intent["id"],
                    worker_id,
                    "exhausted",
                    metrics={"error": str(exc)[:500]},
                )
            except LeaseLost:
                pass


async def experiment_swarm(ctx: ScientistContext, campaign_id: uuid.UUID) -> int:
    workers = [f"{ctx.worker_prefix}-w{i}" for i in range(ctx.config.workers)]
    results = await asyncio.gather(
        *(run_worker(ctx, campaign_id, w) for w in workers), return_exceptions=True
    )
    await ctx.store.exhaust_dead_intents(
        campaign_id, max_attempts=ctx.config.max_claim_attempts
    )
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
    await store.transition_campaign(
        campaign_id, "ablating", from_statuses=["investigating"]
    )
    datasets = await store.dataset_files(campaign_id)
    stats = {"promoted": 0, "refuted": 0, "inconclusive": 0}
    for fact in await store.nodes(campaign_id, node_type="fact", status="open"):
        patches = await store.evidence_contents(fact["id"], "git_patch")
        if not patches:
            continue
        code, setup = recipe_from_patch(patches[0].decode("utf-8"))
        primary = fact["metrics"].get("primary_metric")
        original = fact["metrics"].get(primary) if primary else None

        # Replication: a new seed plus a bootstrap resample of the independent units, so a
        # deterministic analysis is perturbed too (a new seed alone changes nothing there).
        rep = await _run_code(
            ctx,
            campaign_id,
            code,
            seed=2,
            datasets=datasets,
            extra={REPLICATE_FILE: json.dumps({"seed": 2}).encode()},
            setup=setup,
        )
        rep_metrics = parse_metrics(rep.stdout) if rep.ok else None
        replicated, replication_note = (
            replication_outcome(
                primary,
                fact["metrics"],
                rep_metrics,
                ctx.config.replication_rel_tolerance,
            )
            if primary
            else (False, "no primary metric")
        )
        await store.add_evidence(
            fact["id"],
            "stdout_log",
            f"REPLICATION seed=2 bootstrap ({replication_note})\n{rep.stdout}\n{rep.stderr}",
        )

        # Figure critique with the vision model.
        figure_scores = []
        for png in (await store.evidence_contents(fact["id"], "plot_png"))[:2]:
            critique = await ctx.model.structured(
                campaign_id=campaign_id,
                purpose="figure_critique",
                schema=FigureCritique,
                effort="low",
                system=_system("figure reviewer", new_nonce()),
                images=[png],
                prompt=f"Critique this figure for the claim: {fact['title']}. Metrics: {json.dumps(fact['metrics'])[:500]}",
            )
            score = _clamp01(critique.quality_score)
            figure_scores.append(score)
            await store.add_evidence(
                fact["id"],
                "vlm_critique",
                critique.model_dump_json(),
                approval_actor="model",
                vlm_quality_score=round(score, 2),
            )

        # Both kinds gate on p < alpha: for 'difference' it rejects "no effect", for
        # 'equivalence' (TOST) it rejects "outside the tolerance". A claim without a p_value
        # was never tested, so it cannot pass. The campaign-wide multiplicity correction
        # (correct_for_multiple_testing) re-checks this gate once every test is in.
        test_kind = fact["metrics"].get("test_kind", "difference")
        p_value = _number(fact["metrics"].get("p_value"))
        stats_ok = p_value is not None and p_value < ctx.config.alpha
        nonce = new_nonce()
        log = await store.evidence_contents(fact["id"], "stdout_log")
        framed_log = frame_untrusted(
            log[0].decode("utf-8", "replace")[-5000:] if log else "",
            source="stdout",
            nonce=nonce,
        )
        verdict = await ctx.model.structured(
            campaign_id=campaign_id,
            purpose="skeptic",
            schema=SkepticVerdict,
            effort="high",
            system=_system("skeptical reviewer", nonce),
            prompt=(
                f"Candidate fact: {fact['title']}\n{fact['hypothesis_or_spec']}\n"
                f"Metrics (seed 1): {json.dumps(fact['metrics'])}\n"
                f"Replication (seed 2, bootstrap resample): {json.dumps(rep_metrics)} -> "
                f"replicated={replicated} ({replication_note})\n"
                f"Test kind: {test_kind} (p_value is "
                f"{'a TOST equivalence p' if test_kind == 'equivalence' else 'a no-effect test p'}); "
                f"statistical gate p < {ctx.config.alpha}: {stats_ok}\n"
                f"Figure scores: {figure_scores}\nRun log:\n{framed_log.text}\n\n"
                "Decide whether this is a reliable finding worth reporting. Reject anything "
                "that does not replicate, overstates the numbers, or could be an artefact."
            ),
        )
        gates = {
            "replicated": replicated,
            "stats_ok": stats_ok,
            "figures_ok": not figure_scores
            or sum(figure_scores) / len(figure_scores) >= ctx.config.min_figure_score,
            "skeptic": verdict.decision == "promote"
            and verdict.confidence >= ctx.config.min_promote_confidence,
        }
        confidence = _clamp01(verdict.confidence)
        outcome = classify_fact(gates, fact["metrics"].get("supports_hypothesis"))
        if outcome == "verified":
            finding = await store.create_node(
                campaign_id,
                "finding",
                verdict.finding_title,
                verdict.finding_statement,
                dedup_key=spec_dedup_key(verdict.finding_title),
                status="verified",
                confidence_score=round(confidence, 3),
                metrics={
                    "primary_metric": primary,
                    primary: original,
                    "replication": rep_metrics,
                    **gates,
                }
                if primary
                else gates,
            )
            await store.add_edge(
                campaign_id, fact["id"], finding.id, "proves", verdict.rationale[:2000]
            )
            await store.set_node_status(
                fact["id"],
                "verified",
                confidence_score=round(confidence, 3),
                metrics={
                    "gates": gates,
                    "replication": rep_metrics,
                    "replication_note": replication_note,
                },
            )
            stats["promoted"] += 1
        else:
            # refuted: replicated, significant and against the hypothesis. Everything else
            # that failed a gate is inconclusive and is never reported as a negative result.
            await store.set_node_status(
                fact["id"],
                outcome,
                confidence_score=round(confidence, 3),
                metrics={
                    "gates": gates,
                    "replication": rep_metrics,
                    "replication_note": replication_note,
                    "skeptic_rationale": verdict.rationale[:1000],
                },
            )
            stats[outcome] += 1
    rounds = await rounds_completed(ctx, campaign_id) + 1
    await store.set_node_status(
        await _root_goal(ctx, campaign_id), "open", metrics={"rounds_completed": rounds}
    )
    await store.transition_campaign(
        campaign_id, "investigating", from_statuses=["ablating"]
    )
    return {**stats, "rounds_completed": rounds}


# ---------------------------------------------------------------------------
# 5. Sealed evaluation, then grounded manuscript + peer review
# ---------------------------------------------------------------------------


async def correct_for_multiple_testing(
    ctx: ScientistContext, campaign_id: uuid.UUID
) -> dict[str, Any]:
    """Re-check the statistical gate across every hypothesis the campaign tested.

    Each fact was gated at p < alpha on its own, but a campaign tests up to
    ``intents_per_round * max_rounds`` hypotheses; uncorrected, the chance of at least one
    false positive among 12 true nulls is 1 - 0.95**12 = 46%. Once all tests are in, the
    family is every fact that reached the verifier (whatever its verdict, so the family is
    not selected by outcome), and each p_value is adjusted (Benjamini-Hochberg by default).
    A verified or refuted fact whose adjusted p is not below alpha becomes inconclusive,
    and so does every finding it proved. Deterministic and idempotent: it reads only the
    raw p-values, so running it again (sealed phase, then writing) changes nothing."""
    store, cfg = ctx.store, ctx.config
    tested = [
        f
        for f in await store.nodes(campaign_id, node_type="fact")
        if f["status"] in ("verified", "refuted", "inconclusive")
        and isinstance((f["metrics"] or {}).get("gates"), dict)
    ]
    raw = {
        f["id"]: p
        for f in tested
        if (p := _number(f["metrics"].get("p_value"))) is not None
    }
    adjusted = adjusted_p_values(raw, cfg.multiplicity)
    proved = await store.proved_findings([f["id"] for f in tested])
    demoted: list[str] = []
    for f in tested:
        p_adj = adjusted.get(f["id"])
        ok = p_adj is not None and p_adj < cfg.alpha
        info = {
            "method": cfg.multiplicity,
            "family_size": len(raw),
            "alpha": cfg.alpha,
            "p_adjusted": None if p_adj is None else round(p_adj, 6),
        }
        gates = {**f["metrics"]["gates"], "multiplicity": ok}
        status = f["status"]
        if status in ("verified", "refuted") and not ok:
            status = "inconclusive"
            demoted.append(str(f["id"]))
            for finding_id in proved.get(f["id"], []):
                await store.set_node_status(
                    finding_id,
                    "inconclusive",
                    metrics={"multiplicity": ok, "multiple_testing": info},
                )
        await store.set_node_status(
            f["id"], status, metrics={"gates": gates, "multiple_testing": info}
        )
    if demoted:
        await store.record_guard_event(
            campaign_id,
            "scope",
            "deny",
            {
                "note": "multiple-testing correction: adjusted p not below alpha",
                "method": cfg.multiplicity,
                "family_size": len(raw),
                "facts": demoted,
            },
        )
    return {"family_size": len(raw), "demoted": len(demoted)}


async def sealed_evaluation(ctx: ScientistContext, campaign_id: uuid.UUID) -> int:
    store = ctx.store
    await store.transition_campaign(
        campaign_id, "sealed_eval", from_statuses=["investigating", "ablating"]
    )
    # Before spending held-out runs: findings that do not survive the correction are out.
    await correct_for_multiple_testing(ctx, campaign_id)
    sealed = [
        a
        for a in await store.visible_assets(campaign_id, asset_types=["dataset"])
        if a["is_sealed_eval"] or a["access_mode"] == "sealed_eval_only"
    ]
    if not sealed:
        return 0
    datasets = await store.dataset_files(campaign_id)  # now includes held-out files
    manifest = json.dumps(
        {"held_out_files": [a["metadata"].get("file_name") for a in sealed]}
    ).encode()
    evaluated = 0
    for finding in await store.nodes(
        campaign_id, node_type="finding", status="verified"
    ):
        trace = await store.trace_provenance(finding["id"], max_depth=2)
        facts = [n for n in trace["nodes"] if n["node_type"] == "fact"]
        if not facts:
            continue
        fact = facts[0]
        patches = await store.evidence_contents(fact["id"], "git_patch")
        if not patches:
            continue
        code, setup = recipe_from_patch(patches[0].decode())
        run = await _run_code(
            ctx,
            campaign_id,
            code,
            seed=1,
            datasets=datasets,
            extra={SEALED_MANIFEST: manifest},
            setup=setup,
        )
        sealed_metrics = {
            k: v
            for k, v in (parse_metrics(run.stdout) or {}).items()
            if k.startswith("sealed_")
        }
        confirmed, reason = held_out_outcome(
            fact["metrics"] or {}, run.ok, sealed_metrics, ctx.config.alpha
        )
        await store.add_evidence(
            finding["id"],
            "sealed_eval_json",
            json.dumps(
                {
                    "ok": run.ok,
                    "metrics": sealed_metrics,
                    "confirmed": confirmed,
                    "reason": reason,
                },
                sort_keys=True,
            ),
        )
        for asset in sealed:
            await store.link_anchor(finding["id"], asset["id"], "target_benchmark")
        # The held-out data has the last word: a finding it does not confirm is demoted.
        status = "verified" if confirmed else "inconclusive"
        await store.set_node_status(
            finding["id"],
            status,
            metrics={
                "sealed_eval": sealed_metrics or None,
                "held_out": confirmed,
                "held_out_reason": reason,
            },
        )
        if not confirmed:
            await store.set_node_status(
                fact["id"],
                "inconclusive",
                metrics={
                    "gates": {
                        **(fact["metrics"] or {}).get("gates", {}),
                        "held_out": False,
                    },
                    "held_out_reason": reason,
                },
            )
        evaluated += 1
    return evaluated


_LATEX_ESCAPES = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
}


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
            "author": " and ".join(
                latex_escape(a) for a in (meta.get("authors") or [])[:10]
            )
            or "Unknown",
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


def _finding_row(f: dict[str, Any]) -> str:
    m = f.get("metrics") or {}
    key = m.get("primary_metric")
    value = m.get(key) if isinstance(key, str) else None
    shown = f"{value:.6g}" if isinstance(value, (int, float)) else "--"
    conf = f["confidence_score"]
    conf_shown = f"{float(conf):.2f}" if conf is not None else "--"
    return (
        f"{latex_escape(f['title'])} & \\texttt{{{latex_escape(key or '--')}}} & "
        f"{shown} & {conf_shown} \\\\"
    )


def assemble_latex(ms: Manuscript, findings: list[dict[str, Any]]) -> str:
    # The summary table lists verified findings only; with none, it is omitted rather
    # than printed empty (the text then reports negative and preliminary results).
    table = (
        "\\begin{table}[h]\\centering\n\\begin{tabular}{p{0.5\\linewidth}llr}\n"
        "Finding & Primary metric & Value & Confidence \\\\\n\\hline\n"
        + "\n".join(_finding_row(f) for f in findings)
        + "\n\\end{tabular}\n\\caption{Verified findings: primary metric and skeptic confidence.}\n\\end{table}\n"
        if findings
        else ""
    )
    return (
        "\\documentclass{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage{amsmath,amssymb}\n"
        "\\usepackage{hyperref}\n"
        f"\\title{{{latex_escape(ms.title)}}}\n\\author{{Plato autonomous research swarm}}\n"
        "\\begin{document}\n\\maketitle\n"
        f"\\begin{{abstract}}\n{ms.abstract}\n\\end{{abstract}}\n"
        f"\\section{{Introduction}}\n{ms.introduction}\n"
        f"\\section{{Methods}}\n{ms.methods}\n"
        f"\\section{{Results}}\n{ms.results}\n"
        f"{table}"
        f"\\section{{Discussion}}\n{ms.discussion}\n"
        f"\\section{{Limitations}}\n{ms.limitations}\n"
        "\\bibliographystyle{plain}\n\\bibliography{references}\n\\end{document}\n"
    )


def citation_report(
    citable: list[dict[str, Any]],
    keys: dict[str, dict[str, Any]],
    root_metrics: dict[str, Any],
) -> dict[str, Any]:
    """What the citation checks found: per cited paper, and the papers kept out."""
    by_id = {p["id"]: k for k, p in keys.items()}
    cited = []
    for p in citable:
        meta = p["metadata"] or {}
        check = meta.get("citation_check") or {"status": "unchecked"}
        cited.append(
            {
                "key": by_id.get(p["id"]),
                "title": meta.get("title") or p["canonical_name"],
                "doi": meta.get("doi"),
                "arxiv_id": meta.get("arxiv_id"),
                "retrieved_via": meta.get("retrieved_via"),
                "status": check.get("status"),
                "retracted": bool(check.get("retracted")),
                "doi_resolved": check.get("doi_resolved"),
                "arxiv_resolved": check.get("arxiv_resolved"),
                "issues": check.get("issues") or [],
            }
        )
    statuses: dict[str, int] = {}
    for c in cited:
        statuses[c["status"]] = statuses.get(c["status"], 0) + 1
    return {
        "cited": cited,
        "cited_by_status": statuses,
        "retrieved_by_status": root_metrics.get("citation_checks") or {},
        "excluded": root_metrics.get("papers_excluded") or [],
        "sources_searched": root_metrics.get("retrieval_sources") or [],
        "profile": root_metrics.get("profile") or "general",
    }


class DraftSink:
    """Throttled writer of the streaming manuscript to ``plato.manuscript_drafts``.

    The model emits the paper token by token; persisting every delta would be thousands
    of writes, so the sink saves at most once per ``interval`` seconds and ``flush`` saves
    the last text. Failures are logged, never raised: the live view is best effort."""

    def __init__(
        self, store: DualGraphStore, campaign_id: uuid.UUID, interval: float = 1.5
    ):
        self._store, self._cid, self._interval = store, campaign_id, interval
        self.stage, self._last, self._text = "drafting", 0.0, ""

    async def stage_to(self, stage: str, body: str | None = None) -> None:
        self.stage = stage
        if body is not None:
            self._text = body
        await self.flush()

    async def __call__(self, text: str) -> None:
        self._text = text
        now = asyncio.get_running_loop().time()
        if now - self._last >= self._interval:
            await self.flush()

    async def flush(self) -> None:
        self._last = asyncio.get_running_loop().time()
        try:
            await self._store.save_draft(self._cid, self.stage, self._text)
        except Exception:
            logger.warning("could not save manuscript draft", exc_info=True)


async def write_manuscript(
    ctx: ScientistContext, campaign_id: uuid.UUID
) -> dict[str, Any]:
    store = ctx.store
    await store.transition_campaign(
        campaign_id,
        "writing",
        from_statuses=["sealed_eval", "investigating", "ablating"],
    )
    campaign = await store.get_campaign(campaign_id)
    if campaign["status"] != "writing":
        # Never spend tokens on a paper whose completion transition cannot succeed.
        raise RuntimeError(
            f"cannot write manuscript for campaign {campaign_id} in status {campaign['status']!r}"
        )
    root_id = await _root_goal(ctx, campaign_id)
    root_metrics = (await store.get_node(root_id))["metrics"] or {}
    # Idempotent; also covers the budget path, which skips the sealed phase.
    await correct_for_multiple_testing(ctx, campaign_id)
    findings = await store.nodes(campaign_id, node_type="finding", status="verified")
    facts = await store.nodes(campaign_id, node_type="fact")
    refuted = [f for f in facts if f["status"] == "refuted"]
    # Tested but failed a check without contradicting the hypothesis: reported as
    # inconclusive, with the check that failed, never as a negative result.
    inconclusive = [f for f in facts if f["status"] == "inconclusive"]
    # Observations that ran but were never reviewed (the budget ran out first). The writer may
    # report them only as preliminary, so a budget-limited campaign still documents them.
    preliminary = [
        f for f in facts if f["status"] not in ("refuted", "verified", "inconclusive")
    ]

    # Ground the paper in provenance: only papers anchored somewhere in the graph are citable.
    papers = {
        a["id"]: a
        for a in await store.visible_assets(campaign_id, asset_types=["paper"])
    }
    hints = await store.nodes(campaign_id, node_type="hint")
    anchored = await store.anchored_asset_ids(
        [f["id"] for f in findings]
    ) | await store.anchored_asset_ids([h["id"] for h in hints], max_depth=0)

    # A retrieved paper is citable only with an abstract: every citing claim is checked
    # against it, so without one each such claim would be "unsupported" by construction.
    # References the researcher supplied are always citable (claims citing one without an
    # abstract are marked "unchecked", not unsupported).
    def user_supplied(p: dict[str, Any]) -> bool:
        return bool((p["metadata"] or {}).get("user_supplied"))

    def checkable(p: dict[str, Any]) -> bool:
        return user_supplied(p) or has_abstract((p["metadata"] or {}).get("abstract"))

    citable = [
        p
        for i, p in papers.items()
        if checkable(p) and (i in anchored or user_supplied(p))
    ] or [p for p in papers.values() if checkable(p)][:10]
    no_abstract = sorted(
        p["canonical_name"][:200]
        for i, p in papers.items()
        if i in anchored and not checkable(p)
    )
    if no_abstract:
        await store.record_guard_event(
            campaign_id,
            "scope",
            "deny",
            {
                "note": "not citable: no abstract to check claims against",
                "papers": no_abstract,
            },
        )
    keys = {_bib_key(p): p for p in citable}
    bib = build_bibtex(citable)

    nonce = new_nonce()
    finding_text = (
        "\n".join(
            f"- {f['title']}: {f['hypothesis_or_spec']} (confidence {f['confidence_score']}, metrics {json.dumps(f['metrics'])[:400]})"
            for f in findings
        )
        or "(no finding passed verification)"
    )
    refs = "\n".join(
        frame_untrusted(
            f"{k}: {p['canonical_name']} ({p['metadata'].get('year')})",
            source=k,
            nonce=nonce,
        ).text
        for k, p in keys.items()
    )

    def _observations(nodes: list[dict[str, Any]], *, checks: bool = False) -> str:
        def failed(n: dict[str, Any]) -> str:
            gates = (n["metrics"] or {}).get("gates") or {}
            names = [GATE_NAMES.get(k, k) for k, v in gates.items() if not v]
            return f"; failed checks: {', '.join(names)}" if checks and names else ""

        return (
            "\n".join(
                f"- {n['title']}: {n['hypothesis_or_spec']} (metrics {json.dumps(n['metrics'])[:400]}{failed(n)})"
                for n in nodes[:20]
            )
            or "(none)"
        )

    evidence_text = (
        f"Verified findings (passed replication and skeptic review):\n{finding_text}\n\n"
        f"Refuted hypotheses (replicated, statistically significant after the multiple-testing "
        f"correction, and against the stated hypothesis):\n{_observations(refuted)}\n\n"
        f"Inconclusive results (measured, but a verification check failed, so they support "
        f"neither the hypothesis nor its negation):\n{_observations(inconclusive, checks=True)}\n\n"
        f"Preliminary observations (measured but not yet replicated or reviewed):\n{_observations(preliminary)}"
    )
    base_prompt = (
        f"Research question: {campaign['research_question']}\n\n{evidence_text}\n\n"
        f"Citable references (use \\cite{{key}} with these keys only):\n{refs}\n\n"
        "Write each section as LaTeX body text (no preamble). Report numbers exactly as given. Present "
        "verified findings as results; present refuted hypotheses as negative results, with the measured "
        "values; present inconclusive results only as inconclusive, with the measured values and the "
        "check that failed, never as evidence for or against the hypothesis (a failed check is not a "
        "negative result); present preliminary observations only as preliminary, labelled "
        "unreplicated. State "
        "clearly that experiments are computational and automated, and what was not established."
    )
    # The cap covers adaptive thinking plus the full LaTeX body; at 16k the writer
    # truncated once it was given every measured result.
    draft = DraftSink(store, campaign_id)
    await draft.stage_to("drafting", "")
    ms = await ctx.model.structured(
        campaign_id=campaign_id,
        purpose="manuscript",
        schema=Manuscript,
        effort="high",
        max_tokens=MANUSCRIPT_MAX_TOKENS,
        system=_system("scientific writer", nonce),
        prompt=base_prompt,
        on_text=draft,
    )
    await draft.stage_to("reviewing", ms.model_dump_json())
    # Review and revision improve the draft but must never cost the campaign its paper:
    # if any step fails (truncation, refusal, budget) the draft is kept and the failure logged.
    review_failures: list[dict[str, str]] = []

    async def best_effort(stage: str, call):
        try:
            return await call
        except (ModelOutputError, ModelRefusal, BudgetExceeded) as exc:
            review_failures.append({"stage": stage, "error": str(exc)[:500]})
        except Exception as exc:
            logger.exception("%s failed for campaign %s", stage, campaign_id)
            review_failures.append(
                {"stage": stage, "error": f"{type(exc).__name__}: {exc}"[:500]}
            )
        return None

    # Claim-to-evidence matrix: every cited sentence checked against the cited abstract.
    matrix = await best_effort(
        "evidence_matrix", build_evidence_matrix(ctx.model, campaign_id, ms, keys)
    )
    # Four single-angle reviewers (methodology, statistics, novelty, writing) in parallel;
    # the chair below consolidates them with the evidence into one decision.
    panel = await best_effort(
        "review_panel", run_review_panel(ctx.model, campaign_id, ms, evidence_text)
    )
    review: PeerReview | None = await best_effort(
        "peer_review",
        ctx.model.structured(
            campaign_id=campaign_id,
            purpose="peer_review",
            schema=PeerReview,
            effort="high",
            system=_system("handling editor for a top venue", nonce),
            max_tokens=16000,
            prompt=(
                "Write the consolidated review of this manuscript. Weigh the four reviewer "
                "reports and the citation audit against the evidence. Judge the paper claim "
                "by claim: quote each claim exactly as written, check it against the "
                "evidence (numbers, uncertainty, replication, test kind), and approve, ask "
                "to revise, or reject it. Approve only what the evidence establishes as "
                "stated; a number that is not in the evidence is rejected. Required "
                "changes must be concrete edits.\n\n"
                f"Evidence:\n{evidence_text}\n\n"
                f"Reviewer reports:\n{panel_digest(panel or {})}\n\n"
                f"Citation audit (claims whose cited abstract does not support them):\n"
                f"{matrix_digest(matrix or {})}\n\n"
                f"Manuscript:\n{ms.model_dump_json()}"
            ),
        ),
    )
    record = review_record(review, ms) if review is not None else None
    changes = (
        list(review.required_changes)
        if review and review.decision in ("major_revision", "reject")
        else []
    )
    # Citation integrity is not negotiable: unsupported or contradicted citations are
    # always revised, whatever the overall decision.
    changes += matrix_required_changes(matrix or {})
    revised = False
    if changes:
        await draft.stage_to("revising")
        new_ms = await best_effort(
            "manuscript_revision",
            ctx.model.structured(
                campaign_id=campaign_id,
                purpose="manuscript_revision",
                schema=Manuscript,
                effort="high",
                max_tokens=MANUSCRIPT_MAX_TOKENS,
                system=_system("scientific writer", nonce),
                prompt=base_prompt
                + "\n\nRevise the manuscript to address:\n"
                + "\n".join(f"- {c}" for c in changes),
                on_text=draft,
            ),
        )
        if new_ms is not None:
            ms, revised = new_ms, True
            # The review judged the first draft; re-check each claim in the revision so
            # the verdicts shown describe the paper as published.
            if record is not None:
                check = await best_effort(
                    "peer_review_check",
                    check_revision(ctx.model, campaign_id, record, ms, evidence_text),
                )
                record = apply_revision(record, check, ms)
            # The stored matrix must describe the paper as published.
            matrix = (
                await best_effort(
                    "evidence_matrix_final",
                    build_evidence_matrix(ctx.model, campaign_id, ms, keys),
                )
                or matrix
            )
    if review_failures:
        await store.record_guard_event(
            campaign_id,
            "scope",
            "deny",
            {
                "note": "kept the latest draft; a review step failed",
                "failures": review_failures,
            },
        )

    # Whatever the revision did, no citation the final audit found unsupported or
    # contradicted reaches the published paper.
    stripped: list[dict[str, Any]] = []
    if matrix is not None:
        ms, matrix, stripped = strip_unsupported_citations(ms, matrix)
        if stripped:
            await store.record_guard_event(
                campaign_id,
                "scope",
                "deny",
                {
                    "note": "removed citations the cited abstract does not support",
                    "citations": stripped[:40],
                },
            )

    dropped: list[str] = []
    cleaned = {}
    for name in Manuscript.model_fields.keys() - {"title"}:
        cleaned[name], bad = _filter_citations(getattr(ms, name), set(keys))
        dropped += bad
    ms = ms.model_copy(update=cleaned)
    if dropped:
        await store.record_guard_event(
            campaign_id,
            "scope",
            "deny",
            {
                "note": "removed citations not grounded in the graph",
                "keys": sorted(set(dropped)),
            },
        )
    await draft.stage_to("final", ms.model_dump_json())
    tex = assemble_latex(ms, findings)
    await store.add_evidence(root_id, "latex_section", tex, approval_actor="model")
    await store.add_evidence(root_id, "bibtex", bib, approval_actor="system")
    if record is not None:
        if not revised:
            record = apply_revision(record, None, ms)
        await store.add_evidence(
            root_id,
            "peer_review",
            json.dumps(record, sort_keys=True),
            approval_actor="model",
        )
    if matrix is not None:
        await store.add_evidence(
            root_id,
            "evidence_matrix",
            json.dumps(matrix, sort_keys=True),
            approval_actor="model",
        )
    if panel is not None:
        await store.add_evidence(
            root_id,
            "review_panel",
            json.dumps(panel, sort_keys=True),
            approval_actor="model",
        )
    await store.add_evidence(
        root_id,
        "citation_report",
        json.dumps(citation_report(citable, keys, root_metrics), sort_keys=True),
        approval_actor="system",
    )
    # The question counts as answered only when a finding passed verification.
    await store.set_node_status(
        root_id,
        "verified" if findings else "exhausted",
        metrics={
            "findings": len(findings),
            "review_decision": review.decision if review else "not_reviewed",
            "revised": revised,
            "unsupported_claim_rate": matrix.get("unsupported_claim_rate")
            if matrix
            else None,
            "unsupported_claim_rate_before_removal": matrix.get(
                "unsupported_claim_rate_before_removal",
                matrix.get("unsupported_claim_rate"),
            )
            if matrix
            else None,
            "citations_removed": len(stripped),
            "panel_max_severity": panel.get("max_severity") if panel else None,
        },
    )
    await store.transition_campaign(campaign_id, "completed", from_statuses=["writing"])
    return {
        "findings": len(findings),
        "review": review.decision if review else "not_reviewed",
        "revised": revised,
        "unsupported_claim_rate": matrix.get("unsupported_claim_rate")
        if matrix
        else None,
    }
