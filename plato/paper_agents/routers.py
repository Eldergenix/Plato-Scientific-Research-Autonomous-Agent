from langgraph.graph import END

from .parameters import GraphState


# idea - methods router
def citation_router (state: GraphState) -> str:
    """Route the post-refine_results stage.

    When ``add_citations`` is true we run the citation pipeline
    (``citations_node`` -> ``citation_validator_node`` -> claim/evidence
    matrix); otherwise we skip the BibTeX work but still run claim
    extraction so the reviewer panel can see an evidence matrix.
    """

    if   state['paper']['add_citations'] is True:
        return 'citations_node'
    elif state['paper']['add_citations'] is False:
        return 'claim_evidence_fanout'
    else:
        raise Exception('Wrong add_citations value')


# Phase 3 — R6: severity-gated revision-loop router.
def revision_router(state: GraphState):
    """Decide whether to redraft the paper or finish.

    Returns ``"redraft_node"`` while the panel is still surfacing meaningful
    issues *and* we have iterations left, otherwise ``END``.

    Conditions for redraft:
      - ``critique_digest['max_severity'] > 2`` (severities 3..5 are blocking)
      - ``revision_state['iteration'] < revision_state['max_iterations']``

    Either condition failing terminates the loop.
    """
    digest = state.get("critique_digest") or {}
    # mypy treats revision_state as non-Optional (REVISION_STATE is a
    # required field on GraphState) but partial state updates can ship
    # without it. Keep the runtime fallback.
    revision_state = state.get("revision_state") or {}  # type: ignore[unreachable]

    try:
        max_severity = int(digest.get("max_severity", 0) or 0)
    except (TypeError, ValueError):
        max_severity = 0
    try:
        iteration = int(revision_state.get("iteration", 0) or 0)
    except (TypeError, ValueError):
        iteration = 0
    try:
        max_iterations = int(revision_state.get("max_iterations", 0) or 0)
    except (TypeError, ValueError):
        max_iterations = 0

    if max_severity > 2 and iteration < max_iterations:
        return "redraft_node"
    return END
