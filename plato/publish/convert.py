"""Word (.docx) and JATS XML (PubMed Central) versions of the manuscript, via pandoc.

The LaTeX from ``document.latex_pandoc`` is read into pandoc's AST once; the
``PLATOREFERENCES`` marker becomes the ``refs`` Div so citeproc places the reference
list exactly there, formatted with the journal's CSL style. The Word file is built on a
reference document patched to the journal's page rules: Times New Roman 12 pt, double
or single spacing, paper size, margins and, where asked, continuous line numbers.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

from .journals import Journal
from .references import CSL_DIR
from .tools import run_tool

MARKER = "PLATOREFERENCES"
_FONT = (
    '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" '
    'w:eastAsia="Times New Roman" w:cs="Times New Roman" />'
)
# Page geometry in twentieths of a point.
_PAGES = {"letterpaper": (12240, 15840, 1440), "a4paper": (11906, 16838, 1418)}
_FIXED_ZIP_TIME = (2023, 11, 14, 22, 13, 20)


def _rezip(files: dict[str, bytes]) -> bytes:
    """A zip with fixed timestamps and order, so the same input gives the same bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files, key=lambda n: (n != "[Content_Types].xml", n)):
            info = zipfile.ZipInfo(name, date_time=_FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, files[name])
    return buf.getvalue()


def patch_reference_docx(default: bytes, j: Journal) -> bytes:
    with zipfile.ZipFile(io.BytesIO(default)) as z:
        files = {n: z.read(n) for n in z.namelist()}
    styles = files["word/styles.xml"].decode("utf-8")
    styles = re.sub(r"<w:rFonts [^>]*/>", _FONT, styles)
    styles = re.sub(r"<w:color [^>]*/>", "", styles)  # plain black headings
    line = 480 if j.double_spaced else 276
    styles = re.sub(
        r"<w:pPrDefault>.*?</w:pPrDefault>",
        f'<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="{line}" w:lineRule="auto" /></w:pPr></w:pPrDefault>',
        styles,
        flags=re.DOTALL,
    )
    size = 2 * j.font_pt
    styles = re.sub(
        r'(<w:rPrDefault>.*?<w:sz w:val=")\d+(" />\s*<w:szCs w:val=")\d+',
        rf"\g<1>{size}\g<2>{size}",
        styles,
        flags=re.DOTALL,
    )
    files["word/styles.xml"] = styles.encode("utf-8")
    w, h, margin = _PAGES[j.paper]
    sect = (
        f'<w:sectPr><w:pgSz w:w="{w}" w:h="{h}" />'
        f'<w:pgMar w:top="{margin}" w:right="{margin}" w:bottom="{margin}" w:left="{margin}" '
        'w:header="720" w:footer="720" w:gutter="0" />'
        + (
            '<w:lnNumType w:countBy="1" w:restart="continuous" />'
            if j.line_numbers
            else ""
        )
        + "</w:sectPr>"
    )
    doc = files["word/document.xml"].decode("utf-8")
    doc = re.sub(r"<w:sectPr\s*/>|<w:sectPr>.*?</w:sectPr>", sect, doc, flags=re.DOTALL)
    files["word/document.xml"] = doc.encode("utf-8")
    return _rezip(files)


def _place_refs(blocks: list[dict]) -> bool:
    for i, b in enumerate(blocks):
        if b.get("t") in ("Para", "Plain") and any(
            x.get("t") == "Str" and x.get("c") == MARKER for x in b["c"]
        ):
            blocks[i] = {"t": "Div", "c": [["refs", [], []], []]}
            return True
        if b.get("t") == "Div" and _place_refs(b["c"][1]):
            return True
    return False


async def to_ast(tex: str, workdir: Path) -> dict:
    res = await run_tool(
        ["pandoc", "-f", "latex", "-t", "json"], workdir, stdin=tex.encode("utf-8")
    )
    ast = json.loads(res.output[res.output.index("{") :])
    _place_refs(ast["blocks"])
    return ast


async def docx(
    ast: dict, j: Journal, workdir: Path, out: str = "manuscript.docx"
) -> Path:
    ref = workdir / "reference.docx"
    await run_tool(
        ["pandoc", "-o", ref.name, "--print-default-data-file", "reference.docx"],
        workdir,
    )
    ref.write_bytes(patch_reference_docx(ref.read_bytes(), j))
    (workdir / "doc.json").write_text(json.dumps(ast), encoding="utf-8")
    await run_tool(
        [
            "pandoc",
            "doc.json",
            "-f",
            "json",
            "-t",
            "docx",
            "-o",
            out,
            "--citeproc",
            "--csl",
            "style.csl",
            "--bibliography",
            "refs.json",
            "--reference-doc",
            ref.name,
            "--resource-path",
            ".",
            "-M",
            "link-citations=false",
            "-M",
            "reference-section-title=",
        ],
        workdir,
    )
    return workdir / out


async def jats(ast: dict, workdir: Path, out: str = "manuscript.jats.xml") -> Path:
    """JATS Archiving and Interchange XML, the format PubMed Central ingests. Pandoc's
    built-in JATS citation style writes each reference as a structured
    ``<element-citation>`` (authors, title, source, year, volume, pages, DOI)."""
    (workdir / "doc.json").write_text(json.dumps(ast), encoding="utf-8")
    await run_tool(
        [
            "pandoc",
            "doc.json",
            "-f",
            "json",
            "-t",
            "jats_archiving",
            "-s",
            "-o",
            out,
            "--citeproc",
            "--bibliography",
            "refs.json",
        ],
        workdir,
    )
    return workdir / out


def style_file(j: Journal, workdir: Path) -> None:
    (workdir / "style.csl").write_bytes((CSL_DIR / j.csl).read_bytes())
