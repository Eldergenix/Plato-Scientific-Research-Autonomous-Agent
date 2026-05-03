import logging
import time
from typing import Optional

from langchain_core.runnables import RunnableConfig
from tqdm import tqdm

from .parameters import GraphState
from .prompts import novelty_prompt, summary_literature_prompt
from ..paper_agents.tools import extract_latex_block, LLM_call_stream, json_parser3
from ..domain import DomainProfile, get_domain
from ..retrieval.orchestrator import retrieve
from ..safety import detect_injection_signals, wrap_external


# Lazy adapter registration. Importing each source module fires its
# ``register_adapter(...)`` call, but doing it at module-load time
# pulled in 6 modules' worth of httpx/feedparser/etc. on every
# ``build_lg_graph`` import. We defer the registration until the
# first real retrieval call so the graph builder stays cheap.
_adapters_registered = False


def _ensure_adapters_registered() -> None:
    """Import every retrieval source module exactly once."""
    global _adapters_registered
    if _adapters_registered:
        return
    _adapters_registered = True
    import importlib

    for name in (
        "arxiv",
        "openalex",
        "crossref",
        "ads",
        "pubmed",
        "semantic_scholar",
    ):
        try:
            importlib.import_module(f"plato.retrieval.sources.{name}")
        except Exception:
            # Optional adapter dependency missing — skip but keep
            # iterating so the others still register.
            pass

logger = logging.getLogger(__name__)


# This node determines if an idea is novel or not. It may also ask for literature search
def novelty_decider(state: GraphState, config: RunnableConfig):
    """
    The goal of this function is to determine if an idea is novel or not. The function is given access to semantic scholar to find papers related to the project idea.
    """

    print(f"\nAddressing idea novelty: round {state['literature']['iteration']}")

    # check if idea is novel or not
    PROMPT = novelty_prompt(state)

    # Try for three times in case it fails
    for _ in tqdm(range(5), desc="Analyzing novelty", unit="try"):

        state, result = LLM_call_stream(PROMPT, state)
        try:
            result    = json_parser3(result)
            reason    = result["Reason"]
            decision  = result["Decision"]
            query     = result["Query"]
            messages = f"{state['literature']['messages']}\nIteration {state['literature']['iteration']}\ndecision:{decision}\nreason:{reason}\n"
            iteration = state['literature']['iteration'] + 1
            break
        except Exception:
            time.sleep(2)

    else:
        raise Exception('Failed to extract json after 5 attempts')

    # get the reason for the decision
    if 'not novel' in decision.lower():
        print('Decision made: not novel')
        return {"literature": {**state['literature'], "reason": reason, "messages": messages,
                               "decision": decision, "query": query, "iteration": iteration,
                               'next_agent': "literature_summary"}}

    elif 'novel' in decision.lower() or iteration>=state['literature']['max_iterations']:
        decision = 'novel'
        print('Decision made: novel')
        return {"literature": {**state['literature'], "reason": reason, "messages": messages,
                               "decision": decision, "query": query, "iteration": iteration,
                               'next_agent': "literature_summary"}}

    else:
        # Get the value of the "Query" field
        print('Decision made: query')
        print(f'Query: {query}')
        return {"literature": {**state['literature'], "reason": reason, "messages": messages,
                               "decision": decision, "query": query, "iteration": iteration,
                               'next_agent': "semantic_scholar"}}


def _resolve_profile(state: GraphState) -> DomainProfile:
    """Pull a DomainProfile out of state, falling back to the astro default.

    The graph may be primed with either a registered domain *name*
    (``state['domain'] = 'astro'``) or a fully constructed DomainProfile
    (``state['domain_profile']``). Anything else falls through to the astro
    default so this node never crashes a run mid-graph.
    """
    profile = state.get("domain_profile")  # type: ignore[arg-type]
    if isinstance(profile, DomainProfile):
        return profile

    name = state.get("domain")  # type: ignore[arg-type]
    if isinstance(name, str) and name:
        try:
            return get_domain(name)
        except KeyError:
            logger.warning("Unknown domain %r in state; falling back to 'astro'.", name)

    return get_domain("astro")


# This node fans the query out to every retrieval adapter in the active
# domain profile (arxiv, openalex, ads, ... — see plato.domain) instead of
# the legacy single-source Semantic Scholar call. Phase 2 (R4) wiring.
#
# Async by design: ``retrieve`` is async (it awaits adapter HTTP calls in
# parallel via asyncio.gather). Wrapping with ``asyncio.run()`` from inside
# a sync wrapper would crash on any caller that already has a running loop
# (notebooks, ``graph.ainvoke()``, dashboard worker threads with a loop).
# LangGraph natively supports async nodes, so we just use ``await``.
async def semantic_scholar(state: GraphState, config: Optional[RunnableConfig] = None):
    """
    Search the configured retrieval adapters for the current literature query
    and return wrapped, sanitized paper info to the rest of the literature
    graph. Phase 2 (R4) + Phase 3 (R12).
    """

    # Lazy adapter registration — pulls in the 6 source modules on
    # first call rather than on every ``build_lg_graph`` import.
    _ensure_adapters_registered()

    profile = _resolve_profile(state)
    query = state['literature']['query']

    # Pull from every adapter listed by the active DomainProfile, dedup,
    # and cap at 20.
    sources = await retrieve(query, limit=20, profile=profile)

    total_papers = len(sources)
    papers_str: list[str] = []
    papers_analyzed = 0

    if sources:
        print(f"Found {total_papers} potentially relevant papers")

        for paper in sources:
            abstract = paper.abstract
            if abstract is None:
                continue
            papers_analyzed += 1

            # Defense in depth: log injection red flags but keep the source.
            # The wrap_external marker downstream is the actual containment.
            signals = detect_injection_signals(abstract)
            if signals:
                logger.warning(
                    "Injection signals %s detected in source %s; abstract will be wrapped before use.",
                    signals,
                    paper.id,
                )

            wrapped_abstract = wrap_external(abstract, "abstract")
            authors = ", ".join(paper.authors)
            idx = papers_analyzed + state['literature']['num_papers']

            paper_str = (
                f"{idx}. {paper.title} ({paper.year})\n"
                f"Authors: {authors}\n"
                f"Abstract: {wrapped_abstract}\n"
                f"URL: {paper.url}"
            )

            arxiv_pdf: str | None = None
            if paper.arxiv_id:
                arxiv_pdf = f"https://arxiv.org/pdf/{paper.arxiv_id}"
                paper_str = f"{paper_str}\narXiv link: {arxiv_pdf}"

            if paper.pdf_url and paper.pdf_url != arxiv_pdf:
                paper_str = f"{paper_str}\npdf: {paper.pdf_url}"

            paper_str = f"{paper_str}\n\n"

            literature_log = state['files'].get('literature_log')
            if literature_log:
                with open(literature_log, 'a') as f:
                    f.write(paper_str)

            papers_log = state['files'].get('papers')
            if papers_log:
                with open(papers_log, 'a') as f:
                    f.write(paper_str)

            papers_str.append(paper_str)
    else:
        papers_str.append("No papers found with the query.\n")

    total_papers_found = state['literature']['num_papers'] + papers_analyzed
    print('Total papers analyzed', total_papers_found)

    return {"literature": {**state['literature'],
                           'papers': papers_str,
                           "num_papers": total_papers_found,
                           "sources": list(sources)}}


def literature_summary(state: GraphState, config: RunnableConfig):
    """
    This agent will take all messages from previous iterations and write a summary of the findings
    """

    # generate the summary
    PROMPT = summary_literature_prompt(state)
    state, result = LLM_call_stream(PROMPT, state)
    text = extract_latex_block(state, result, "SUMMARY")

    # write summary to file
    with open(f"{state['files']['literature']}", 'w') as f:
        f.write(f"Idea {state['literature']['decision']}\n\n")
        f.write(text)

    # print out the summary
    print(text)

    print(f"done {state['tokens']['ti']} {state['tokens']['to']}")

    # Returning a partial state update (rather than falling off the end
    # with an implicit ``None``) so the checkpointer captures the
    # generated summary text. Without this, a resume from this node
    # would skip the summary entirely.
    return {
        "literature": {
            **state['literature'],
            'summary': text,
        }
    }
