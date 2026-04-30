"""Research-gap detector node (Workflow gap #12).

Pure analysis — never calls an LLM. Walks ``state['evidence_links']`` and
``state['sources']`` to surface three classes of structural weakness in
the retrieved corpus:

1. **Contradiction clusters** — claims that have *both* a ``supports`` and
   a ``refutes`` evidence link. The literature disagrees about the claim.
2. **Coverage holes** — keywords drawn from the idea text that appear in
   fewer than two source titles+abstracts. The corpus barely touches that
   topic.
3. **Methodology homogeneity** — every retrieved source mentions the
   *same* method keyword. Useful as a flag that the maker is going to be
   anchored to a single approach.

The output is a list of ``{kind, description, severity (0-5), evidence}``
dicts. ``severity`` is an integer band so consumers don't have to wrangle
floats; the bands are spec'd next to each detector.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from typing import Any, Iterable, Optional

from langchain_core.runnables import RunnableConfig

from .parameters import GraphState
from ..state.models import Claim, EvidenceLink, Source

logger = logging.getLogger(__name__)


# Method keywords we look for when checking methodology homogeneity.
# Lowercased substrings — the matcher is intentionally cheap.
_METHOD_KEYWORDS = (
    "transformer",
    "cnn",
    "mlp",
    "rnn",
    "lstm",
    "gan",
    "diffusion",
    "regression",
    "bayesian",
    "monte carlo",
    "mcmc",
    "n-body",
    "simulation",
    "random forest",
    "gradient boosting",
    "graph neural network",
    "reinforcement learning",
    "clustering",
    "pca",
    "nmf",
)

# Common English stopwords stripped out of the idea text before keyword
# extraction. Conservative list — we'd rather show a marginally noisy
# keyword than miss a real coverage hole.
_STOPWORDS = frozenset(
    """
    a an the and or but if then so to of in on for with without by from at
    is are was were be been being has have had do does did this that these
    those it its as we i you he she they them our their there here over
    under not no yes can could would should may might will shall would
    about into through between among across versus via per
    """.split()
)

# Idea keywords are unique tokens of length >= MIN_KEYWORD_LEN. Two-letter
# tokens are almost always noise once stopwords are dropped.
_MIN_KEYWORD_LEN = 4

# Cap on the number of idea keywords inspected — covers a sensible idea
# without iterating over the entire description on long inputs.
_MAX_KEYWORDS = 12


def _idea_text(state: GraphState) -> str:
    if not isinstance(state, dict):
        return ""
    idea = state.get("idea")
    if isinstance(idea, dict):
        text = idea.get("idea")
        if isinstance(text, str):
            return text
    desc = state.get("data_description")
    return desc if isinstance(desc, str) else ""


def _idea_keywords(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-]+", text.lower())
    seen: list[str] = []
    seen_set: set[str] = set()
    for tok in tokens:
        if len(tok) < _MIN_KEYWORD_LEN:
            continue
        if tok in _STOPWORDS:
            continue
        if tok in seen_set:
            continue
        seen_set.add(tok)
        seen.append(tok)
        if len(seen) >= _MAX_KEYWORDS:
            break
    return seen


def _source_haystacks(sources: Iterable[Source]) -> list[str]:
    """Lower-cased title+abstract per source — the search target for keyword scans."""
    out: list[str] = []
    for s in sources:
        title = s.title or ""
        abstract = s.abstract or ""
        out.append(f"{title} {abstract}".lower())
    return out


def _claim_lookup(claims: Iterable[Claim]) -> dict[str, Claim]:
    return {c.id: c for c in claims if isinstance(c, Claim) and c.id}


def _detect_contradictions(
    evidence_links: list[EvidenceLink], claim_text: dict[str, Claim]
) -> list[dict[str, Any]]:
    """A drafted claim with both 'supports' and 'refutes' links is a contradiction."""
    by_claim: dict[str, set[str]] = defaultdict(set)
    src_ids: dict[str, set[str]] = defaultdict(set)
    for link in evidence_links:
        if not isinstance(link, EvidenceLink):
            continue
        by_claim[link.claim_id].add(link.support)
        src_ids[link.claim_id].add(link.source_id)

    gaps: list[dict[str, Any]] = []
    for claim_id, labels in by_claim.items():
        if {"supports", "refutes"}.issubset(labels):
            claim = claim_text.get(claim_id)
            text = claim.text if claim else claim_id
            sources = sorted(src_ids[claim_id])
            # Severity scales with how many sources are arguing on each
            # side, capped at 5.
            severity = min(5, max(2, len(sources)))
            gaps.append(
                {
                    "kind": "contradiction",
                    "description": (
                        f"Claim {claim_id!r} has both supporting and refuting "
                        f"evidence across {len(sources)} sources: {text!r}"
                    ),
                    "severity": severity,
                    "evidence": sources,
                }
            )
    return gaps


def _detect_coverage_holes(
    keywords: list[str], haystacks: list[str]
) -> list[dict[str, Any]]:
    """Keywords appearing in <2 source titles+abstracts are coverage holes."""
    if not haystacks:
        # No corpus at all — every keyword is uncovered. Return one summary
        # gap rather than spamming 12 individual ones.
        if not keywords:
            return []
        return [
            {
                "kind": "coverage",
                "description": (
                    "No retrieved sources at all; every idea keyword is "
                    "uncovered."
                ),
                "severity": 5,
                "evidence": keywords,
            }
        ]

    gaps: list[dict[str, Any]] = []
    for kw in keywords:
        hits = sum(1 for h in haystacks if kw in h)
        if hits < 2:
            # 0 hits == high severity, 1 hit == moderate severity.
            severity = 4 if hits == 0 else 2
            gaps.append(
                {
                    "kind": "coverage",
                    "description": (
                        f"Idea keyword {kw!r} appears in {hits} of "
                        f"{len(haystacks)} retrieved sources."
                    ),
                    "severity": severity,
                    "evidence": [kw],
                }
            )
    return gaps


def _detect_homogeneity(
    sources: list[Source], haystacks: list[str]
) -> list[dict[str, Any]]:
    """All sources sharing the same method keyword is a methodology gap."""
    if len(sources) < 2:
        return []

    matches: Counter[str] = Counter()
    for h in haystacks:
        for kw in _METHOD_KEYWORDS:
            if kw in h:
                matches[kw] += 1

    n = len(haystacks)
    homogeneous = [kw for kw, count in matches.items() if count == n]
    if not homogeneous:
        return []

    return [
        {
            "kind": "homogeneity",
            "description": (
                f"All {n} retrieved sources mention method keyword(s) "
                f"{homogeneous!r}; the corpus is methodologically homogeneous."
            ),
            "severity": 3,
            "evidence": homogeneous,
        }
    ]


async def gap_detector(state: GraphState, config: Optional[RunnableConfig] = None):
    """LangGraph node: pure-analysis gap detection over retrieved evidence."""

    if not isinstance(state, dict):
        return {"gaps": []}

    sources_raw = state.get("sources") or []
    literature = state.get("literature") or {}
    if isinstance(literature, dict):
        for s in literature.get("sources") or []:
            if isinstance(s, Source):
                sources_raw.append(s)

    sources: list[Source] = [s for s in sources_raw if isinstance(s, Source)]
    evidence_links: list[EvidenceLink] = [
        l for l in (state.get("evidence_links") or []) if isinstance(l, EvidenceLink)
    ]
    claims: list[Claim] = [
        c for c in (state.get("claims") or []) if isinstance(c, Claim)
    ]

    haystacks = _source_haystacks(sources)
    keywords = _idea_keywords(_idea_text(state))
    claim_index = _claim_lookup(claims)

    gaps: list[dict[str, Any]] = []
    gaps.extend(_detect_contradictions(evidence_links, claim_index))
    gaps.extend(_detect_coverage_holes(keywords, haystacks))
    gaps.extend(_detect_homogeneity(sources, haystacks))

    return {"gaps": gaps}


__all__ = ["gap_detector"]
