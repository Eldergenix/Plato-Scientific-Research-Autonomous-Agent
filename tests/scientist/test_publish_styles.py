"""Citation styles and submission materials in publication packages: author-date and
numbered styles in the text and the reference list (PDF and Word), RIS, the cover
letter, JAMA's title page and layout, and Nature's Extended Data. Real pdfLaTeX and
pandoc, real Postgres."""

from __future__ import annotations

import dataclasses
import io
import re
import zipfile

import pytest
from test_publish import _completed, needs_tex

from plato.publish import journals
from plato.publish.package import build_package
from plato.publish.references import csl_item, ris


def _files(pkg) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(pkg.zip_bytes)) as z:
        return {n.split("/", 1)[1]: z.read(n) for n in z.namelist()}


def _docx_text(data: bytes) -> str:
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode()
    return re.sub(r"<[^>]+>", "", xml.replace("</w:p>", "\n"))


def test_preprints_are_described_as_csl_preprints_with_their_arxiv_doi():
    item = csl_item(
        "k",
        {
            "metadata": {
                "title": "T",
                "authors": ["Ada Lovelace"],
                "year": 2025,
                "arxiv_id": "2504.08066v2",
            }
        },
    )
    assert item["type"] == "article" and item["publisher"] == "arXiv"
    assert item["number"] == "arXiv:2504.08066v2"
    assert (
        item["DOI"] == "10.48550/arXiv.2504.08066"
    )  # versionless, as arXiv registers it
    assert "container-title" not in item
    out = ris([item])
    assert out.startswith("TY  - GEN\r\nAU  - Lovelace, Ada\r\nTI  - T\r\n")
    assert "DO  - 10.48550/arXiv.2504.08066\r\n" in out and out.endswith("ER  -\r\n")


def test_every_style_is_an_official_csl_file_with_a_known_in_text_form():
    for s in journals.STYLES.values():
        text = (journals.CSL_DIR / s.csl).read_text("utf-8")
        fmt = re.search(r'citation-format="([^"]+)"', text).group(1)
        assert (fmt == "author-date") == (s.cite == "author_date"), s.key
        assert "creativecommons.org/licenses/by-sa/3.0" in text, s.key
    nature = journals.get("nature")
    assert journals.style_for(nature) == nature.style
    assert journals.style_for(nature, "apa").csl == "apa.csl"
    with pytest.raises(KeyError):
        journals.style_for(nature, "nope")


@needs_tex
async def test_author_date_and_numbered_styles_in_pdf_and_word(store):
    cid, model = await _completed(store)

    apa = await build_package(store, model, cid, "arxiv", crossref=False, style="apa")
    f = _files(apa)
    tex = f["manuscript/manuscript.tex"].decode()
    assert apa.pdf_ok and f["manuscript/manuscript.pdf"].startswith(b"%PDF")
    assert "\\cite{" not in tex and "\\begin{thebibliography}" not in tex
    assert "(Author, 2025)" in tex  # citeproc's APA in-text form
    refs = tex.split("\\section*{\\refname}")[1]
    assert re.search(
        r"Author, A\. \(2025\)\. \\emph\{Bootstrap methods revisited", refs
    )
    assert "\\hangindent" in refs
    assert "(Author, 2025)" in _docx_text(f["manuscript/manuscript.docx"])
    checks = {c.id: c for c in apa.checks}
    assert checks["citation_style"].status == "pass"  # arXiv prescribes no style
    assert apa.summary()["citation_style"] == {"key": "apa", "name": "APA 7th edition"}
    assert "Citations and references: APA 7th edition." in f["README.md"].decode()

    van = await build_package(
        store, model, cid, "arxiv", crossref=False, style="vancouver"
    )
    tex = _files(van)["manuscript/manuscript.tex"].decode()
    assert "\\usepackage[numbers,square,sort&compress]{natbib}" in tex
    assert re.search(r"\\bibitem\{[^}]+\} Author A\. Bootstrap methods revisited", tex)

    # Another style for a journal with its own: built, and flagged.
    nat = await build_package(store, model, cid, "nature", crossref=False, style="apa")
    checks = {c.id: c for c in nat.checks}
    assert checks["citation_style"].status == "warn"
    assert "asks for Nature" in checks["citation_style"].detail
    own = await build_package(store, model, cid, "nature", crossref=False)
    tex = _files(own)["manuscript/manuscript.tex"].decode()
    assert "\\setcitestyle{citesep={,}}" in tex  # superscripts 1,2 not 1;2
    assert {c.id: c for c in own.checks}["citation_style"].status == "pass"


@needs_tex
async def test_cover_letter_and_reference_files(store):
    cid, model = await _completed(store)
    for key in journals.JOURNALS:
        pkg = await build_package(store, model, cid, key, crossref=False)
        f = _files(pkg)
        assert "manuscript/references.ris" in f
        assert f["manuscript/references.ris"].startswith(b"TY  - ")
        j = journals.get(key)
        if j.cover_letter is None:
            assert not any(p.startswith("submission/") for p in f), key
            continue
        letter = f["submission/cover_letter.md"].decode()
        assert f"in {j.name}." in letter and "Dear [Editor's name]" in letter
        assert "not under consideration elsewhere" in letter
        for ask in j.cover_letter:
            assert ask in letter, (key, ask)
        assert "(Author One" not in letter
        word = _docx_text(f["submission/cover_letter.docx"])
        assert "We confirm that:" in word
        checklist = f["SUBMISSION_CHECKLIST.md"].decode()
        assert "## Cover letter (submission/cover_letter.docx)" in checklist
        for name, url in j.forms:
            assert f"- [ ] {name}: {url}" in checklist
    jama = _files(await build_package(store, model, cid, "jama", crossref=False))
    assert (
        "postal address, email, telephone"
        in jama["submission/cover_letter.md"].decode()
    )


@needs_tex
async def test_jama_title_page_order_and_separate_figures(store):
    cid, model = await _completed(store)
    pkg = await build_package(store, model, cid, "jama", crossref=False)
    f = _files(pkg)
    tex = f["manuscript/manuscript.tex"].decode()
    assert pkg.pdf_ok
    assert re.search(r"Word count: \d", tex)
    assert "highest academic degree" in tex
    assert tex.index("\\section*{Key Points}") < tex.index("\\section*{Abstract}")
    assert "\\raggedright" in tex.split("\\begin{document}")[1][:40]
    body = tex.split("\\begin{document}")[1]
    assert "\\includegraphics" not in body  # figures go as separate files
    order = [
        body.index(s)
        for s in (
            "\\section*{Introduction}",
            "\\paragraph{Article information.}",
            "\\begin{thebibliography}",
            "\\section*{Figure legends}",
            "\\caption{Verified findings",
        )
    ]
    assert order == sorted(order)
    assert body.count("\\clearpage") >= 4
    docx = f["manuscript/manuscript.docx"]
    xml = zipfile.ZipFile(io.BytesIO(docx)).read("word/document.xml").decode()
    assert xml.count('w:type="page"') >= 4 and "<w:drawing" not in xml
    text = _docx_text(docx)
    assert text.index("Word count:") < text.index("Key Points") < text.index("Abstract")
    assert "Figure 1. " in text
    checks = {c.id: c for c in pkg.checks}
    assert checks["figure_files"].status == "pass"


@needs_tex
async def test_nature_extra_figures_become_extended_data(store, monkeypatch):
    cid, model = await _completed(store)
    small = dataclasses.replace(journals.JOURNALS["nature"], display_items_max=2)
    monkeypatch.setitem(journals.JOURNALS, "nature", small)
    pkg = await build_package(store, model, cid, "nature", crossref=False)
    f = _files(pkg)
    ed = sorted(p for p in f if p.startswith("manuscript/extended_data/"))
    assert ed and ed[0].startswith("manuscript/extended_data/Extended_Data_Fig_1.")
    tex = f["manuscript/manuscript.tex"].decode()
    assert "\\section*{Extended Data figure legends}" in tex
    assert "Extended Data Fig. 1 |" in tex
    sup = f["supplement/supplementary_information.tex"].decode()
    assert "Supplementary Figures" not in sup
    assert pkg.pdf_ok
    assert "Extended Data Fig. 1 |" in _docx_text(f["manuscript/manuscript.docx"])
