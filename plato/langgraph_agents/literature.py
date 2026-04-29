import asyncio
import logging
import time

import requests
from langchain_core.runnables import RunnableConfig
from tqdm import tqdm

from .parameters import GraphState
from .prompts import novelty_prompt, summary_literature_prompt
from ..paper_agents.tools import extract_latex_block, LLM_call_stream, json_parser3
from ..domain import DomainProfile, get_domain
from ..retrieval.orchestrator import retrieve
# Importing the source modules has the side effect of registering each
# adapter (arxiv, openalex, crossref, ads) in ADAPTER_REGISTRY.
from ..retrieval.sources import arxiv, openalex, crossref, ads  # noqa: F401
from ..safety import detect_injection_signals, wrap_external

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
def semantic_scholar(state: GraphState, config: RunnableConfig):
    """
    Search the configured retrieval adapters for the current literature query
    and return wrapped, sanitized paper info to the rest of the literature
    graph. Phase 2 (R4) + Phase 3 (R12).
    """

    profile = _resolve_profile(state)
    query = state['literature']['query']

    # Pull from every adapter listed by the active DomainProfile, dedup,
    # and cap at 20. asyncio.run is safe here because the literature graph
    # is invoked synchronously from Plato.check_idea_semantic_scholar.
    sources = asyncio.run(retrieve(query, limit=20, profile=profile))

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


# DEPRECATED: prefer plato.retrieval.orchestrator.retrieve. Retained for
# backward compatibility with any callers outside the LangGraph nodes.
def SSAPI(query, keys, limit=10) -> list:
    """
    Search for papers similar to the given query using Semantic Scholar API.

    Args:
        query (str): The search query (e.g., keywords or paper title).
        keys (dict): a python dictionary containing the session keys, including the semantic scholar one
        limit (int): Number of papers to retrieve (default is 10).

    Returns:
        list: A list of dictionaries containing paper details.
    """

    # Base URL for Semantic Scholar API
    BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

    params = {"query": query,
              "limit": limit,
              "fields": "title,authors,year,abstract,url,paperId,externalIds,openAccessPdf"}

    # For each query, call Semantic Scholar a maximum of 200 times.
    # When no Semantic Scholar key is present, the system may return an error
    for _ in tqdm(range(200), desc="Calling Semantic Scholar", unit="try"):

        # Conditionally include headers if API_KEY is available
        if keys.SEMANTIC_SCHOLAR:
            response = requests.get(BASE_URL,
                                    headers={"x-api-key": keys.SEMANTIC_SCHOLAR},
                                    params=params)
        else:
            response = requests.get(BASE_URL, params=params)

        if response.status_code==200:
            return response.json()
        else:
            time.sleep(0.5) #wait for 1/2 second before retrying

    else:
        print(f"Error: {response.status_code}, {response.text}")
        return []



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
