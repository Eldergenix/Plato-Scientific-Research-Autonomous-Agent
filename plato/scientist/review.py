"""Claim-to-evidence matrix and the four-reviewer panel for the scientist's manuscript.

Ported from the library pipeline (``plato.langgraph_agents.claim_extractor``,
``plato.paper_agents.evidence_matrix_node`` and ``plato.paper_agents.reviewer_panel``)
onto the scientist's structured-output model client, with two changes that make them
cheap and verifiable enough to run on every campaign:

* Claims are extracted deterministically: every manuscript sentence that carries a
  ``\\cite{}`` is a claim, paired with each key it cites. One model call then judges all
  pairs against the cited abstracts (the library made one call per pair).
* A supporting or refuting verdict counts only if its quote is found verbatim in the
  cited abstract; otherwise it is downgraded to ``unclear``. The model cannot invent
  support.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any

from .guard import frame_untrusted, framing_instructions
from .schemas import EvidenceMatrix, Manuscript, PanelCritique

MAX_PAIRS = 40
_SECTIONS = (
    "abstract",
    "introduction",
    "methods",
    "results",
    "discussion",
    "limitations",
)
_CITE = re.compile(r"\\cite[pt]?\{([^}]*)\}")
# Sentence ends: . ! ? followed by whitespace and an upper-case letter or a LaTeX command.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\\])")


def _system(role: str, nonce: str) -> str:
    return (
        f"You are the {role} in an autonomous research team. Be precise, quantitative and "
        "honest about uncertainty; never invent results, citations or numbers. "
        + framing_instructions(nonce)
    )


def _plain(sentence: str) -> str:
    text = _CITE.sub("", sentence)
    text = re.sub(r"\\[a-zA-Z]+\*?\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([.,;:!?)])", r"\1", text)  # where a removed \cite left a gap


def extract_cited_claims(ms: Manuscript, allowed: set[str]) -> list[dict[str, Any]]:
    """Every sentence citing at least one allowed key, with those keys."""
    claims: list[dict[str, Any]] = []
    for section in _SECTIONS:
        body = getattr(ms, section, "") or ""
        for sentence in _SENTENCE_END.split(body):
            keys = [
                k.strip()
                for m in _CITE.finditer(sentence)
                for k in m.group(1).split(",")
                if k.strip() in allowed
            ]
            if keys:
                claims.append(
                    {
                        "id": len(claims),
                        "section": section,
                        "text": _plain(sentence)[:600],
                        "keys": list(dict.fromkeys(keys)),
                    }
                )
    return claims


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_span(abstract: str, quote: str) -> tuple[int, int] | None:
    """Character span of ``quote`` in ``abstract`` (whitespace and case insensitive)."""
    q = _norm(quote)
    if len(q) < 12 or not abstract:
        return None
    # Map positions in the normalised text back to the original abstract.
    index: list[int] = []
    out: list[str] = []
    prev_space = True
    for i, ch in enumerate(abstract):
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                index.append(i)
            prev_space = True
        else:
            out.append(ch.lower())
            index.append(i)
            prev_space = False
    norm = "".join(out)
    start = norm.find(q)
    if start < 0:
        return None
    return index[start], index[start + len(q) - 1] + 1


async def build_evidence_matrix(
    model: Any,
    campaign_id: uuid.UUID,
    ms: Manuscript,
    papers: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Judge every (cited claim, cited paper) pair against the paper's abstract."""
    claims = extract_cited_claims(ms, set(papers))
    pairs = [(c, k) for c in claims for k in c["keys"]][:MAX_PAIRS]
    result: dict[str, Any] = {
        "claims": [],
        "pairs_judged": 0,
        "pairs_total": sum(len(c["keys"]) for c in claims),
    }
    if not pairs:
        return {**result, "supported_claims": 0, "unsupported_claim_rate": 0.0}

    nonce = uuid.uuid4().hex[:12]
    abstracts = {
        k: (papers[k]["metadata"].get("abstract") or "") for k in {k for _, k in pairs}
    }
    framed_sources = "\n".join(
        frame_untrusted(
            f"{k}: {papers[k]['canonical_name']}\n{abstracts[k] or '(no abstract available)'}",
            source=k,
            nonce=nonce,
        ).text
        for k in sorted(abstracts)
    )
    lines = "\n".join(
        f"[{i}] claim ({c['section']}): {c['text']}\n    cites: {k}"
        for i, (c, k) in enumerate(pairs)
    )
    out = await model.structured(
        campaign_id=campaign_id,
        purpose="evidence_matrix",
        schema=EvidenceMatrix,
        effort="medium",
        max_tokens=12000,
        system=_system("citation auditor", nonce),
        prompt=(
            "For each numbered claim-citation pair, judge whether the cited paper's abstract "
            "supports the claim. Judge only from the abstract text given. Quote the abstract "
            "verbatim for supports and refutes; a paraphrase is not a quote.\n\n"
            f"Cited abstracts:\n{framed_sources}\n\nPairs:\n{lines}"
        ),
    )
    verdicts: dict[int, Any] = {
        link.pair_index: link for link in out.links if 0 <= link.pair_index < len(pairs)
    }
    by_claim: dict[int, dict[str, Any]] = {}
    for i, (claim, key) in enumerate(pairs):
        link = verdicts.get(i)
        support = link.support if link else "unclear"
        span = quote_span(abstracts[key], link.quote) if link else None
        verified = span is not None
        if support in ("supports", "refutes") and not verified:
            support = "unclear"  # an unquotable verdict is not evidence
        entry = by_claim.setdefault(
            claim["id"],
            {
                "section": claim["section"],
                "text": claim["text"],
                "citations": [],
            },
        )
        entry["citations"].append(
            {
                "key": key,
                "title": papers[key]["canonical_name"],
                "support": support,
                "strength": link.strength if link else "weak",
                "quote": abstracts[key][span[0] : span[1]] if span else "",
                "quote_span": list(span) if span else None,
                "rationale": (link.rationale if link else "not judged")[:400],
            }
        )
    for entry in by_claim.values():
        kinds = {c["support"] for c in entry["citations"]}
        entry["verdict"] = (
            "refuted"
            if "refutes" in kinds
            else "supported"
            if "supports" in kinds
            else "unsupported"
        )
    claims_out = list(by_claim.values())
    supported = sum(1 for c in claims_out if c["verdict"] == "supported")
    return {
        **result,
        "claims": claims_out,
        "pairs_judged": len(verdicts),
        "supported_claims": supported,
        "unsupported_claim_rate": round(1 - supported / len(claims_out), 4),
    }


def matrix_required_changes(matrix: dict[str, Any]) -> list[str]:
    changes = []
    for c in matrix.get("claims", []):
        keys = ", ".join(x["key"] for x in c["citations"])
        if c["verdict"] == "refuted":
            changes.append(
                f'In {c["section"]}, the claim "{c["text"][:200]}" is contradicted by the '
                f"abstract of {keys}: correct the claim or drop the citation."
            )
        elif c["verdict"] == "unsupported":
            changes.append(
                f'In {c["section"]}, the claim "{c["text"][:200]}" cites {keys}, but the cited '
                "abstract does not support it: cite only for what the paper states, or remove the citation."
            )
    return changes[:12]


# Reviewer angles and their focus, ported from plato.paper_agents.prompts.
PANEL: dict[str, tuple[str, str]] = {
    "methodology": (
        "senior methodology reviewer",
        (
            "experimental design and controls; dataset suitability and possible biases; "
            "evaluation metrics and baselines; reproducibility (parameters, seeds, code and data); "
            "whether the methods actually support the claimed results"
        ),
    ),
    "statistics": (
        "senior statistics reviewer",
        (
            "sample sizes and power; error bars, confidence intervals and uncertainty; "
            "significance testing and multiple-comparison corrections; distributional "
            "assumptions; over-claiming from noisy estimates; whether reported numbers are "
            "sufficient to reproduce the claims"
        ),
    ),
    "novelty": (
        "senior reviewer for novelty and related work",
        (
            "whether the contribution is novel relative to the cited literature; missing or "
            "misrepresented prior work; over-claimed novelty; positioning against the state of the art"
        ),
    ),
    "writing": (
        "senior reviewer for writing quality",
        (
            "clarity and flow; section structure; consistent terminology and notation; "
            "references to tables and figures; grammar that impedes comprehension (not typos)"
        ),
    ),
}


async def run_review_panel(
    model: Any,
    campaign_id: uuid.UUID,
    ms: Manuscript,
    evidence_text: str,
) -> dict[str, Any]:
    """Four independent single-angle reviews, run concurrently. A failed reviewer is
    recorded with its error; the others still count."""
    nonce = uuid.uuid4().hex[:12]
    paper = frame_untrusted(ms.model_dump_json(), source="manuscript", nonce=nonce).text

    async def review(angle: str) -> PanelCritique:
        role, focus = PANEL[angle]
        return await model.structured(
            campaign_id=campaign_id,
            purpose=f"review_{angle}",
            schema=PanelCritique,
            effort="medium",
            max_tokens=6000,
            system=_system(role, nonce),
            prompt=(
                f"Review the manuscript for {angle} issues only. Focus on: {focus}.\n"
                "Check claims against the evidence below; the evidence is authoritative.\n\n"
                f"Evidence:\n{evidence_text}\n\nManuscript:\n{paper}"
            ),
        )

    results = await asyncio.gather(*(review(a) for a in PANEL), return_exceptions=True)
    reviewers: dict[str, Any] = {}
    for angle, res in zip(PANEL, results, strict=True):
        if isinstance(res, BaseException):
            if isinstance(res, asyncio.CancelledError):
                raise res
            reviewers[angle] = {"error": f"{type(res).__name__}: {res}"[:500]}
        else:
            reviewers[angle] = {
                **res.model_dump(),
                "severity": max(0, min(5, int(res.severity))),
            }
    done = [r for r in reviewers.values() if "error" not in r]
    return {
        "reviewers": reviewers,
        "completed": len(done),
        "max_severity": max((r["severity"] for r in done), default=None),
    }


def panel_digest(panel: dict[str, Any]) -> str:
    lines = []
    for angle, r in panel.get("reviewers", {}).items():
        if "error" in r:
            lines.append(f"- {angle}: review unavailable")
            continue
        lines.append(f"- {angle} (severity {r['severity']}/5): {r['summary']}")
        lines += [
            f"    * [{i['section']}] {i['issue']} Fix: {i['fix']}"
            for i in r["issues"][:6]
        ]
    return "\n".join(lines) or "(no panel reviews)"


def matrix_digest(matrix: dict[str, Any]) -> str:
    claims = matrix.get("claims", [])
    if not claims:
        return "(no cited claims)"
    counts = {
        v: sum(1 for c in claims if c["verdict"] == v)
        for v in ("supported", "unsupported", "refuted")
    }
    return (
        json.dumps(counts)
        + "\n"
        + "\n".join(
            f"- [{c['verdict']}] {c['text'][:200]}"
            for c in claims
            if c["verdict"] != "supported"
        )
    )
