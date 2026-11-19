"""The manuscript as an ordered document for one journal, rendered two ways:

* ``latex_pdf``: a self-contained pdfLaTeX source (single file, inline bibliography),
  formatted to the journal's rules: spacing, line numbers, paper size, Times, citation
  style, section order, front matter and back-matter statements;
* ``latex_pandoc``: the same content in the plain LaTeX dialect pandoc reads, with
  ``\\cite`` left for citeproc, for the Word (.docx) and JATS (PubMed Central) outputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .adapt import JournalAdaptation
from .journals import AI_NOTE, CitationStyle, Journal
from .texsafe import (
    lancet_decimals,
    move_citations_after_punctuation,
    sanitize,
    strip_citations,
    tighten_superscript_citations,
    word_count,
)

# A paragraph holding only this word becomes a page break in the Word file.
PAGE_BREAK = "PLATOPAGEBREAK"
ABSTRACT_HERE = "PLATOABSTRACTHERE"

# Journals whose main text opens without an "Introduction" heading.
UNHEADED_INTRO = {"nature", "science", "nejm"}


@dataclass
class Figure:
    file: str  # path inside the package's manuscript folder, e.g. figures/fig1.png
    title: str
    legend: str
    source_node: str | None = None


@dataclass
class Table:
    caption: str
    header: list[str]
    rows: list[list[str]]
    notes: str = ""


@dataclass
class Doc:
    journal: Journal
    title: str
    adaptation: JournalAdaptation
    sections: dict[str, str]  # sanitised LaTeX bodies keyed by lower-case name
    figures: list[Figure]
    table: Table | None
    model: str
    supplement_items: list[str] = field(default_factory=list)
    style: CitationStyle | None = None  # None: the journal's own style
    extended: list[Figure] = field(default_factory=list)  # Nature Extended Data figures

    def __post_init__(self) -> None:
        if self.style is None:
            self.style = self.journal.style


def escape(text: str) -> str:
    return (
        re.sub(r"([&%$#_{}])", r"\\\1", text)
        .replace("~", r"\textasciitilde{}")
        .replace("^", r"\textasciicircum{}")
    )


def _style_citations(text: str, doc: Doc) -> str:
    style = doc.style
    if style.after_punctuation:
        text = move_citations_after_punctuation(text)
    if style.cite == "super":
        text = tighten_superscript_citations(text)
    if doc.journal.decimal_midpoint:
        text = lancet_decimals(text)
    return text


def _body(doc: Doc, name: str) -> str:
    return _style_citations(doc.sections.get(name, ""), doc)


def statements(doc: Doc) -> list[tuple[str, str]]:
    """Back-matter statements in the journal's order. Bracketed text marks what only the
    authors can supply; the checklist lists every placeholder left in the package."""
    j = doc.journal
    data = (
        "All data generated in this study (per-experiment metrics, figure source data and the "
        "input datasets) are provided with this manuscript in the supplementary data package "
        "(data/), with SHA-256 checksums in MANIFEST.json. [Deposit the package in a public "
        "repository that issues a DOI and cite it here.]"
    )
    code = (
        "The analysis code of every experiment is provided in code/, with its execution logs "
        "in logs/. [Archive the code with a DOI (for example Zenodo) and cite it here.]"
    )
    ai = (
        f"The experiments, analyses and first draft of this manuscript were produced by Plato, an "
        f"automated research system, using the {doc.model} language model (Anthropic). "
        "[State how the authors checked the code, the results and the text, and take "
        "responsibility for them.]"
    )
    texts = {
        "Data availability": data,
        "Code availability": code,
        "Data and code availability": f"{data} {code}",
        "Data, code, and materials availability": f"{data} {code} This study generated no new materials.",
        "Data sharing": data,
        "Data sharing statement": data,
        "Data Availability Statement": data,
        "Acknowledgements": "[Acknowledge non-author contributions.] " + ai,
        "Acknowledgments": "[Acknowledge non-author contributions.] " + ai,
        "Author contributions": "[Describe each author's contribution, for example with the CRediT taxonomy.]",
        "Author Contributions": "[Conceptualization, X.X.; methodology, X.X.; ... (CRediT roles).]",
        "Contributors": "[Describe each author's contribution and name the authors who accessed and verified the data.]",
        "Competing interests": "[Declare any competing interests, or state: The authors declare no competing interests.]",
        "Declaration of interests": "[Declare any competing interests, or state: The authors declare no competing interests.]",
        "Disclosures": "[Disclosure forms provided by the authors; summarise any conflicts here.]",
        "Conflict of interest disclosures": "[Report each author's conflicts, or state that none were reported.]",
        "Conflicts of Interest": "[The authors declare no conflict of interest.]",
        "Funding": "[List all funding sources, or state: This research received no external funding.]",
        "Funding/support": "[List all funding sources and grant numbers.]",
        "Role of the funding source": "[Describe the funder's role, or state that the funder had no role in study design, data collection, analysis, interpretation or writing.]",
        "Article information": "[Author contributions, accepted for publication date and corresponding author are completed by the authors.]",
        "Institutional Review Board Statement": "Not applicable: computational study with no new human or animal data. [Revise if the input datasets contain human-subject data.]",
        "Informed Consent Statement": "Not applicable. [Revise if the input datasets contain data from human participants.]",
        "Additional information": "Supplementary Information is available for this paper. Correspondence and requests for materials should be addressed to [corresponding author].",
        "Resource availability": (
            "\\textbf{Lead contact.} [Name and email of the lead contact.] "
            "\\textbf{Materials availability.} This study did not generate new materials. "
            f"\\textbf{{Data and code availability.}} {data} {code}"
        ),
        "Declaration of generative AI and AI-assisted technologies": ai,
        "Supplementary Materials": "Supplementary materials accompany this manuscript: "
        + "; ".join(
            escape(i) for i in doc.supplement_items or ["Supplementary Information"]
        )
        + ".",
    }
    out = []
    for name in j.back_matter:
        if name == "STAR Methods":
            continue  # rendered as a section
        out.append((name, texts.get(name, "[To be completed by the authors.]")))
    # Every profile ends with an explicit AI-use statement unless it already has one.
    if not any("AI" in n or ai in t for n, t in out):
        out.append(("Use of artificial intelligence", ai))
    return out


def _abstract_paragraphs(doc: Doc) -> list[tuple[str | None, str]]:
    a = doc.adaptation.abstract
    if len(a) == 1 and a[0].heading == "Abstract":
        return [(None, _style_citations(sanitize(a[0].text), doc))]
    return [(s.heading, _style_citations(sanitize(s.text), doc)) for s in a]


def _key_points(doc: Doc) -> str:
    """JAMA: "a separate section called Key Points before the Abstract"."""
    a, j = doc.adaptation, doc.journal
    if not (j.key_points and a.key_points):
        return ""
    kp = a.key_points
    return (
        "\\section*{Key Points}\n"
        f"\\textbf{{Question:}} {sanitize(kp.question)}\n\n"
        f"\\textbf{{Findings:}} {sanitize(kp.findings)}\n\n"
        f"\\textbf{{Meaning:}} {sanitize(kp.meaning)}\n"
    )


def _front_extras(doc: Doc) -> list[tuple[str, str]]:
    """(heading, latex) blocks between the abstract and the main text."""
    a, j, out = doc.adaptation, doc.journal, []
    if j.research_in_context and a.research_in_context:
        r = a.research_in_context
        out.append(
            (
                "Research in context",
                (
                    f"\\textbf{{Evidence before this study}}\n\n{sanitize(r.evidence_before)}\n\n"
                    f"\\textbf{{Added value of this study}}\n\n{sanitize(r.added_value)}\n\n"
                    f"\\textbf{{Implications of all the available evidence}}\n\n{sanitize(r.implications)}"
                ),
            )
        )
    if j.highlights and a.highlights:
        items = "\n".join(f"\\item {sanitize(h)}" for h in a.highlights)
        out.append(("Highlights", f"\\begin{{itemize}}\n{items}\n\\end{{itemize}}"))
    if j.etoc_blurb and a.etoc_blurb:
        out.append(("eTOC blurb", sanitize(a.etoc_blurb)))
    if j.keywords and a.keywords:
        out.append(("Keywords", "; ".join(escape(k) for k in a.keywords)))
    return out


def main_sections(doc: Doc) -> list[tuple[str | None, str, bool]]:
    """(heading, body, figures_after) for the main text in the journal's order."""
    j, out = doc.journal, []
    limitations = _body(doc, "limitations")
    has_lim_section = any(s.lower().startswith("limitations") for s in j.sections)
    for name in j.sections:
        key = name.lower()
        if key == "introduction":
            out.append(
                (
                    None if j.key in UNHEADED_INTRO else name,
                    _body(doc, "introduction"),
                    False,
                )
            )
        elif key in ("methods", "materials and methods"):
            if j.methods_in_supplement:
                continue
            out.append((name, _body(doc, "methods"), False))
        elif key == "results":
            out.append((name, _body(doc, "results"), True))
        elif key == "discussion":
            body = _body(doc, "discussion")
            if limitations and not has_lim_section:
                body += "\n\n\\subsection*{Limitations}\n" + limitations
            out.append((name, body, False))
        elif key.startswith("limitations"):
            out.append((name, limitations, False))
        elif key == "conclusions":
            text = doc.adaptation.conclusions
            if text:
                out.append((name, _style_citations(sanitize(text), doc), False))
    if j.methods_in_supplement:
        out.append(
            (
                None,
                "Materials and methods are available as supplementary materials.",
                False,
            )
        )
    if "STAR Methods" in j.back_matter:
        out.append(
            (
                "STAR Methods",
                "\\subsection*{Method details}\n" + _body(doc, "methods"),
                False,
            )
        )
    return out


def _bib_label(style: CitationStyle) -> str:
    return {
        "ieee.csl": r"[#1]",
        "the-lancet.csl": r"#1",
        "american-chemical-society.csl": r"(#1)",
    }.get(style.csl, r"#1.")


def _natbib(style: CitationStyle) -> str:
    """Numbered styles are typeset by natbib; author-date citations arrive already
    formatted by citeproc, so natbib is loaded only for any stray command."""
    if style.cite == "super":
        # Superscripts separated by commas without spaces: 1,2 and 1-3 (natbib's
        # default separator is a semicolon).
        return "\\usepackage[super,sort&compress]{natbib}\n\\setcitestyle{citesep={,}}"
    if style.cite == "paren_italic":
        return (
            "\\usepackage[numbers,round,sort&compress]{natbib}\n"
            "\\setcitestyle{citesep={,}}\n"
            "\\renewcommand{\\citenumfont}[1]{\\textit{#1}}"
        )
    return "\\usepackage[numbers,square,sort&compress]{natbib}"


def _figure_latex(f: Figure, n: int, j: Journal, width: str = "\\linewidth") -> str:
    return (
        "\\begin{figure}[!htbp]\n\\centering\n"
        f"\\includegraphics[width={width},height=0.6\\textheight,keepaspectratio]{{{f.file}}}\n"
        f"\\caption{{\\textbf{{{escape(f.title)}.}} {escape(f.legend)}}}\n"
        f"\\label{{fig:{n}}}\n\\end{{figure}}\n"
    )


def _table_latex(t: Table) -> str:
    cols = "p{0.42\\linewidth}" + "l" * (len(t.header) - 1)
    head = " & ".join(f"\\textbf{{{escape(h)}}}" for h in t.header)
    rows = "\n".join(" & ".join(escape(c) for c in r) + " \\\\" for r in t.rows)
    notes = f"\n\\par\\smallskip{{\\footnotesize {escape(t.notes)}}}" if t.notes else ""
    return (
        "\\begin{table}[!htbp]\n\\centering\n"
        f"\\caption{{{escape(t.caption)}}}\n\\label{{tab:1}}\n\\small\n"
        f"\\begin{{tabular}}{{{cols}}}\n\\toprule\n{head} \\\\\n\\midrule\n{rows}\n\\bottomrule\n\\end{{tabular}}"
        f"{notes}\n\\end{{table}}\n"
    )


def main_text_words(doc: Doc) -> int:
    """Words in the main text: every section after the abstract, without title, abstract,
    acknowledgments, references, tables and figure legends (JAMA's definition)."""
    return sum(word_count(text) for _, text, _ in main_sections(doc))


def _authors(doc: Doc) -> tuple[str, str]:
    """(authors line, corresponding-author line) placeholders in the journal's form."""
    j = doc.journal
    if j.title_page_word_count:  # JAMA: highest degrees and complete contact details
        return (
            (
                "[Author One, highest academic degree]\\textsuperscript{1}, "
                "[Author Two, highest academic degree]\\textsuperscript{2}"
            ),
            "Corresponding author: [name, postal address, email, telephone]",
        )
    return (
        "[Author One]\\textsuperscript{1}, [Author Two]\\textsuperscript{2}",
        "*Corresponding author: [name, email]",
    )


def _extended_legends(doc: Doc) -> str:
    if not doc.extended:
        return ""
    items = "\n\n".join(
        f"\\textbf{{Extended Data Fig. {i} | {escape(f.title)}.}} {escape(f.legend)}"
        for i, f in enumerate(doc.extended, 1)
    )
    return f"\\section*{{Extended Data figure legends}}\n{items}\n"


def _figure_legends(doc: Doc) -> str:
    """Legends on their own, for journals that take figures as separate files."""
    label = "Fig." if doc.journal.figure_label == "Fig." else "Figure"
    items = "\n\n".join(
        f"\\textbf{{{label} {i}. {escape(f.title)}.}} {escape(f.legend)}"
        for i, f in enumerate(doc.figures, 1)
    )
    return f"\\section*{{Figure legends}}\n{items}\n" if items else ""


def _pdf_title(title: str) -> str:
    """The title as plain text for the PDF's metadata (no commands, maths kept as text)."""
    keep = "&%$#_"
    t = re.sub(r"\\cite[pt]?\{[^}]*\}", "", title)
    # Escaped symbols are parked on private-use characters while commands are removed.
    t = re.sub(r"\\([&%$#_])", lambda m: chr(0xE000 + keep.index(m.group(1))), t)
    t = re.sub(r"\\[a-zA-Z]+\*?\{([^}]*)\}", r"\1", t)
    t = re.sub(r"\\[a-zA-Z]+\*?|[\\{}$]", " ", t)
    t = "".join(keep[ord(c) - 0xE000] if 0xE000 <= ord(c) < 0xE005 else c for c in t)
    return escape(re.sub(r"\s+", " ", t).strip())


def latex_pdf(doc: Doc, bibliography: str) -> str:
    j = doc.journal
    style = doc.style
    size = f"{j.font_pt}pt,{j.paper}"
    margin = "1in" if j.paper == "letterpaper" else "2.5cm"
    pre = [
        f"\\documentclass[{size}]{{article}}",
        "% Generated by Plato for "
        + j.name
        + " ("
        + j.article_type
        + "); rules from "
        + j.source
        + "; references: "
        + style.name,
        "\\usepackage[T1]{fontenc}",
        "\\usepackage[utf8]{inputenc}",
        "\\usepackage{textcomp}",
        "\\usepackage{mathptmx}",
        "\\usepackage[scaled=0.92]{helvet}",
        "\\usepackage{amsmath,amssymb}",
        "\\usepackage{graphicx}",
        "\\usepackage{booktabs,array}",
        f"\\usepackage[margin={margin}]{{geometry}}",
        "\\usepackage{setspace}",
        "\\doublespacing" if j.double_spaced else "\\singlespacing",
        "\\usepackage[labelfont=bf,labelsep=period,font=small]{caption}",
        f"\\captionsetup[figure]{{name={'Fig.' if j.figure_label == 'Fig.' else 'Figure'}}}",
        "\\usepackage{float}",
        "\\usepackage{xcolor}",
        _natbib(style),
        f"\\renewcommand{{\\bibnumfmt}}[1]{{{_bib_label(style)}}}",
        "\\usepackage[hidelinks]{hyperref}",
        "\\usepackage{xurl}",  # long DOIs and URLs break anywhere instead of overrunning
        # The title PDF viewers show (in the tab, the window and document properties).
        f"\\hypersetup{{pdftitle={{{_pdf_title(doc.adaptation.title)}}}}}",
    ]
    if j.line_numbers:
        pre += ["\\usepackage[switch]{lineno}", "\\linenumbers"]
    if j.key == "science":
        pre.append("\\renewcommand{\\refname}{References and Notes}")
    pre += ["\\raggedbottom", "\\setlength{\\parskip}{0.4em}", "\\begin{document}"]
    if j.ragged_right:
        pre.append("\\raggedright")
    newpage = ["\\clearpage"] if j.section_page_breaks else []

    a = doc.adaptation
    title = sanitize(a.title)
    authors, corresponding = _authors(doc)
    lab = (lambda s: f"\\textbf{{{s}}} ") if j.key == "science" else (lambda s: "")
    head = [
        "\\begin{center}",
        f"{lab('Title:')}{{\\Large\\bfseries {title}\\par}}\\vspace{{1em}}",
        f"{lab('Authors:')}{authors}\\par",
        (
            f"{{\\small {lab('Affiliations:')}\\textsuperscript{{1}}[Affiliation, city, country]. "
            "\\textsuperscript{2}[Affiliation, city, country].\\par}"
        ),
        f"{{\\small {corresponding}\\par}}",
    ]
    if j.title_page_word_count:
        head.append(f"{{\\small Word count: {main_text_words(doc):,}\\par}}")
    head += ["\\end{center}", *newpage]
    body: list[str] = [_key_points(doc)]
    label = j.abstract.label
    paras = _abstract_paragraphs(doc)
    body.append(f"\\section*{{{label}{':' if j.key == 'science' else ''}}}")
    for h, text in paras:
        body.append((f"\\textbf{{{h}:}} " if h else "") + text + "\n")
    for h, text in _front_extras(doc):
        body.append(f"\\section*{{{h}}}\n{text}\n")
    body += newpage
    if j.key == "science":
        body.append("\\section*{Main Text:}")
    inline = not j.figures_separate
    figs_done = False

    def figures() -> None:
        if doc.table:
            body.append(_table_latex(doc.table))
        for i, f in enumerate(doc.figures, 1):
            body.append(_figure_latex(f, i, j))

    for heading, text, figures_after in main_sections(doc):
        if heading:
            body.append(f"\\section*{{{heading}}}")
        body.append(text + "\n")
        if figures_after and not figs_done and inline:
            figs_done = True
            figures()
    if not figs_done and inline:
        figures()
    stated = [f"\\paragraph{{{h}.}} {text}\n" for h, text in statements(doc)]
    if j.section_page_breaks:
        # JAMA order: text (with the article information), references, figure legends,
        # tables, each part on a new page.
        body += stated + ["\\clearpage", bibliography]
        if j.figures_separate:
            body += ["\\clearpage", _figure_legends(doc)]
            if doc.table:
                body += ["\\clearpage", _table_latex(doc.table)]
    else:
        body.append(bibliography)
        body += stated
        if j.figures_separate:
            body.append(_figure_legends(doc))
            if doc.table:
                body.append(_table_latex(doc.table))
    body.append(_extended_legends(doc))
    return "\n".join(pre + head + body + ["\\end{document}", ""])


def latex_pandoc(doc: Doc, image_ext: str = ".png") -> str:
    """Plain LaTeX for pandoc (Word and JATS). Citations stay as ``\\cite`` for citeproc;
    the reference list is inserted where ``refs`` sits and page breaks where
    ``PAGE_BREAK`` paragraphs sit."""
    j = doc.journal
    a = doc.adaptation
    paras = _abstract_paragraphs(doc)
    abstract = "\n\n".join((f"\\textbf{{{h}:}} " if h else "") + t for h, t in paras)
    authors, corresponding = _authors(doc)
    out = [
        "\\documentclass{article}",
        f"\\title{{{sanitize(a.title)}}}",
        f"\\author{{{authors}}}",
        "\\date{}",
        "\\begin{document}",
        "\\maketitle",
        (
            "\\textsuperscript{1}[Affiliation, city, country]. \\textsuperscript{2}[Affiliation, city, country]. "
            f"{corresponding.lstrip('*')}."
        ),
    ]
    brk = [PAGE_BREAK] if j.section_page_breaks else []
    if j.title_page_word_count:
        out.append(f"Word count: {main_text_words(doc):,}")
    out += brk
    # The abstract stays a LaTeX abstract (JATS front matter); the Word writer would
    # print it above the affiliations, so ABSTRACT_HERE marks where Word puts it.
    out.append(f"\\begin{{abstract}}\n{abstract}\n\\end{{abstract}}")
    out.append(_key_points(doc))
    out.append(ABSTRACT_HERE)
    for h, text in _front_extras(doc):
        out.append(f"\\section*{{{h}}}\n{text}")
    out += brk
    figs_done = False
    inline = not j.figures_separate

    # Word captions are not numbered automatically: write the labels out.
    label = "Fig." if j.figure_label == "Fig." else "Figure"
    table = (
        Table(
            f"Table 1. {doc.table.caption}",
            doc.table.header,
            doc.table.rows,
            doc.table.notes,
        )
        if doc.table
        else None
    )

    def figs() -> None:
        if table:
            out.append(_table_latex(table))
        for i, f in enumerate(doc.figures, 1):
            fig = Figure(
                re.sub(r"\.[a-z]+$", image_ext, f.file),
                f"{label} {i}. {f.title}",
                f.legend,
            )
            out.append(_figure_latex(fig, i, j))

    for heading, text, figures_after in main_sections(doc):
        if heading:
            out.append(f"\\section*{{{heading}}}")
        out.append(text)
        if figures_after and not figs_done and inline:
            figs_done = True
            figs()
    if not figs_done and inline:
        figs()
    refs = [
        "\\section*{"
        + ("References and Notes" if j.key == "science" else "References")
        + "}",
        "PLATOREFERENCES",
    ]
    stated = [f"\\section*{{{h}}}\n{text}" for h, text in statements(doc)]
    if j.section_page_breaks:
        out += stated + brk + refs
    else:
        out += refs + stated
    if j.figures_separate:
        out += brk + [_figure_legends(doc)]
        if table:
            out += brk + [_table_latex(table)]
    if doc.extended:
        out.append(_extended_legends(doc))
    out += ["\\end{document}", ""]
    return "\n\n".join(x for x in out if x)


def supplement_latex(
    doc: Doc,
    figures: list[Figure],
    tables: list[Table],
    methods: bool,
    bibliography: str = "",
) -> str:
    """Supplementary Information: Materials and Methods (when the journal moves them out
    of the main text), supplementary figures and tables, and a list of data files. The
    methods keep their citations, numbered as in the main text's reference list."""
    j = doc.journal
    margin = "1in" if j.paper == "letterpaper" else "2.5cm"
    s = [
        f"\\documentclass[11pt,{j.paper}]{{article}}",
        "\\usepackage[T1]{fontenc}\\usepackage[utf8]{inputenc}\\usepackage{textcomp}",
        "\\usepackage{mathptmx}\\usepackage[scaled=0.92]{helvet}\\usepackage{amsmath,amssymb}",
        "\\usepackage{graphicx}\\usepackage{booktabs,array,longtable}",
        f"\\usepackage[margin={margin}]{{geometry}}",
        "\\usepackage[labelfont=bf,labelsep=period,font=small]{caption}",
        _natbib(doc.style),
        f"\\renewcommand{{\\bibnumfmt}}[1]{{{_bib_label(doc.style)}}}",
        "\\usepackage[hidelinks]{hyperref}\\usepackage{xurl}",
        "\\renewcommand{\\thefigure}{S\\arabic{figure}}\\renewcommand{\\thetable}{S\\arabic{table}}",
        "\\begin{document}",
        (
            "\\begin{center}{\\Large\\bfseries Supplementary Information for\\par}\\vspace{0.5em}"
            f"{{\\large {sanitize(doc.adaptation.title)}\\par}}\\vspace{{0.5em}}"
            "[Author One], [Author Two]\\end{center}"
        ),
        "\\tableofcontents\\clearpage",
    ]
    if methods:
        s.append("\\section{Materials and Methods}")
        s.append(
            _body(doc, "methods")
            if bibliography
            else strip_citations(_body(doc, "methods"))
        )
    if figures:
        s.append("\\section{Supplementary Figures}")
        for i, f in enumerate(figures, 1):
            s.append(_figure_latex(f, 100 + i, j, width="0.85\\linewidth"))
    if tables:
        s.append("\\section{Supplementary Tables}")
        for t in tables:
            cols = "p{0.36\\linewidth}" + "l" * (len(t.header) - 1)
            head = " & ".join(f"\\textbf{{{escape(h)}}}" for h in t.header)
            rows = "\n".join(" & ".join(escape(c) for c in r) + " \\\\" for r in t.rows)
            s.append(
                f"\\begin{{longtable}}{{{cols}}}\n\\caption{{{escape(t.caption)}}}\\\\\n\\toprule\n{head} \\\\\n\\midrule\n\\endhead\n{rows}\n\\bottomrule\n\\end{{longtable}}"
            )
    s.append("\\section{Data files}")
    s.append(
        "The supplementary data package contains: \\texttt{data/} (metrics, figure source data "
        "as CSV and Excel, input datasets), \\texttt{code/} (each experiment's code), "
        "\\texttt{logs/} (execution logs), \\texttt{review/} (automated review reports) and "
        "\\texttt{MANIFEST.json} (SHA-256 checksums)."
    )
    if methods and bibliography:
        s.append(bibliography)
    s.append("\\section*{Note on this package}\n" + escape(AI_NOTE))
    s.append("\\end{document}\n")
    return "\n\n".join(s)
