"""Turn a researcher's own files into campaign inputs.

* Reference files (.bib, .ris, .nbib, CSL-JSON, EndNote XML) become paper assets marked
  ``user_supplied``: the scientist reads them with the literature it finds and may always
  cite them.
* Documents (PDF, Word, ODT, RTF, HTML, Markdown, LaTeX, plain text) become
  ``corpus_domain`` assets marked ``user_document`` with the extracted text. The planner
  reads excerpts as untrusted input (framed and screened like paper abstracts).

Data files (CSV, Excel, VCF, ...) are not handled here: they are campaign datasets.
Parsing runs in the sandbox (``tools.run_tool``), because the files come from outside.
"""

from __future__ import annotations

import json
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plato.scientist.db.store import DualGraphStore, paper_dedup_key, sha256_hex

from .tools import ToolError, hand_to_sandbox_user, run_tool

EXCERPT_CHARS = 20_000
MAX_REFERENCES_PER_FILE = 500

REFERENCE_FORMATS = {
    ".bib": "biblatex",
    ".bibtex": "bibtex",
    ".ris": "ris",
    ".json": "csljson",
    ".xml": "endnotexml",
}
DOCUMENT_FORMATS = {
    ".docx": "docx",
    ".odt": "odt",
    ".rtf": "rtf",
    ".html": "html",
    ".htm": "html",
    ".md": "markdown",
    ".tex": "latex",
    ".epub": "epub",
}


@dataclass
class Material:
    file_name: str
    content: bytes
    kind: str  # "reference" | "document"


def _ext(name: str) -> str:
    return Path(name).suffix.lower()


def parse_nbib(text: str) -> list[dict[str, Any]]:
    """PubMed's MEDLINE/.nbib export -> CSL items (pandoc does not read it)."""
    items, cur, tag = [], {}, None
    for line in text.splitlines():
        if not line.strip():
            if cur:
                items.append(cur)
            cur, tag = {}, None
            continue
        m = re.match(r"^([A-Z]{2,4})\s*-\s(.*)$", line)
        if m:
            tag, val = m.group(1), m.group(2).strip()
            cur.setdefault(tag, []).append(val)
        elif tag and line.startswith("      "):
            cur[tag][-1] += " " + line.strip()
    if cur:
        items.append(cur)
    out = []
    for r in items:
        title = " ".join(r.get("TI", [])).strip()
        if not title:
            continue
        item: dict[str, Any] = {"title": title, "type": "article-journal"}
        names = r.get("FAU") or r.get("AU") or []
        item["author"] = [
            {"family": n.split(",", 1)[0].strip(), "given": n.split(",", 1)[1].strip()}
            if "," in n
            else {"literal": n}
            for n in names
        ]
        if r.get("DP") and (y := re.match(r"(\d{4})", r["DP"][0])):
            item["issued"] = {"date-parts": [[int(y.group(1))]]}
        for src, dst in (
            ("JT", "container-title"),
            ("VI", "volume"),
            ("IP", "issue"),
            ("PG", "page"),
            ("AB", "abstract"),
        ):
            if r.get(src):
                item[dst] = r[src][0]
        for aid in r.get("AID", []) + r.get("LID", []):
            if aid.endswith("[doi]"):
                item["DOI"] = aid.removesuffix("[doi]").strip()
        if r.get("PMID"):
            item["PMID"] = r["PMID"][0]
        out.append(item)
    return out


async def parse_references(m: Material, workdir: Path) -> list[dict[str, Any]]:
    ext = _ext(m.file_name)
    if ext in (".nbib", ".medline", ".txt"):
        return parse_nbib(m.content.decode("utf-8", "replace"))[
            :MAX_REFERENCES_PER_FILE
        ]
    fmt = REFERENCE_FORMATS.get(ext)
    if fmt is None:
        raise ValueError(f"{m.file_name}: unsupported reference format")
    src = workdir / f"refs{ext}"
    src.write_bytes(m.content)
    hand_to_sandbox_user(workdir)
    res = await run_tool(["pandoc", src.name, "-f", fmt, "-t", "csljson"], workdir)
    data = json.loads(res.output[res.output.index("[") :])
    return [d for d in data if isinstance(d, dict)][:MAX_REFERENCES_PER_FILE]


def _year(item: dict[str, Any]) -> int | None:
    try:
        return int(item["issued"]["date-parts"][0][0])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _authors(item: dict[str, Any]) -> list[str]:
    out = []
    for a in item.get("author") or []:
        if a.get("literal"):
            out.append(a["literal"])
        elif a.get("family"):
            out.append(f"{a['family']}, {a.get('given', '')}".strip(", "))
    return out[:50]


async def extract_text(m: Material, workdir: Path) -> str:
    ext = _ext(m.file_name)
    src = workdir / f"doc{ext or '.txt'}"
    src.write_bytes(m.content)
    hand_to_sandbox_user(workdir)
    if ext == ".pdf":
        res = await run_tool(
            ["pdftotext", "-enc", "UTF-8", "-nopgbrk", src.name, "-"], workdir
        )
        return res.output
    if ext in DOCUMENT_FORMATS:
        res = await run_tool(
            [
                "pandoc",
                src.name,
                "-f",
                DOCUMENT_FORMATS[ext],
                "-t",
                "plain",
                "--wrap=none",
            ],
            workdir,
        )
        return res.output
    return m.content.decode("utf-8", "replace")


async def ingest(
    store: DualGraphStore,
    program_id: uuid.UUID,
    campaign_id: uuid.UUID,
    materials: list[Material],
) -> dict[str, Any]:
    """Add the materials to the campaign's scope. A file that cannot be parsed is reported,
    never fatal: the campaign still starts with everything else."""
    added = {"references": 0, "documents": 0, "errors": []}
    for m in materials:
        with tempfile.TemporaryDirectory(prefix="plato-material-") as tmp:
            work = Path(tmp)
            try:
                if m.kind == "reference":
                    for item in await parse_references(m, work):
                        title = re.sub(
                            r"<[^>]+>", "", str(item.get("title") or "")
                        ).strip()
                        doi = item.get("DOI")
                        arxiv = None
                        if (u := str(item.get("URL") or "")) and (
                            am := re.search(r"arxiv\.org/abs/([^\s/?#]+)", u)
                        ):
                            arxiv = am.group(1)
                        try:
                            key = paper_dedup_key(
                                doi=doi,
                                arxiv_id=arxiv,
                                title=title or None,
                                year=_year(item),
                            )
                        except ValueError:
                            continue
                        asset = await store.upsert_asset(
                            program_id,
                            "paper",
                            key,
                            (title or key)[:500],
                            uri_or_commit=item.get("URL")
                            or (f"https://doi.org/{doi}" if doi else None),
                            metadata={
                                "title": title,
                                "authors": _authors(item),
                                "year": _year(item),
                                "venue": item.get("container-title"),
                                "doi": doi,
                                "arxiv_id": arxiv,
                                "volume": item.get("volume"),
                                "issue": item.get("issue"),
                                "page": item.get("page"),
                                "abstract": str(item.get("abstract") or "")[:3000],
                                "user_supplied": True,
                                "source_file": m.file_name,
                            },
                        )
                        await store.set_scope(campaign_id, asset.id, "read_only")
                        added["references"] += 1
                else:
                    text = re.sub(r"[ \t]+", " ", await extract_text(m, work)).strip()
                    if not text:
                        added["errors"].append(
                            f"{m.file_name}: no text could be extracted"
                        )
                        continue
                    digest = sha256_hex(m.content)
                    asset = await store.upsert_asset(
                        program_id,
                        "corpus_domain",
                        f"userdoc:{digest}",
                        m.file_name[:255],
                        metadata={
                            "user_document": True,
                            "file_name": m.file_name,
                            "sha256": digest,
                            "chars": len(text),
                            "excerpt": text[:EXCERPT_CHARS],
                        },
                    )
                    await store.set_scope(campaign_id, asset.id, "read_only")
                    added["documents"] += 1
            except (
                ToolError,
                ValueError,
                UnicodeDecodeError,
                json.JSONDecodeError,
            ) as exc:
                added["errors"].append(f"{m.file_name}: {exc}"[:300])
    return added
