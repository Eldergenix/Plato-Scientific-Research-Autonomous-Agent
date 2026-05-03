"""Phase 3 — R6: tests for the multi-reviewer panel + revision loop.

Covers:
- Each reviewer node parses the LLM JSON into a `severity` + `issues` dict and
  merges it under `state['critiques'][reviewer]`.
- `critique_aggregator` reduces per-reviewer severities into a single
  `max_severity` and concatenates issues into a flat list.
- `revision_router` redrafts iff severity > 2 AND iteration < max_iterations,
  else terminates with `END`.
- End-to-end with mocked `LLM_call`: severity drops 4 -> 1 across two
  iterations and the loop terminates.
"""

from __future__ import annotations

import json
from typing import Any, Iterable
from unittest.mock import patch

import pytest
from langgraph.graph import END


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(**overrides: Any) -> dict:
    """A minimal `GraphState`-shaped dict for unit tests."""
    state: dict[str, Any] = {
        "messages": [],
        "files": {},
        "idea": {"Idea": "x", "Methods": "y", "Results": "z"},
        "paper": {
            "Title": "A Paper",
            "Abstract": "abstract text",
            "Introduction": "intro text",
            "Methods": "methods text",
            "Results": "results text",
            "Conclusions": "conclusions text",
            "Keywords": "k1, k2",
            "References": "",
            "summary": "",
            "journal": "JCAP",
            "add_citations": False,
            "cmbagent_keywords": False,
        },
        "tokens": {"ti": 0, "to": 0, "i": 0, "o": 0},
        "llm": {"model": "stub", "max_output_tokens": 1024, "llm": None, "temperature": 0.0},
        "latex": {"section_to_fix": ""},
        "keys": None,
        "time": {"start": 0.0},
        "writer": "scientist",
        "params": {"num_keywords": 3},
        "critiques": {},
        "critique_digest": None,
        "revision_state": {"iteration": 0, "max_iterations": 2},
    }
    state.update(overrides)
    return state


def _llm_call_returning(payload: dict | str):
    """Build a mock side-effect for ``LLM_call`` that returns a fenced JSON block."""

    def _side_effect(prompt, state, *, node_name=None):  # signature mirrors tools.LLM_call
        if isinstance(payload, dict):
            body = json.dumps(payload)
        else:
            body = payload
        return state, f"```json\n{body}\n```"

    return _side_effect


def _scripted_llm_call(scripts: Iterable[dict | str]):
    """A side-effect that walks through a list of payloads, one per call."""
    iterator = iter(scripts)

    def _side_effect(prompt, state, *, node_name=None):
        try:
            payload = next(iterator)
        except StopIteration as exc:
            raise AssertionError("LLM_call invoked more times than scripted") from exc
        if isinstance(payload, dict):
            body = json.dumps(payload)
        else:
            body = payload
        return state, f"```json\n{body}\n```"

    return _side_effect


# ---------------------------------------------------------------------------
# Reviewer nodes
# ---------------------------------------------------------------------------


def test_methodology_reviewer_produces_critique_dict():
    from plato.paper_agents import reviewer_panel

    state = _make_state()
    payload = {
        "severity": 4,
        "issues": [
            {"section": "methods", "issue": "no controls", "fix": "add controls"},
        ],
    }
    with patch.object(
        reviewer_panel, "LLM_call", side_effect=_llm_call_returning(payload)
    ) as mock_call:
        update = reviewer_panel.methodology_reviewer(state, config=None)

    mock_call.assert_called_once()
    assert "critiques" in update
    crit = update["critiques"]["methodology"]
    assert crit["severity"] == 4
    assert crit["issues"] == [
        {"section": "methods", "issue": "no controls", "fix": "add controls"}
    ]


def test_all_four_reviewers_write_under_their_own_keys():
    from plato.paper_agents import reviewer_panel

    state = _make_state()
    payload = {"severity": 1, "issues": []}

    with patch.object(
        reviewer_panel, "LLM_call", side_effect=_llm_call_returning(payload)
    ):
        for fn, key in (
            (reviewer_panel.methodology_reviewer, "methodology"),
            (reviewer_panel.statistics_reviewer, "statistics"),
            (reviewer_panel.novelty_reviewer, "novelty"),
            (reviewer_panel.writing_reviewer, "writing"),
        ):
            update = fn(state, config=None)
            assert key in update["critiques"]
            assert update["critiques"][key]["severity"] == 1


def test_reviewer_clamps_invalid_severity_to_range():
    from plato.paper_agents import reviewer_panel

    state = _make_state()
    payload = {"severity": "not-a-number", "issues": "also-bad"}
    with patch.object(
        reviewer_panel, "LLM_call", side_effect=_llm_call_returning(payload)
    ):
        update = reviewer_panel.methodology_reviewer(state, config=None)

    crit = update["critiques"]["methodology"]
    assert crit["severity"] == 0
    assert crit["issues"] == []


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


def test_critique_aggregator_computes_max_severity_and_flattens_issues():
    from plato.paper_agents.critique_aggregator import critique_aggregator

    state = _make_state(
        critiques={
            "methodology": {
                "severity": 4,
                "issues": [{"section": "methods", "issue": "a", "fix": "fa"}],
            },
            "statistics": {
                "severity": 2,
                "issues": [{"section": "results", "issue": "b", "fix": "fb"}],
            },
            "novelty": {"severity": 1, "issues": []},
            "writing": {
                "severity": 3,
                "issues": [{"section": "intro", "issue": "c", "fix": "fc"}],
            },
        },
        revision_state={"iteration": 0, "max_iterations": 2},
    )

    update = critique_aggregator(state, config=None)
    digest = update["critique_digest"]
    assert digest["max_severity"] == 4
    assert digest["iteration"] == 0
    sections = sorted(i["section"] for i in digest["issues"])
    assert sections == ["intro", "methods", "results"]
    # Each issue is tagged with its reviewer.
    reviewers = sorted({i["reviewer"] for i in digest["issues"]})
    assert reviewers == ["methodology", "statistics", "writing"]


def test_critique_aggregator_handles_empty_critiques():
    from plato.paper_agents.critique_aggregator import critique_aggregator

    state = _make_state(critiques={})
    update = critique_aggregator(state, config=None)
    digest = update["critique_digest"]
    assert digest["max_severity"] == 0
    assert digest["issues"] == []


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


def test_revision_router_redrafts_when_severe_and_under_cap():
    from plato.paper_agents.routers import revision_router

    state = _make_state(
        critique_digest={"max_severity": 4, "issues": [], "iteration": 0},
        revision_state={"iteration": 0, "max_iterations": 2},
    )
    assert revision_router(state) == "redraft_node"


def test_revision_router_terminates_when_severity_low():
    from plato.paper_agents.routers import revision_router

    state = _make_state(
        critique_digest={"max_severity": 2, "issues": [], "iteration": 0},
        revision_state={"iteration": 0, "max_iterations": 2},
    )
    assert revision_router(state) == END


def test_revision_router_terminates_when_iteration_cap_reached():
    from plato.paper_agents.routers import revision_router

    state = _make_state(
        critique_digest={"max_severity": 5, "issues": [], "iteration": 2},
        revision_state={"iteration": 2, "max_iterations": 2},
    )
    assert revision_router(state) == END


def test_revision_router_handles_missing_state():
    from plato.paper_agents.routers import revision_router

    # No digest, no revision_state -> safe default to END.
    state = _make_state(critique_digest=None, revision_state={})
    assert revision_router(state) == END


# ---------------------------------------------------------------------------
# Redraft node
# ---------------------------------------------------------------------------


def test_redraft_node_updates_paper_and_increments_iteration():
    from plato.paper_agents import redraft_node as redraft_module

    state = _make_state(
        critique_digest={
            "max_severity": 4,
            "issues": [{"reviewer": "methodology", "section": "methods", "issue": "x", "fix": "y"}],
            "iteration": 0,
        },
        revision_state={"iteration": 0, "max_iterations": 2},
    )
    payload = {
        "Abstract": "improved abstract",
        "Introduction": state["paper"]["Introduction"],
        "Methods": "improved methods",
        "Results": state["paper"]["Results"],
        "Conclusions": state["paper"]["Conclusions"],
    }
    with patch.object(
        redraft_module, "LLM_call", side_effect=_llm_call_returning(payload)
    ):
        update = redraft_module.redraft_node(state, config=None)

    assert update["paper"]["Abstract"] == "improved abstract"
    assert update["paper"]["Methods"] == "improved methods"
    # Untouched sections retained.
    assert update["paper"]["Title"] == "A Paper"
    assert update["revision_state"]["iteration"] == 1
    assert update["critiques"] == {}


def test_redraft_node_tolerates_unparseable_llm_output():
    from plato.paper_agents import redraft_node as redraft_module

    state = _make_state(
        critique_digest={"max_severity": 4, "issues": [], "iteration": 0},
        revision_state={"iteration": 0, "max_iterations": 2},
    )

    def _bad_side_effect(prompt, state, *, node_name=None):
        return state, "not valid json at all"

    with patch.object(redraft_module, "LLM_call", side_effect=_bad_side_effect):
        update = redraft_module.redraft_node(state, config=None)

    # Paper unchanged, but iteration still bumps so the loop terminates.
    assert update["paper"]["Abstract"] == "abstract text"
    assert update["revision_state"]["iteration"] == 1


# ---------------------------------------------------------------------------
# End-to-end: severity 4 -> 1 across two passes, loop terminates.
# ---------------------------------------------------------------------------


def test_revision_loop_terminates_when_severity_drops():
    """Simulate: first pass severity=4, redraft, second pass severity=1, END."""
    from plato.paper_agents import reviewer_panel
    from plato.paper_agents import redraft_node as redraft_module
    from plato.paper_agents.critique_aggregator import critique_aggregator
    from plato.paper_agents.routers import revision_router

    state = _make_state()

    # ---- First reviewer pass: all severity 4 ----
    high_severity_payload = {
        "severity": 4,
        "issues": [{"section": "methods", "issue": "weak", "fix": "strengthen"}],
    }
    with patch.object(
        reviewer_panel, "LLM_call", side_effect=_llm_call_returning(high_severity_payload)
    ):
        for reviewer_fn in (
            reviewer_panel.methodology_reviewer,
            reviewer_panel.statistics_reviewer,
            reviewer_panel.novelty_reviewer,
            reviewer_panel.writing_reviewer,
        ):
            update = reviewer_fn(state, config=None)
            state["critiques"] = update["critiques"]
            state["tokens"] = update["tokens"]

    update = critique_aggregator(state, config=None)
    state["critique_digest"] = update["critique_digest"]
    assert state["critique_digest"]["max_severity"] == 4
    assert revision_router(state) == "redraft_node"

    # ---- Redraft ----
    redraft_payload = {
        "Abstract": "improved abstract",
        "Introduction": "improved intro",
        "Methods": "improved methods",
        "Results": "improved results",
        "Conclusions": "improved conclusions",
    }
    with patch.object(
        redraft_module, "LLM_call", side_effect=_llm_call_returning(redraft_payload)
    ):
        update = redraft_module.redraft_node(state, config=None)
    state["paper"] = update["paper"]
    state["revision_state"] = update["revision_state"]
    state["critiques"] = update["critiques"]
    state["tokens"] = update["tokens"]
    assert state["revision_state"]["iteration"] == 1
    assert state["paper"]["Methods"] == "improved methods"

    # ---- Second reviewer pass: all severity 1 ----
    low_severity_payload = {"severity": 1, "issues": []}
    with patch.object(
        reviewer_panel, "LLM_call", side_effect=_llm_call_returning(low_severity_payload)
    ):
        for reviewer_fn in (
            reviewer_panel.methodology_reviewer,
            reviewer_panel.statistics_reviewer,
            reviewer_panel.novelty_reviewer,
            reviewer_panel.writing_reviewer,
        ):
            update = reviewer_fn(state, config=None)
            state["critiques"] = update["critiques"]
            state["tokens"] = update["tokens"]

    update = critique_aggregator(state, config=None)
    state["critique_digest"] = update["critique_digest"]
    assert state["critique_digest"]["max_severity"] == 1
    # Severity now <= 2 -> terminate, even though we still have an iteration left.
    assert revision_router(state) == END


def test_revision_loop_terminates_at_iteration_cap_even_if_severity_high():
    """Severity stays high (4), but max_iterations=1 forces termination."""
    from plato.paper_agents.critique_aggregator import critique_aggregator
    from plato.paper_agents.routers import revision_router

    state = _make_state(
        revision_state={"iteration": 1, "max_iterations": 1},
        critiques={
            "methodology": {"severity": 4, "issues": []},
            "statistics": {"severity": 4, "issues": []},
            "novelty": {"severity": 4, "issues": []},
            "writing": {"severity": 4, "issues": []},
        },
    )
    update = critique_aggregator(state, config=None)
    state["critique_digest"] = update["critique_digest"]
    assert state["critique_digest"]["max_severity"] == 4
    assert revision_router(state) == END


# ---------------------------------------------------------------------------
# Graph wiring smoke test.
# ---------------------------------------------------------------------------


def test_build_graph_compiles_with_revision_loop_nodes():
    """The full paper graph compiles and exposes the new nodes."""
    from langgraph.checkpoint.memory import MemorySaver
    from plato.paper_agents.agents_graph import build_graph

    graph = build_graph(checkpointer=MemorySaver())
    assert graph is not None
    nodes = set(graph.get_graph().nodes.keys())
    for expected in (
        "reviewer_panel_fanout",
        "methodology_reviewer",
        "statistics_reviewer",
        "novelty_reviewer",
        "writing_reviewer",
        "critique_aggregator",
        "redraft_node",
    ):
        assert expected in nodes, f"missing graph node: {expected}"
