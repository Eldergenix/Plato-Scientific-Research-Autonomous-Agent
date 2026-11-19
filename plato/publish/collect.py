"""Read everything a publication package needs for one campaign from the dual graph.

The manuscript is read from its immutable evidence receipt (``latex_section`` on the
root goal), not from the live draft, so an export always reflects the paper the
campaign actually completed with.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from plato.scientist.db.store import DualGraphStore
from plato.scientist.nodes import ROOT_GOAL_KEY, _bib_key

SECTION_NAMES = ("Introduction", "Methods", "Results", "Discussion", "Limitations")


class NotPublishable(RuntimeError):
    """The campaign has no completed manuscript to export."""


@dataclass
class Evidence:
    id: uuid.UUID
    node_id: uuid.UUID
    kind: str
    content: bytes
    quality: float | None


@dataclass
class Materials:
    campaign: dict[str, Any]
    title: str
    sections: dict[
        str, str
    ]  # abstract, introduction, methods, results, discussion, limitations
    review: dict[str, Any] | None
    papers: dict[str, dict[str, Any]]  # bib key -> knowledge asset (visible papers)
    nodes: list[dict[str, Any]]
    evidence: list[Evidence]
    lineage: dict[uuid.UUID, list[uuid.UUID]]  # finding id -> ancestor node ids
    datasets: list[dict[str, Any]]  # asset rows + "content"
    user_documents: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    guard_events: list[dict[str, Any]] = field(default_factory=list)

    def by_status(self, node_type: str, status: str | None = None) -> list[dict]:
        return [
            n
            for n in self.nodes
            if n["node_type"] == node_type and (status is None or n["status"] == status)
        ]


def _braced(text: str, start: int) -> tuple[str, int]:
    """Content of the brace group opening at ``text[start] == '{'`` and the index after it."""
    depth, i = 0, start
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i], i + 1
        i += 1
    raise ValueError("unbalanced braces")


_TABLE_RE = re.compile(r"\\begin\{table\}.*?\\end\{table\}\n?", re.DOTALL)


def parse_manuscript(tex: str) -> tuple[str, dict[str, str]]:
    """Split the LaTeX written by ``assemble_latex`` back into title and sections. The
    generated findings table is dropped: the package rebuilds it per journal."""
    m = re.search(r"\\title\{", tex)
    if not m:
        raise NotPublishable("manuscript has no title")
    title, _ = _braced(tex, m.end() - 1)
    am = re.search(r"\\begin\{abstract\}\n?(.*?)\n?\\end\{abstract\}", tex, re.DOTALL)
    sections = {"abstract": am.group(1).strip() if am else ""}
    heads = list(re.finditer(r"\\section\{([^}]*)\}\n?", tex))
    end_doc = tex.find("\\bibliographystyle")
    for i, h in enumerate(heads):
        stop = (
            heads[i + 1].start()
            if i + 1 < len(heads)
            else (end_doc if end_doc > 0 else len(tex))
        )
        body = _TABLE_RE.sub("", tex[h.end() : stop]).strip()
        sections[h.group(1).strip().lower()] = body
    for name in SECTION_NAMES:
        sections.setdefault(name.lower(), "")
    return title.strip(), sections


async def collect(store: DualGraphStore, campaign_id: uuid.UUID) -> Materials:
    campaign = await store.get_campaign(campaign_id)
    if campaign is None:
        raise NotPublishable("campaign not found")
    if campaign["status"] != "completed":
        raise NotPublishable("the campaign has not finished its paper yet")
    pool = store.pool
    parts = await pool.fetch(
        """
        SELECT DISTINCT ON (e.artifact_type) e.artifact_type, e.content
          FROM plato.evidence_artifacts e JOIN plato.exploration_nodes n ON n.id = e.node_id
         WHERE n.campaign_id = $1 AND n.node_type = 'goal' AND n.dedup_key = $2
           AND e.artifact_type IN ('latex_section', 'peer_review') AND e.content IS NOT NULL
         ORDER BY e.artifact_type, e.created_at DESC
        """,
        campaign_id,
        ROOT_GOAL_KEY,
    )
    by_type = {r["artifact_type"]: bytes(r["content"]).decode("utf-8") for r in parts}
    if "latex_section" not in by_type:
        raise NotPublishable("the campaign completed without a manuscript")
    title, sections = parse_manuscript(by_type["latex_section"])
    review = None
    if "peer_review" in by_type:
        try:
            review = json.loads(by_type["peer_review"])
        except json.JSONDecodeError:
            review = None

    nodes = await store.nodes(campaign_id)
    papers_rows = await store.visible_assets(campaign_id, asset_types=["paper"])
    papers = {_bib_key(p): p for p in papers_rows}
    docs = [
        a
        for a in await store.visible_assets(campaign_id, asset_types=["corpus_domain"])
        if (a["metadata"] or {}).get("user_document")
    ]
    ev_rows = await pool.fetch(
        """
        SELECT e.id, e.node_id, e.artifact_type, e.content, e.vlm_quality_score
          FROM plato.evidence_artifacts e JOIN plato.exploration_nodes n ON n.id = e.node_id
         WHERE n.campaign_id = $1 AND e.content IS NOT NULL
           AND e.artifact_type IN ('plot_png', 'stdout_log', 'git_patch', 'sealed_eval_json', 'vlm_critique')
         ORDER BY e.created_at
        """,
        campaign_id,
    )
    evidence = [
        Evidence(
            r["id"],
            r["node_id"],
            r["artifact_type"],
            bytes(r["content"]),
            float(r["vlm_quality_score"])
            if r["vlm_quality_score"] is not None
            else None,
        )
        for r in ev_rows
    ]
    lineage: dict[uuid.UUID, list[uuid.UUID]] = {}
    for f in (n for n in nodes if n["node_type"] == "finding"):
        rows = await pool.fetch(
            "SELECT node_id FROM plato.lineage($1::uuid, 8) ORDER BY depth", f["id"]
        )
        lineage[f["id"]] = [r["node_id"] for r in rows]
    # Held-out (sealed) evaluation data is never exported: its owner kept it from the
    # research agents, and publishing it would end its use as an unseen test set.
    visible, blobs = await store.dataset_inputs(campaign_id)
    datasets = [
        {
            **a,
            "content": blobs.get(
                (a["metadata"] or {}).get("file_name") or a["canonical_name"]
            ),
        }
        for a in visible
        if not a["is_sealed_eval"] and a["access_mode"] != "sealed_eval_only"
    ]
    usage = dict(
        await pool.fetchrow(
            """
            SELECT tokens_used, token_budget_max, gpu_seconds_used, gpu_seconds_max,
                   created_at, updated_at
              FROM plato.research_campaigns WHERE id = $1
            """,
            campaign_id,
        )
    )
    return Materials(
        campaign=campaign,
        title=title,
        sections=sections,
        review=review,
        papers=papers,
        nodes=nodes,
        evidence=evidence,
        lineage=lineage,
        datasets=datasets,
        user_documents=docs,
        usage=usage,
        guard_events=await store.guard_events(campaign_id),
    )
