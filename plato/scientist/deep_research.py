"""Deep research sub-agent: gathers the details an experiment needs before it is designed.

When the experiment planner marks an intent with ``research_needs`` (published parameter
values, effect sizes, dataset formats, protein properties...), a Claude sub-agent (role
``deep_researcher``) runs Firecrawl's search, scrape, analyse and repeat loop with these
tools:

* Research Index (free): ``search_papers``, ``read_paper`` (in-body passages),
  ``related_papers`` (citation graph), ``protein_lookup`` (UniProt).
* Billed (Firecrawl credits): ``web_search``, ``scrape_page``, ``developer_search``,
  ``find_tools`` and ``run_tool`` (Alexandria structured-data tools).

It ends with ``finish``: a brief whose every finding names the sources it came from.

Safety and cost
---------------
* Every tool result is third-party content and reaches the model framed as untrusted
  (nonce-tagged); injection signals are recorded as guard events. ``scrape_page`` only
  accepts URLs that a search in the same session returned, and ``run_tool`` only tools
  that ``find_tools`` listed with a price, so page text cannot steer the agent to
  arbitrary addresses or unpriced tools.
* Billed calls reserve their worst-case cost against the campaign budget before the
  request and settle to the credits Firecrawl reports, in allowance tokens
  (``PLATO_FIRECRAWL_CREDIT_TOKENS`` per credit). The campaign budget feeds the monthly
  allowance, so research spend is metered like model spend. A per-intent credit cap
  bounds each session. Campaigns on the person's own Anthropic key are not metered by the
  allowance, so they get only the free Research Index tools.
* Papers the brief cites go through the same citation, retraction and abstract checks as
  the literature scout's, and become citable only with an abstract. Web pages, code and
  tool data inform the experiment but are never citable in the paper.
"""

from __future__ import annotations

import json
import logging
import math
import os
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import pydantic

from plato.retrieval.firecrawl import (
    FirecrawlClient,
    FirecrawlError,
    Paid,
    search_credits,
)

from .guard import frame_untrusted
from .schemas import ResearchBrief

logger = logging.getLogger(__name__)

PURPOSE = "deep_research"
CREDIT_TOKENS_ENV = "PLATO_FIRECRAWL_CREDIT_TOKENS"
# Allowance tokens charged per Firecrawl credit. An allowance token is a Claude Haiku 5.5
# token ($0.10 per million input tokens, the cheapest rate, so a credit is never
# undercharged). jarvisos.xyz is on Firecrawl's Standard plan: $99 a month (monthly billing,
# the higher of its two prices) for 100,000 credits = $0.00099 per credit, and
# $0.00099 / $0.0000001 = 9,900. Credits bought past the plan cost more ($5 per 2,000 =
# 25,000) and the Hobby plan's top-ups most ($5 per 1,000 = 50,000): set
# PLATO_FIRECRAWL_CREDIT_TOKENS when either applies.
DEFAULT_CREDIT_TOKENS = 9_900
# Firecrawl does not document a developer-search price and its response carries no
# creditsUsed. A live check on 2026-11-19 (web search 2 + scrape 1 + Alexandria tool
# discovery 0 + one developer search) drew 5 credits from the team balance, so charge the
# 2 credits left unexplained; a reported creditsUsed still wins.
DEVELOPER_SEARCH_CREDITS = 2.0
MAX_TOOL_TEXT = 6_000
WEB_RESULTS = 5


def credit_tokens(env: Mapping[str, str] | None = None) -> int:
    raw = (
        (env if env is not None else os.environ).get(CREDIT_TOKENS_ENV) or ""
    ).strip()
    if not raw:
        return DEFAULT_CREDIT_TOKENS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "%s=%r is not an integer; using %d",
            CREDIT_TOKENS_ENV,
            raw,
            DEFAULT_CREDIT_TOKENS,
        )
        return DEFAULT_CREDIT_TOKENS
    return max(0, value)


@dataclass(frozen=True)
class ResearchLimits:
    max_turns: int = 10
    # Firecrawl credits one session may spend (the campaign budget is the hard bound).
    max_credits: float = 12.0
    max_scrapes: int = 3
    max_tokens_per_turn: int = 8_000
    effort: str = "medium"
    max_stalls: int = 1


class CreditCapReached(RuntimeError):
    pass


class CreditMeter:
    """Charges billed Firecrawl calls to the campaign budget, reserve then settle."""

    def __init__(
        self,
        store: Any,
        campaign_id: uuid.UUID,
        *,
        tokens_per_credit: int,
        cap: float,
        keep_free: int = 0,
    ) -> None:
        self.store = store
        self.campaign_id = campaign_id
        self.rate = tokens_per_credit
        self.cap = cap
        self.keep_free = keep_free
        self.spent = 0.0

    @property
    def remaining(self) -> float:
        return max(0.0, self.cap - self.spent)

    def tokens(self, credits: float) -> int:
        return math.ceil(max(0.0, credits) * self.rate)

    async def charge(
        self, estimate: float, call: Callable[[], Awaitable[Paid]]
    ) -> Paid:
        if self.spent + estimate > self.cap + 1e-9:
            raise CreditCapReached(
                f"this call would cost about {estimate:g} credits; {self.remaining:g} left"
            )
        reserved = self.tokens(estimate)
        # Raises BudgetExceeded when the campaign cannot afford it (writing budget kept).
        await self.store.reserve_tokens(
            self.campaign_id, reserved, keep_free=self.keep_free
        )
        actual = estimate  # a request that may have run is charged at its estimate
        try:
            paid = await call()
            actual = paid.credits
            return paid
        except FirecrawlError as exc:
            if exc.status is not None and 400 <= exc.status < 500 and exc.status != 408:
                actual = 0.0  # rejected before any work: not billed
            raise
        except ValueError:
            actual = 0.0  # refused locally, never sent
            raise
        finally:
            self.spent += actual
            await self.store.settle_tokens(
                self.campaign_id, reserved, self.tokens(actual)
            )


# ----------------------------------------------------------------------------- tools
def _schema(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


_S = {"type": "string"}
_I = {"type": "integer"}
_IDS = {"type": "array", "items": _S}

FREE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_papers",
        "description": (
            "Free. Semantic search over ~43M paper abstracts (PubMed, bioRxiv, medRxiv, arXiv). "
            "Returns papers with ids like P1, their abstracts and identifiers. Start here."
        ),
        "input_schema": _schema(
            {
                "query": _S,
                "k": {**_I, "description": "Papers to return, 1-10 (default 6)."},
                "from_date": {**_S, "description": "Earliest date, YYYY-MM-DD."},
                "to_date": {**_S, "description": "Latest date, YYYY-MM-DD."},
            },
            ["query"],
        ),
    },
    {
        "name": "read_paper",
        "description": (
            "Free. Read inside one paper: the body passages (methods, tables, results) that "
            "best answer a question. paper is a P id or a pmid:/pmcid:/doi:/arxiv: id."
        ),
        "input_schema": _schema(
            {"paper": _S, "question": _S, "k": {**_I, "description": "Passages, 1-6."}},
            ["paper", "question"],
        ),
    },
    {
        "name": "related_papers",
        "description": (
            "Free. Papers linked to a seed paper through the citation graph, ranked for your "
            "intent. mode: similar (default), citers (later work citing it) or references."
        ),
        "input_schema": _schema(
            {
                "paper": _S,
                "intent": _S,
                "mode": {"type": "string", "enum": ["similar", "citers", "references"]},
            },
            ["paper", "intent"],
        ),
    },
    {
        "name": "protein_lookup",
        "description": (
            "Free. UniProt entry for a protein: function, location, disease, domains, "
            "interactions, length and mass. protein: accession, entry name, gene symbol or "
            "exact name; organism: NCBI taxon id or name (default human)."
        ),
        "input_schema": _schema({"protein": _S, "organism": _S}, ["protein"]),
    },
]

PAID_TOOLS: list[dict[str, Any]] = [
    {
        "name": "web_search",
        "description": (
            f"Costs credits. Web search returning up to {WEB_RESULTS} pages (ids W1, W2...) "
            "with snippets. Use when papers do not cover the need (software documentation, "
            "datasets, registries, guidelines). recency: day, week, month or year."
        ),
        "input_schema": _schema(
            {
                "query": _S,
                "recency": {"type": "string", "enum": ["day", "week", "month", "year"]},
            },
            ["query"],
        ),
    },
    {
        "name": "scrape_page",
        "description": (
            "Costs credits (1 per page, PDFs up to 5). Full text of one page as markdown. Only "
            "URLs returned by web_search or developer_search in this session are allowed."
        ),
        "input_schema": _schema({"url": _S}, ["url"]),
    },
    {
        "name": "developer_search",
        "description": (
            "Costs credits. Search developer documentation, GitHub issues, pull requests and "
            "readmes (ids D1...). Use for how a library or file format works."
        ),
        "input_schema": _schema(
            {
                "query": _S,
                "types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["doc", "issue", "pull_request", "readme"],
                    },
                },
            },
            ["query"],
        ),
    },
    {
        "name": "find_tools",
        "description": (
            "Free to search. Find Alexandria structured-data tools (databases and APIs such as "
            "government statistics or registries) for a need; lists each tool's price and "
            "inputs. Run one with run_tool."
        ),
        "input_schema": _schema({"query": _S}, ["query"]),
    },
    {
        "name": "run_tool",
        "description": (
            "Costs the tool's listed credits. Run an Alexandria tool that find_tools returned, "
            "with options matching its listed inputs."
        ),
        "input_schema": _schema(
            {"provider": _S, "capability": _S, "options": {"type": "object"}},
            ["provider", "capability"],
        ),
    },
]


def inline_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """The JSON schema with every ``$ref`` replaced by its definition (no ``$defs``)."""
    defs = schema.get("$defs") or {}

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                return walk(defs[ref.split("/")[-1]])
            return {k: walk(v) for k, v in node.items() if k not in ("$defs", "title")}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


FINISH_TOOL: dict[str, Any] = {
    "name": "finish",
    "description": (
        "End the research with the brief for the research engineer. Every finding and "
        "parameter must list the ids (P1, W2, ...) of the sources that state it; anything "
        "without a source is dropped. Put needs you could not answer in unresolved."
    ),
    "input_schema": inline_schema(ResearchBrief.model_json_schema()),
}


def tool_specs(paid: bool) -> list[dict[str, Any]]:
    return [*FREE_TOOLS, *(PAID_TOOLS if paid else []), FINISH_TOOL]


SYSTEM = (
    "You are the research assistant of an autonomous research team. Before an experiment is "
    "designed, you find the specific facts it needs (published parameter values, effect "
    "sizes, distributions, data formats, protein properties) and report them with their "
    "sources. Work like a careful scientist: search, read the most relevant sources, follow "
    "up gaps with new queries, then finish. Prefer peer-reviewed papers (the free Research "
    "Index tools); use web pages for what papers do not cover. Billed tools spend the "
    "research budget, so use them only when they add something. Never invent numbers or "
    "sources: report only what a source states, and list what you could not find."
)


@dataclass
class SourceRecord:
    id: str
    kind: str  # paper | web | code | protein | tool
    title: str
    url: str | None = None
    paper: dict[str, Any] | None = None  # Research Index record, for papers


@dataclass
class ResearchOutcome:
    brief: ResearchBrief | None
    turns: int
    reason: str
    credits: float
    sources: dict[str, SourceRecord] = field(default_factory=dict)
    signals: list[str] = field(default_factory=list)

    def cited(self) -> dict[str, SourceRecord]:
        if self.brief is None:
            return {}
        ids = {i for f in self.brief.findings for i in f.sources} | {
            i for p in self.brief.parameters for i in p.sources
        }
        return {i: s for i, s in self.sources.items() if i in ids}


def _clip(text: str, limit: int = MAX_TOOL_TEXT) -> str:
    return (
        text
        if len(text) <= limit
        else text[:limit] + f"\n...[{len(text) - limit} chars cut]"
    )


def _year(paper: Mapping[str, Any]) -> str:
    date = str(paper.get("createdDate") or "")
    return f" ({date[:4]})" if date[:4].isdigit() else ""


class ResearchTools:
    """Runs the sub-agent's tool calls against Firecrawl and keeps the source registry."""

    def __init__(
        self,
        client: FirecrawlClient,
        meter: CreditMeter | None,
        limits: ResearchLimits,
    ) -> None:
        self.client = client
        self.meter = meter  # None: billed tools are unavailable
        self.limits = limits
        self.sources: dict[str, SourceRecord] = {}
        self._by_key: dict[str, str] = {}
        self._counts: dict[str, int] = {}
        self._allowed_urls: dict[str, str] = {}  # url -> source id
        self._tools: dict[tuple[str, str], float | None] = {}
        self.scrapes = 0

    # -------------------------------------------------------------- registry
    def _register(
        self,
        prefix: str,
        key: str,
        kind: str,
        title: str,
        url: str | None = None,
        paper: dict[str, Any] | None = None,
    ) -> str:
        if key in self._by_key:
            sid = self._by_key[key]
            if paper and not self.sources[sid].paper:
                self.sources[sid].paper = paper
            return sid
        self._counts[prefix] = self._counts.get(prefix, 0) + 1
        sid = f"{prefix}{self._counts[prefix]}"
        self._by_key[key] = sid
        self.sources[sid] = SourceRecord(sid, kind, title[:300], url, paper)
        return sid

    def _paper(self, paper: dict[str, Any]) -> str | None:
        pid = str(paper.get("paperId") or "")
        title = str(paper.get("title") or "").strip()
        if not pid or not title:
            return None
        if pid.startswith("web:"):  # a web page surfaced by the paper search
            url = pid[4:]
            sid = self._register("W", f"url:{url}", "web", title, url)
            self._allowed_urls[url] = sid
            return sid
        return self._register("P", f"paper:{pid}", "paper", title, None, paper)

    def _paper_ref(self, ref: str) -> str:
        ref = (ref or "").strip()
        rec = self.sources.get(ref)
        if rec is not None and rec.paper:
            return str(rec.paper.get("paperId"))
        if rec is not None:
            raise ValueError(f"{ref} is not a paper")
        return ref

    def _paper_lines(self, papers: list[dict[str, Any]]) -> str:
        lines = []
        for p in papers:
            sid = self._paper(p)
            if sid is None:
                continue
            ident = p.get("primaryId") or p.get("paperId")
            lines.append(
                f"[{sid}] {p.get('title')}{_year(p)} {ident}\n"
                f"{str(p.get('abstract') or '')[:700]}"
            )
        return "\n\n".join(lines) or "(no papers)"

    # -------------------------------------------------------------- dispatch
    async def call(self, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        """(text, is_error). Never raises except BudgetExceeded and lease errors."""
        handler = getattr(self, f"_t_{name}", None)
        if handler is None or (name in _PAID_NAMES and self.meter is None):
            return f"unknown tool {name!r}", True
        try:
            return _clip(await handler(**args)), False
        except TypeError as exc:
            return f"bad arguments for {name}: {exc}", True
        except (ValueError, CreditCapReached) as exc:
            return str(exc), True
        except FirecrawlError as exc:
            return f"{name} failed: {exc}", True

    async def _t_search_papers(
        self,
        query: str,
        k: int = 6,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> str:
        papers = await self.client.search_papers(
            query, k=max(1, min(int(k), 10)), from_date=from_date, to_date=to_date
        )
        return self._paper_lines(papers)

    async def _t_read_paper(self, paper: str, question: str, k: int = 4) -> str:
        body = await self.client.get_paper(
            self._paper_ref(paper), query=question, k=max(1, min(int(k), 6))
        )
        meta = body.get("paper") if isinstance(body.get("paper"), dict) else {}
        sid = self._paper(meta) if meta else None
        passages = [p for p in body.get("passages") or [] if isinstance(p, dict)]
        head = f"[{sid}] {meta.get('title')}{_year(meta)}" if sid else str(paper)
        return (
            head
            + "\n\n"
            + (
                "\n\n---\n\n".join(str(p.get("text") or "")[:1500] for p in passages)
                or "(no matching passages)"
            )
        )

    async def _t_related_papers(
        self, paper: str, intent: str, mode: str = "similar"
    ) -> str:
        body = await self.client.related_papers(
            self._paper_ref(paper), intent, mode=mode, k=8
        )
        return self._paper_lines(
            [r for r in body.get("results") or [] if isinstance(r, dict)]
        )

    async def _t_protein_lookup(self, protein: str, organism: str | None = None) -> str:
        body = await self.client.protein(protein, organism=organism)
        match = body.get("match")
        if match == "ambiguous":
            cands = [c for c in body.get("candidates") or [] if isinstance(c, dict)]
            return "Ambiguous; call again with one accession:\n" + "\n".join(
                f"- {c.get('accession')} {c.get('entryName')}: {c.get('name')} "
                f"({(c.get('organism') or {}).get('scientificName')})"
                for c in cands[:10]
            )
        entry = body.get("protein")
        if match != "found" or not isinstance(entry, dict):
            return "No UniProt entry matches."
        sid = self._register(
            "U",
            f"uniprot:{entry.get('accession')}",
            "protein",
            f"UniProt {entry.get('accession')} {entry.get('name')}",
            entry.get("url"),
        )

        def texts(key: str, n: int = 3) -> str:
            items = [s for s in entry.get(key) or [] if isinstance(s, dict)]
            return " | ".join(str(s.get("text") or "")[:400] for s in items[:n]) or "-"

        organism_name = (entry.get("organism") or {}).get("scientificName")
        return (
            f"[{sid}] {entry.get('accession')} {entry.get('entryName')}: {entry.get('name')} "
            f"(gene {entry.get('gene')}, {organism_name}); length {entry.get('length')} aa, "
            f"mass {entry.get('mass')} Da\nFunction: {texts('function')}\n"
            f"Location: {texts('subcellularLocation')}\nDisease: {texts('disease')}\n"
            f"Subunit: {texts('subunit', 2)}\nDomains: {texts('domain', 2)}\n"
            f"Interactions: {entry.get('interactionCount')}; features: "
            f"{entry.get('featureCount')}; variants: {entry.get('variantCount')}\n"
            f"Papers: {', '.join((entry.get('paperIds') or [])[:6])}\n"
            f"UniProt release {body.get('release')}"
        )

    async def _t_web_search(self, query: str, recency: str | None = None) -> str:
        assert self.meter is not None
        tbs = {"day": "qdr:d", "week": "qdr:w", "month": "qdr:m", "year": "qdr:y"}.get(
            recency or ""
        )
        paid = await self.meter.charge(
            search_credits(WEB_RESULTS),
            lambda: self.client.search(query, limit=WEB_RESULTS, tbs=tbs),
        )
        data = paid.body.get("data") if isinstance(paid.body.get("data"), dict) else {}
        lines = []
        for r in data.get("web") or []:
            if not isinstance(r, dict) or not r.get("url"):
                continue
            url = str(r["url"])
            sid = self._register(
                "W", f"url:{url}", "web", str(r.get("title") or url), url
            )
            self._allowed_urls[url] = sid
            lines.append(
                f"[{sid}] {r.get('title')}\n{url}\n{str(r.get('description') or '')[:500]}"
            )
        return "\n\n".join(lines) or "(no results)"

    async def _t_scrape_page(self, url: str) -> str:
        assert self.meter is not None
        url = (url or "").strip()
        sid = self._allowed_urls.get(url)
        if sid is None:
            raise ValueError(
                "only URLs returned by web_search or developer_search can be scraped"
            )
        if self.scrapes >= self.limits.max_scrapes:
            raise ValueError(f"scrape limit reached ({self.limits.max_scrapes} pages)")
        self.scrapes += 1
        paid = await self.meter.charge(1.0, lambda: self.client.scrape(url))
        data = paid.body.get("data") if isinstance(paid.body.get("data"), dict) else {}
        return f"[{sid}] {url}\n\n{data.get('markdown') or '(no text)'}"

    async def _t_developer_search(
        self, query: str, types: list[str] | None = None
    ) -> str:
        assert self.meter is not None

        async def run() -> Paid:
            body = await self.client.developer_search(query, k=5, types=types)
            reported = body.get("creditsUsed")
            if isinstance(reported, (int, float)) and reported >= 0:
                return Paid(body, float(reported), True)
            return Paid(body, DEVELOPER_SEARCH_CREDITS)

        paid = await self.meter.charge(DEVELOPER_SEARCH_CREDITS, run)
        lines = []
        for r in paid.body.get("results") or []:
            if not isinstance(r, dict) or not r.get("url"):
                continue
            url = str(r["url"])
            sid = self._register(
                "D", f"url:{url}", "code", str(r.get("title") or url), url
            )
            self._allowed_urls[url] = sid
            text = " ".join(
                str(p.get("text") or "")
                for p in r.get("passages") or []
                if isinstance(p, dict)
            )
            lines.append(f"[{sid}] {r.get('title') or ''} {url}\n{text[:900]}")
        return "\n\n".join(lines) or "(no results)"

    async def _t_find_tools(self, query: str) -> str:
        assert self.meter is not None
        paid = await self.meter.charge(
            0.0,
            lambda: self.client.search(
                query, limit=5, sources=["alexandria"], tool_detail="full"
            ),
        )
        data = paid.body.get("data") if isinstance(paid.body.get("data"), dict) else {}
        lines = []
        for t in data.get("tools") or []:
            if (
                not isinstance(t, dict)
                or not t.get("provider")
                or not t.get("capability")
            ):
                continue
            cost = t.get("creditsCost")
            price = (
                float(cost) if isinstance(cost, (int, float)) and cost >= 0 else None
            )
            self._tools[(str(t["provider"]), str(t["capability"]))] = price
            options = [
                f"{o.get('name')}{'*' if o.get('required') else ''}: {str(o.get('description') or '')[:120]}"
                for o in t.get("options") or []
                if isinstance(o, dict)
            ]
            lines.append(
                f"- provider={t['provider']} capability={t['capability']} "
                f"price={'unknown (cannot run)' if price is None else f'{price:g} credits'}"
                f"{' per record' if t.get('perRecord') else ''}\n  {str(t.get('description') or '')[:400]}"
                + (f"\n  options: {'; '.join(options[:12])}" if options else "")
            )
        return "\n".join(lines) or "(no tools)"

    async def _t_run_tool(
        self, provider: str, capability: str, options: dict[str, Any] | None = None
    ) -> str:
        assert self.meter is not None
        key = (provider.strip(), capability.strip())
        if key not in self._tools:
            raise ValueError(
                "run_tool only runs tools that find_tools listed in this session"
            )
        price = self._tools[key]
        if price is None:
            raise ValueError("this tool lists no price, so it cannot be run")
        paid = await self.meter.charge(
            price,
            lambda: self.client.run_tool(
                key[0], key[1], options or {}, listed_credits=price
            ),
        )
        data = paid.body.get("data") if isinstance(paid.body.get("data"), dict) else {}
        results = [r for r in data.get("alexandria") or [] if isinstance(r, dict)]
        if not results:
            return "(no result)"
        first = results[0]
        if first.get("error"):
            err = first["error"] if isinstance(first["error"], dict) else {}
            return f"tool error: {err.get('code')}: {err.get('message')}"
        sid = self._register(
            "T",
            f"tool:{key[0]}/{key[1]}:{json.dumps(options, sort_keys=True)}",
            "tool",
            f"{key[0]} {key[1]}",
        )
        return f"[{sid}] {key[0]} {key[1]}\n" + json.dumps(
            first.get("data"), default=str
        )


_PAID_NAMES = frozenset(t["name"] for t in PAID_TOOLS)


def _validated_brief(
    args: dict[str, Any], known: set[str]
) -> tuple[ResearchBrief | None, str]:
    try:
        brief = ResearchBrief.model_validate(args)
    except pydantic.ValidationError as exc:
        return None, f"finish rejected: {exc.errors()[:3]}"
    findings = [
        f.model_copy(update={"sources": [s for s in f.sources if s in known]})
        for f in brief.findings
    ]
    params = [
        p.model_copy(update={"sources": [s for s in p.sources if s in known]})
        for p in brief.parameters
    ]
    brief = brief.model_copy(
        update={
            "findings": [f for f in findings if f.sources][:10],
            "parameters": [p for p in params if p.sources][:10],
            "unresolved": brief.unresolved[:10],
        }
    )
    return brief, "ok"


async def run_research(
    *,
    model: Any,
    campaign_id: uuid.UUID,
    task: str,
    tools: ResearchTools,
    nonce: str,
    system: str,
    limits: ResearchLimits | None = None,
    on_turn: Callable[[int], Awaitable[None]] | None = None,
) -> ResearchOutcome:
    limits = limits or ResearchLimits()
    specs = tool_specs(paid=tools.meter is not None)
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    signals: list[str] = []
    stalls = 0

    def outcome(brief: ResearchBrief | None, turn: int, reason: str) -> ResearchOutcome:
        spent = tools.meter.spent if tools.meter is not None else 0.0
        return ResearchOutcome(brief, turn, reason, spent, tools.sources, signals)

    for turn in range(1, limits.max_turns + 1):
        if on_turn is not None:
            await on_turn(turn)
        reply = await model.converse(
            campaign_id=campaign_id,
            purpose=PURPOSE,
            system=system,
            messages=messages,
            tools=specs,
            max_tokens=limits.max_tokens_per_turn,
            effort=limits.effort,
        )
        messages.append({"role": "assistant", "content": reply.content})
        if not reply.tool_uses:
            stalls += 1
            if stalls > limits.max_stalls:
                return outcome(None, turn, "stopped without a brief")
            messages.append(
                {
                    "role": "user",
                    "content": "Continue with the tools, and end with finish.",
                }
            )
            continue
        stalls = 0
        results: list[dict[str, Any]] = []
        for tool_id, name, args in reply.tool_uses:
            if name == "finish":
                brief, note = _validated_brief(args, set(tools.sources))
                if brief is not None:
                    return outcome(brief, turn, "finished")
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": note,
                        "is_error": True,
                    }
                )
                continue
            text, is_error = await tools.call(name, args)
            framed = frame_untrusted(text, source=f"tool:{name}", nonce=nonce)
            signals.extend(framed.injection_signals)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": framed.text,
                    "is_error": is_error,
                }
            )
        remaining = limits.max_turns - turn
        if remaining <= 2:
            results.append(
                {
                    "type": "text",
                    "text": f"{remaining} turn(s) left. Call finish with what you have now.",
                }
            )
        messages.append({"role": "user", "content": results})
    return outcome(None, limits.max_turns, "turn limit reached")


def render_brief(research: Mapping[str, Any]) -> str:
    """Plain-text brief for the research engineer (framed by the caller)."""
    brief = research.get("brief") or {}
    sources = {s["id"]: s for s in research.get("sources") or []}

    def label(ids: list[str]) -> str:
        return ", ".join(
            f"{i}: {sources[i]['title'][:80]}" if i in sources else i for i in ids
        )

    lines = [str(brief.get("summary") or "").strip()]
    for f in brief.get("findings") or []:
        lines.append(f"- {f['statement']} [{label(f['sources'])}]")
    if brief.get("parameters"):
        lines.append("Parameters:")
        for p in brief["parameters"]:
            lines.append(f"- {p['name']} = {p['value']} [{label(p['sources'])}]")
    if brief.get("unresolved"):
        lines.append(
            "Not found (state your assumption): " + "; ".join(brief["unresolved"])
        )
    return "\n".join(line for line in lines if line)
