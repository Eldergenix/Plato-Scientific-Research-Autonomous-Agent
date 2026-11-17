"""LangGraph wiring for the autonomous scientist.

    START -> (resume router) -> literature_scout -> experiment_planner -> experiment_swarm
          -> verifier -> (round router) -> experiment_planner ... | sealed_evaluation
          -> write_manuscript -> END

The graph state is deliberately tiny (campaign id + loop counters). Durable research
state lives in the Postgres dual graph, so no LangGraph checkpointer is needed: a
restarted run enters through ``resume`` and continues from the campaign status.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .db.store import TERMINAL_STATUSES, BudgetExceeded
from .llm import ModelOutputError, ModelRefusal
from .nodes import (
    ScientistConfig,
    ScientistContext,
    experiment_planner,
    experiment_swarm,
    literature_scout,
    rounds_completed,
    sealed_evaluation,
    verifier,
    write_manuscript,
)

logger = logging.getLogger(__name__)


class ScientistState(TypedDict, total=False):
    campaign_id: str
    round: int
    new_intents: int
    budget_exhausted: bool


def build_scientist_graph(ctx: ScientistContext):
    def cid(state: ScientistState) -> uuid.UUID:
        return uuid.UUID(state["campaign_id"])

    def guarded(fn):
        async def node(state: ScientistState) -> dict[str, Any]:
            try:
                return await fn(state) or {}
            except BudgetExceeded as exc:
                logger.warning("budget exhausted in %s: %s", fn.__name__, exc)
                await ctx.store.record_guard_event(cid(state), "budget", "deny", {"node": fn.__name__, "error": str(exc)})
                return {"budget_exhausted": True}
        node.__name__ = fn.__name__
        return node

    async def scout(state: ScientistState):
        await literature_scout(ctx, cid(state))

    async def planner(state: ScientistState):
        created = await experiment_planner(ctx, cid(state), state.get("round", 0))
        return {"new_intents": created}

    async def swarm(state: ScientistState):
        await experiment_swarm(ctx, cid(state))

    async def verify(state: ScientistState):
        stats = await verifier(ctx, cid(state))
        return {"round": stats["rounds_completed"]}

    async def sealed(state: ScientistState):
        await sealed_evaluation(ctx, cid(state))

    async def manuscript(state: ScientistState):
        try:
            await write_manuscript(ctx, cid(state))
        except BudgetExceeded as exc:
            await ctx.store.transition_campaign(cid(state), "halted", reason=f"budget exhausted while writing: {exc}")
            raise

    async def resume_route(state: ScientistState) -> str:
        campaign = await ctx.store.get_campaign(cid(state))
        status = campaign["status"]
        if status in TERMINAL_STATUSES:
            return END
        if status == "ideation":
            return "literature_scout"
        if status in ("investigating", "ablating"):
            pending = await ctx.store.has_pending_intents(cid(state))
            return "experiment_swarm" if pending else "experiment_planner"
        if status == "sealed_eval":
            return "sealed_evaluation"
        return "write_manuscript"

    def budget_first(route):
        """An exhausted budget always goes straight to writing the paper."""
        def checked(state: ScientistState) -> str:
            return "write_manuscript" if state.get("budget_exhausted") else route(state)
        return checked

    def after_budget_check(next_node: str):
        return budget_first(lambda _state: next_node)

    @budget_first
    def round_route(state: ScientistState) -> str:
        return "sealed_evaluation" if state.get("round", 0) >= ctx.config.max_rounds else "experiment_planner"

    @budget_first
    def planner_route(state: ScientistState) -> str:
        # No new experiments proposed: the search frontier is exhausted.
        return "experiment_swarm" if state.get("new_intents", 0) > 0 else "sealed_evaluation"

    g = StateGraph(ScientistState)
    g.add_node("literature_scout", guarded(scout))
    g.add_node("experiment_planner", guarded(planner))
    g.add_node("experiment_swarm", guarded(swarm))
    g.add_node("verifier", guarded(verify))
    g.add_node("sealed_evaluation", guarded(sealed))
    g.add_node("write_manuscript", manuscript)

    g.add_conditional_edges(START, resume_route, ["literature_scout", "experiment_planner", "experiment_swarm",
                                                  "sealed_evaluation", "write_manuscript", END])
    g.add_conditional_edges("literature_scout", after_budget_check("experiment_planner"),
                            ["experiment_planner", "write_manuscript"])
    g.add_conditional_edges("experiment_planner", planner_route,
                            ["experiment_swarm", "sealed_evaluation", "write_manuscript"])
    g.add_conditional_edges("experiment_swarm", after_budget_check("verifier"), ["verifier", "write_manuscript"])
    g.add_conditional_edges("verifier", round_route, ["experiment_planner", "sealed_evaluation", "write_manuscript"])
    g.add_conditional_edges("sealed_evaluation", after_budget_check("write_manuscript"), ["write_manuscript"])
    g.add_edge("write_manuscript", END)
    return g.compile()


async def run_campaign(ctx: ScientistContext, campaign_id: uuid.UUID) -> dict[str, Any]:
    """Run (or resume) a campaign to completion. Model refusals or malformed output in a
    non-worker node halt the campaign with the reason recorded."""
    campaign = await ctx.store.get_campaign(campaign_id)
    if campaign is None:
        raise KeyError(f"campaign {campaign_id} not found")
    ctx.config = ScientistConfig.from_campaign(campaign["config"])
    graph = build_scientist_graph(ctx)
    try:
        # Rounds are persisted on the root goal, so a resumed run keeps counting.
        start_round = await rounds_completed(ctx, campaign_id)
        await graph.ainvoke({"campaign_id": str(campaign_id), "round": start_round},
                            config={"recursion_limit": 8 * (ctx.config.max_rounds + 2)})
    except (ModelRefusal, ModelOutputError) as exc:
        await ctx.store.transition_campaign(campaign_id, "halted", reason=str(exc)[:1000])
    return await ctx.store.campaign_summary(campaign_id)
