from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DocType = Literal["plain", "paged", "slides", "docs"]

@dataclass
class DocMeta:
    name: str
    author: str = ""
    lang: str = "English"
    theme: str = "paperwhite"
    layout: str = "latex"

def to_qd(md: str, doctype: DocType, meta: DocMeta) -> str:
    header = [
        f".docname {{{meta.name}}}",
        f".doctype {{{doctype}}}",
        f".doclang {{{meta.lang}}}",
    ]
    if meta.author:
        header.append(f".docauthor {{{meta.author}}}")
    header.append(f".theme {{{meta.theme}}} layout:{{{meta.layout}}}")
    return "\n".join(header) + "\n\n" + md

def to_qd_paper(md: str, meta: DocMeta) -> str:
    return to_qd(md, "paged", meta)

def to_qd_slides(slide_outline_md: str, meta: DocMeta) -> str:
    # Caller MUST provide pre-segmented slide-outline markdown.
    # The slide_outline LangGraph agent emits "## Slide N: ..." breaks.
    return to_qd(slide_outline_md, "slides", meta)

def to_qd_docs(md: str, meta: DocMeta) -> str:
    return to_qd(md, "docs", meta)

def to_qd_plain(md: str, meta: DocMeta) -> str:
    return to_qd(md, "plain", meta)

def write_qd(qd_text: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(qd_text, encoding="utf-8")
    return dest
