"""Journal-specific front matter, written by the model from the finished paper.

Each journal asks for front matter in its own shape: a structured abstract with fixed
headings (NEJM, The Lancet, JAMA, Genes), Key Points (JAMA), Highlights and an eTOC
blurb (Cell), a Research in context panel (The Lancet), a title within a character
limit (Nature, Science). The model rewrites only these pieces, from the manuscript
and the verified evidence, under the journal's limits. The body text is never
rewritten, so every reported number stays exactly as the campaign measured it.

The result is cached per campaign and journal (``plato.publication_adaptations``), so
rebuilding a package is free and deterministic. The tokens are charged to the
campaign like its other model calls and count toward the owner's monthly allowance.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import anthropic
from pydantic import BaseModel, Field

from plato.scientist.db.migrate import advisory_key
from plato.scientist.db.store import BudgetExceeded
from plato.scientist.guard import frame_untrusted, framing_instructions, new_nonce
from plato.scientist.llm import ModelOutputError, ModelRefusal

from .collect import Materials
from .journals import Journal
from .texsafe import plain_text, strip_citations

logger = logging.getLogger(__name__)

ADAPT_MAX_TOKENS = 12_000
# Tokens granted to a completed campaign for one adaptation (input + output, worst case).
ADAPT_GRANT = 60_000


class AbstractSection(BaseModel):
    heading: str = Field(
        description="Exactly one of the headings the journal requires."
    )
    text: str = Field(description="LaTeX-safe prose for this part of the abstract.")


class KeyPoints(BaseModel):
    question: str = Field(description="One sentence.")
    findings: str = Field(
        description="One or two sentences with the main numbers, no test statistics."
    )
    meaning: str = Field(description="One sentence.")


class ResearchInContext(BaseModel):
    evidence_before: str = Field(
        description="Evidence before this study: what was searched and known."
    )
    added_value: str = Field(description="Added value of this study.")
    implications: str = Field(description="Implications of all the available evidence.")


class JournalAdaptation(BaseModel):
    title: str = Field(description="Title within the journal's limits.")
    abstract: list[AbstractSection] = Field(
        description="The abstract. One section with heading 'Abstract' when the journal wants an unstructured paragraph."
    )
    conclusions: str = Field(
        default="", description="A short Conclusions paragraph, when asked for."
    )
    key_points: KeyPoints | None = None
    highlights: list[str] = Field(default_factory=list)
    etoc_blurb: str = ""
    research_in_context: ResearchInContext | None = None
    keywords: list[str] = Field(default_factory=list)
    figure_titles: list[str] = Field(
        default_factory=list,
        description="One short descriptive title per listed figure, in order (no citations).",
    )


def _requirements(j: Journal, n_figures: int) -> str:
    a = j.abstract
    lines = [f"Journal: {j.name} ({j.article_type})."]
    if j.title_max_chars:
        lines.append(
            f"- title: at most {j.title_max_chars} characters including spaces."
        )
    if j.title_max_words:
        lines.append(f"- title: at most {j.title_max_words} words.")
    if a.headings:
        lines.append(
            "- abstract: structured, with exactly these headings in this order: "
            + "; ".join(a.headings)
            + (f"; at most {a.max_words} words in total." if a.max_words else ".")
        )
    else:
        lines.append(
            "- abstract: one unstructured paragraph with heading 'Abstract'"
            + (f", at most {a.max_words} words." if a.max_words else ".")
        )
    lines.append(
        "- abstract citations: "
        + (
            "\\cite{key} allowed with the keys used in the manuscript."
            if a.citations_allowed
            else "none."
        )
    )
    if "Conclusions" in j.sections:
        lines.append("- conclusions: one paragraph of at most 120 words.")
    if j.key_points:
        lines.append(
            "- key_points: Question, Findings, Meaning; at most 100 words in total."
        )
    if j.highlights:
        lines.append(
            "- highlights: 3 or 4 bullets, each at most 85 characters including spaces, no abbreviations."
        )
    if j.etoc_blurb:
        lines.append(
            "- etoc_blurb: two sentences in the third person, at most 50 words."
        )
    if j.research_in_context:
        lines.append(
            "- research_in_context: the three parts, no citations, about 100 words each."
        )
    if j.keywords:
        lines.append(f"- keywords: {j.keywords[0]} to {j.keywords[1]} keywords.")
    if n_figures:
        lines.append(
            f"- figure_titles: exactly {n_figures} short titles (at most 12 words each)."
        )
    lines.append("Leave every other field empty.")
    return "\n".join(lines)


async def grant_budget(
    pool, campaign: dict[str, Any], tokens: int, cap: int | None
) -> None:
    """Make room for an export's model call on a finished campaign. For default-key
    campaigns of an account the grant must fit in what is left of the monthly allowance,
    checked under the same per-account lock that campaign creation uses."""
    cid = campaign["id"]
    async with pool.acquire() as conn, conn.transaction():
        account = campaign.get("account_id")
        if cap is not None and account is not None:
            await conn.execute(
                "SELECT pg_advisory_xact_lock($1)",
                advisory_key(b"plato.account:" + account.bytes),
            )
            committed = await conn.fetchval(
                "SELECT plato.account_committed_tokens($1)", account
            )
            if committed + tokens > cap:
                raise BudgetExceeded(
                    f"formatting needs about {tokens:,} tokens and {max(cap - committed, 0):,} are left this month"
                )
        await conn.execute(
            """
            UPDATE plato.research_campaigns
               SET token_budget_max = GREATEST(token_budget_max, tokens_used + $2)
             WHERE id = $1
            """,
            cid,
            tokens,
        )


def fallback(m: Materials, j: Journal, n_figures: int) -> JournalAdaptation:
    """Deterministic front matter when no model call is possible. The package checks
    flag what it could not produce (for example a structured abstract)."""
    abstract = m.sections.get("abstract", "")
    if not j.abstract.citations_allowed:
        abstract = strip_citations(abstract)
    title = m.title
    if j.title_max_chars and len(title) > j.title_max_chars:
        title = title[: j.title_max_chars].rsplit(" ", 1)[0]
    return JournalAdaptation(
        title=title,
        abstract=[AbstractSection(heading="Abstract", text=abstract)],
        figure_titles=[f"Experiment result {i + 1}" for i in range(n_figures)],
    )


async def adapt(
    model,
    pool,
    m: Materials,
    j: Journal,
    figure_notes: list[str],
    *,
    cap: int | None,
) -> tuple[JournalAdaptation, str]:
    """``(adaptation, source)`` where source is ``model`` or ``fallback: <reason>``."""
    if model is None:
        return fallback(m, j, len(figure_notes)), "fallback: no model configured"
    nonce = new_nonce()
    manuscript = frame_untrusted(
        "\n\n".join(
            f"[{k}]\n{v}" for k, v in [("title", m.title), *m.sections.items()] if v
        ),
        source="manuscript",
        nonce=nonce,
        max_chars=60_000,
    )
    verified = [
        n for n in m.nodes if n["node_type"] == "finding" and n["status"] == "verified"
    ]
    evidence = (
        "\n".join(
            f"- {n['title']}: {n['hypothesis_or_spec']} (confidence {n['confidence_score']})"
            for n in verified
        )
        or "(no finding passed verification)"
    )
    figures = (
        "\n".join(f"[{i + 1}] {t}" for i, t in enumerate(figure_notes)) or "(none)"
    )
    prompt = (
        f"{_requirements(j, len(figure_notes))}\n\n"
        "Write the journal's front matter for this finished manuscript. Use only facts and "
        "numbers that appear in the manuscript or the verified findings, copied exactly; never "
        "introduce a number, method or claim that is not there. Keep the manuscript's caveats: "
        "experiments were computational and automated, and say what was not established. "
        "Write LaTeX-safe prose (escape %, &, _).\n\n"
        f"Verified findings:\n{evidence}\n\nFigures:\n{figures}\n\nManuscript:\n{manuscript.text}"
    )
    try:
        await grant_budget(pool, m.campaign, ADAPT_GRANT, cap)
        out = await model.structured(
            campaign_id=m.campaign["id"],
            purpose="publication_format",
            schema=JournalAdaptation,
            effort="medium",
            max_tokens=ADAPT_MAX_TOKENS,
            system=(
                f"You are the submissions editor of {j.name}. {framing_instructions(nonce)}"
            ),
            prompt=prompt,
        )
    except BudgetExceeded as exc:
        return fallback(m, j, len(figure_notes)), f"fallback: {exc}"
    except (ModelOutputError, ModelRefusal, anthropic.APIError) as exc:
        # The package is still built (with the manuscript's own front matter) when the model
        # is unavailable; the summary records why.
        logger.warning("adaptation failed for %s: %s", j.key, exc)
        return fallback(
            m, j, len(figure_notes)
        ), f"fallback: the model call failed ({exc})"
    except (
        Exception
    ) as exc:  # the front matter is optional: never fail the build over it
        logger.exception("adaptation crashed for %s", j.key)
        return fallback(
            m, j, len(figure_notes)
        ), f"fallback: the model call failed ({type(exc).__name__})"
    return normalise(out, m, j, len(figure_notes)), "model"


def normalise(
    a: JournalAdaptation, m: Materials, j: Journal, n_figures: int
) -> JournalAdaptation:
    """Hold the model to the journal's shape: headings in order, no forbidden citations,
    the right number of figure titles."""
    if j.abstract.headings:
        by = {s.heading.strip().rstrip(":").lower(): s.text for s in a.abstract}
        sections = [
            AbstractSection(heading=h, text=by.get(h.lower(), ""))
            for h in j.abstract.headings
        ]
        if not any(s.text for s in sections):  # the model ignored the headings
            sections = [
                AbstractSection(
                    heading=j.abstract.headings[0],
                    text=" ".join(s.text for s in a.abstract),
                )
            ]
    else:
        sections = [
            AbstractSection(
                heading="Abstract", text=" ".join(s.text for s in a.abstract)
            )
        ]
    if not j.abstract.citations_allowed:
        sections = [
            AbstractSection(heading=s.heading, text=strip_citations(s.text))
            for s in sections
        ]
    titles = [strip_citations(t) for t in a.figure_titles][:n_figures]
    titles += [f"Experiment result {i + 1}" for i in range(len(titles), n_figures)]
    return a.model_copy(
        update={
            "title": re.sub(r"\s+", " ", strip_citations(a.title)).strip() or m.title,
            "abstract": sections,
            "highlights": [strip_citations(h) for h in a.highlights][:4]
            if j.highlights
            else [],
            "etoc_blurb": strip_citations(a.etoc_blurb) if j.etoc_blurb else "",
            "key_points": a.key_points if j.key_points else None,
            "research_in_context": a.research_in_context
            if j.research_in_context
            else None,
            "keywords": a.keywords[: j.keywords[1]] if j.keywords else [],
            "conclusions": strip_citations(a.conclusions)
            if "Conclusions" in j.sections
            else "",
            "figure_titles": titles,
        }
    )


_NUM_RE = re.compile(r"(?<![\w.])-?\d+(?:[.,]\d+)?%?")


def unsupported_numbers(a: JournalAdaptation, m: Materials) -> list[str]:
    """Numbers in the generated front matter that appear nowhere in the manuscript or the
    graph's metrics: a guard against the model inventing results."""
    source = plain_text(" ".join(m.sections.values()) + " " + m.title)
    source += " " + " ".join(json.dumps(n.get("metrics") or {}) for n in m.nodes)
    known = {x.rstrip("%").replace(",", "") for x in _NUM_RE.findall(source)}
    generated = " ".join(
        [
            a.title,
            a.conclusions,
            a.etoc_blurb,
            *a.highlights,
            *(s.text for s in a.abstract),
        ]
        + (
            [a.key_points.question, a.key_points.findings, a.key_points.meaning]
            if a.key_points
            else []
        )
        + (
            [
                a.research_in_context.evidence_before,
                a.research_in_context.added_value,
                a.research_in_context.implications,
            ]
            if a.research_in_context
            else []
        )
    )
    out = []
    for x in _NUM_RE.findall(plain_text(generated)):
        v = x.rstrip("%").replace(",", "")
        # Small integers (counts, "two", years) are too common to check reliably.
        if v in known or (
            v.lstrip("-").isdigit() and (int(v) <= 10 or 1900 <= int(v) <= 2100)
        ):
            continue
        out.append(x)
    return sorted(set(out))
