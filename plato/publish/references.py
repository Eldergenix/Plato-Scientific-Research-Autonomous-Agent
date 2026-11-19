"""References: CSL-JSON from the graph's paper assets, rendered in each journal's style.

The reference list is formatted by pandoc's citeproc with the journal's official CSL
style (``plato/publish/csl``), then turned into a ``thebibliography`` block so the
LaTeX source stays a single self-contained file (Nature and arXiv both ask for that).
Numbering follows the order of first citation, which every supported journal uses.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .tools import run_tool

CSL_DIR = Path(__file__).parent / "csl"
_CITE_RE = re.compile(r"\\cite\{([^}]*)\}")
_ARXIV_RE = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$")


def cited_keys_in_order(*texts: str) -> list[str]:
    seen: dict[str, None] = {}
    for text in texts:
        for m in _CITE_RE.finditer(text):
            for key in m.group(1).split(","):
                key = key.strip()
                if key:
                    seen.setdefault(key, None)
    return list(seen)


def _split_name(name: str) -> dict[str, str]:
    name = re.sub(r"\s+", " ", name).strip()
    if "," in name:  # "Family, Given"
        family, given = (p.strip() for p in name.split(",", 1))
        return {"family": family, "given": given}
    parts = name.split(" ")
    if len(parts) == 1:
        return {"literal": name}
    # Keep particles with the family name: "Ludwig van Beethoven" -> "van Beethoven".
    i = len(parts) - 1
    while i > 1 and parts[i - 1].lower() in {
        "van",
        "von",
        "de",
        "der",
        "da",
        "di",
        "du",
        "le",
        "la",
        "del",
    }:
        i -= 1
    return {"family": " ".join(parts[i:]), "given": " ".join(parts[:i])}


def csl_item(key: str, asset: dict[str, Any]) -> dict[str, Any]:
    meta = asset.get("metadata") or {}
    crossref = (meta.get("crossref") or {}).get("fields")
    if crossref and crossref.get("title"):
        # Crossref's record is authoritative for published work (complete authors,
        # journal, volume, issue, pages); keep the DOI and any arXiv id we know.
        item = {"id": key, **crossref}
        doi = (meta.get("doi") or "").strip()
        if doi:
            item["DOI"] = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
        return item
    title = (meta.get("title") or asset.get("canonical_name") or "").strip()
    item: dict[str, Any] = {"id": key, "title": title}
    authors = [
        a for a in (meta.get("authors") or []) if isinstance(a, str) and a.strip()
    ]
    if authors:
        item["author"] = [_split_name(a) for a in authors]
    year = meta.get("year")
    if isinstance(year, int) or (isinstance(year, str) and year.isdigit()):
        item["issued"] = {"date-parts": [[int(year)]]}
    doi = (meta.get("doi") or "").strip()
    if doi:
        item["DOI"] = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    arxiv = (meta.get("arxiv_id") or "").strip()
    venue = (meta.get("venue") or "").strip()
    for k in ("volume", "issue", "page", "publisher"):
        if meta.get(k):
            item[k] = str(meta[k])
    if venue and venue.lower() not in {"arxiv", "arxiv.org"}:
        item["type"] = "article-journal"
        item["container-title"] = venue
    elif arxiv and _ARXIV_RE.match(arxiv):
        # A preprint as CSL describes one: the server is the publisher and the arXiv id
        # its number. arXiv registers a versionless DOI (10.48550/arXiv.<id>) for every
        # paper, so DOI-based styles (Nature, APA, Cell) print a resolvable link.
        base = _ARXIV_RE.match(arxiv).group(1)
        item["type"] = "article"
        item["publisher"] = "arXiv"
        item["number"] = f"arXiv:{arxiv}"
        item.setdefault("DOI", f"10.48550/arXiv.{base}")
        item.setdefault("URL", f"https://arxiv.org/abs/{arxiv}")
    else:
        item["type"] = "article"
    url = asset.get("uri_or_commit")
    if url and str(url).startswith(("http://", "https://")) and "DOI" not in item:
        item.setdefault("URL", str(url))
    return item


def csl_items(
    keys: list[str], papers: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [csl_item(k, papers[k]) for k in keys if k in papers]


def bibtex(items: list[dict[str, Any]]) -> str:
    """A BibTeX file for authors who keep editing in their own reference manager."""

    def esc(v: str) -> str:
        return v.replace("\\", "").replace("{", "").replace("}", "")

    out = []
    for it in items:
        kind = "article" if it.get("type") == "article-journal" else "misc"
        fields: list[tuple[str, str]] = [
            ("title", "{" + esc(it.get("title", "")) + "}")
        ]
        names = []
        for a in it.get("author", []):
            names.append(
                a.get("literal")
                or f"{a.get('family', '')}, {a.get('given', '')}".strip(", ")
            )
        if names:
            fields.append(("author", " and ".join(esc(n) for n in names)))
        if it.get("container-title") and kind == "article":
            fields.append(("journal", esc(it["container-title"])))
        if it.get("issued"):
            fields.append(("year", str(it["issued"]["date-parts"][0][0])))
        for src, dst in (
            ("volume", "volume"),
            ("issue", "number"),
            ("page", "pages"),
            ("DOI", "doi"),
            ("URL", "url"),
        ):
            if it.get(src):
                fields.append((dst, esc(str(it[src]))))
        if it.get("publisher") == "arXiv" and it.get("number"):
            fields.append(("eprint", it["number"].removeprefix("arXiv:")))
            fields.append(("archiveprefix", "arXiv"))
        body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields)
        out.append(f"@{kind}{{{it['id']},\n{body}\n}}")
    return "\n\n".join(out) + ("\n" if out else "")


def _strip_label(inlines: list[dict]) -> list[dict]:
    out: list[dict] = []
    for i in inlines:
        if i.get("t") == "Span":
            classes = i["c"][0][1]
            if "csl-left-margin" in classes:
                continue
            if "csl-right-inline" in classes or "csl-block" in classes:
                out.extend(_strip_label(i["c"][1]))
                continue
        out.append(i)
    return out


def _inlines_of(blocks: list[dict]) -> list[dict]:
    """The reference text of one citeproc entry, without its number label (citeproc
    emits the label as a ``csl-left-margin`` Div or Span depending on pandoc version)."""
    out: list[dict] = []
    for b in blocks:
        t = b.get("t")
        if t == "Div":
            classes = b["c"][0][1]
            if "csl-left-margin" in classes:
                continue
            out.extend(_inlines_of(b["c"][1]))
        elif t in ("Para", "Plain"):
            if out:
                out.append({"t": "Space"})
            out.extend(_strip_label(b["c"]))
    return out


async def render_references(
    items: list[dict[str, Any]],
    csl: str,
    workdir: Path,
    clusters: list[tuple[str, ...]] = (),
) -> tuple[list[tuple[str, str]], dict[tuple[str, ...], str]]:
    r"""Format the reference list, and each in-text citation cluster, with a CSL style.

    Returns ``[(key, latex_entry)]`` in the order the style lists references (citation
    order for numbered styles, alphabetical for author-date ones) and, for every cluster
    asked for, its in-text form as LaTeX, e.g. ``(Smith \& Jones, 2020; Lee, 2021)``."""
    if not items:
        return [], {}
    order = [it["id"] for it in items]
    (workdir / "refs.json").write_text(
        json.dumps(items, ensure_ascii=False), encoding="utf-8"
    )
    (workdir / "style.csl").write_bytes((CSL_DIR / csl).read_bytes())
    clusters = list(clusters)
    if clusters:
        paras = ["[" + "; ".join(f"@{k}" for k in c) + "]" for c in clusters]
        # Every reference is listed even if a cluster was scrubbed from the text.
        meta = ["-M", "nocite=" + ", ".join(f"@{k}" for k in order)]
    else:
        paras = [f"[@{k}]" for k in order]
        meta = []
    res = await run_tool(
        [
            "pandoc",
            "-f",
            "markdown",
            "-t",
            "json",
            "--citeproc",
            "--csl",
            "style.csl",
            "--bibliography",
            "refs.json",
            "-M",
            "link-citations=false",
            "-M",
            "link-bibliography=false",
            *meta,
        ],
        workdir,
        stdin=("\n\n".join(paras) + "\n").encode(),
    )
    doc = json.loads(res.output[res.output.index("{") :])
    entries: dict[str, list[dict]] = {}

    def walk(blocks: list[dict]) -> None:
        for b in blocks:
            if b.get("t") == "Div":
                ident = b["c"][0][0]
                if ident.startswith("ref-"):
                    entries[ident[4:]] = _inlines_of(b["c"][1])
                else:
                    walk(b["c"][1])

    walk(doc["blocks"])
    listed = [k for k in entries if k in order] + [k for k in order if k not in entries]
    cited: list[list[dict]] = []
    if clusters:
        top = [b for b in doc["blocks"] if b.get("t") == "Para"][: len(clusters)]
        for b in top:
            out: list[dict] = []
            for i in b["c"]:
                out.extend(i["c"][1] if i.get("t") == "Cite" else [i])
            cited.append(out)
    # Convert every piece to LaTeX in one pandoc run, separated by a marker paragraph.
    marker = "PLATOREFSEPARATOR"
    blocks: list[dict] = []
    for inl in [entries.get(k) or [{"t": "Str", "c": k}] for k in listed] + cited:
        blocks.append({"t": "Para", "c": inl})
        blocks.append({"t": "Para", "c": [{"t": "Str", "c": marker}]})
    out_doc = {**doc, "blocks": blocks, "meta": {}}
    res = await run_tool(
        ["pandoc", "-f", "json", "-t", "latex", "--wrap=none"],
        workdir,
        stdin=json.dumps(out_doc).encode(),
    )
    parts = [p.strip() for p in res.output.split(marker)]
    refs = [(k, parts[i]) for i, k in enumerate(listed)]
    texts = {c: parts[len(listed) + i] for i, c in enumerate(clusters)}
    return refs, texts


async def render_bibliography(
    items: list[dict[str, Any]], csl: str, workdir: Path
) -> list[tuple[str, str]]:
    """``[(key, latex_entry)]`` in the style's order."""
    return (await render_references(items, csl, workdir))[0]


def _one_line(v: object) -> str:
    return re.sub(r"\s+", " ", str(v)).strip()


def ris(items: list[dict[str, Any]]) -> str:
    """RIS, the format EndNote, Zotero, Mendeley and most submission systems import."""
    out = []
    for it in items:
        kind = {"article-journal": "JOUR", "book": "BOOK", "chapter": "CHAP"}.get(
            it.get("type", ""), "GEN"
        )
        lines = [("TY", kind)]
        for a in it.get("author", []):
            name = a.get("literal") or ", ".join(
                x for x in (a.get("family", ""), a.get("given", "")) if x
            )
            lines.append(("AU", name))
        lines.append(("TI", it.get("title", "")))
        if it.get("container-title"):
            lines.append(("T2", it["container-title"]))
        if it.get("issued"):
            lines.append(("PY", str(it["issued"]["date-parts"][0][0])))
        for src, tag in (("volume", "VL"), ("issue", "IS"), ("publisher", "PB")):
            if it.get(src):
                lines.append((tag, str(it[src])))
        page = str(it.get("page") or "")
        if page:
            sp, _, ep = page.replace("\u2013", "-").partition("-")
            lines.append(("SP", sp.strip()))
            if ep.strip():
                lines.append(("EP", ep.strip()))
        if it.get("number"):
            lines.append(("M1", str(it["number"])))
        if it.get("DOI"):
            lines.append(("DO", it["DOI"]))
        if it.get("URL"):
            lines.append(("UR", it["URL"]))
        lines.append(("ID", it["id"]))
        lines.append(("ER", ""))
        out.append("\r\n".join(f"{t}  - {_one_line(v)}".rstrip() for t, v in lines))
    return "\r\n\r\n".join(out) + ("\r\n" if out else "")


def author_date_bibliography(entries: list[tuple[str, str]]) -> str:
    """An unnumbered reference list with hanging indents (author-date styles)."""
    if not entries:
        return ""
    body = "\n\n".join(
        f"\\noindent\\hangindent=1.5em\\hangafter=1 {text}\\par" for _, text in entries
    )
    return f"\\section*{{\\refname}}\n\\begingroup\\raggedright\n{body}\n\\endgroup\n"


def thebibliography(entries: list[tuple[str, str]]) -> str:
    if not entries:
        return ""
    body = "\n".join(f"\\bibitem{{{k}}} {text}" for k, text in entries)
    # Ragged right: justified references stretch long DOIs and URLs across the line.
    return (
        f"\\begin{{thebibliography}}{{{len(entries)}}}\\raggedright\n{body}\n"
        "\\end{thebibliography}\n"
    )
