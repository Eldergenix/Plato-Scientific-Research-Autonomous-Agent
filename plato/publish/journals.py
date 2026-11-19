"""Submission profiles for the journals Plato can format a paper for.

Every number here comes from the journal's own author instructions, read on
2026-11-18 (``source`` and ``verified``). Where a journal publishes no LaTeX class we
can redistribute, the profile reproduces its rules (structure, limits, citation
style, spacing, statements) on the standard ``article`` class and says so in
``template_note``. Reference lists are rendered with the journal's official style
from the Citation Style Language repository (``csl``), so the PDF, the Word file and
the JATS XML all format references the same way.

Limits are what the journal states for its main research article type. ``None``
means the journal sets no limit for that item.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Literal

CSL_DIR = Path(__file__).parent / "csl"


@cache
def csl_title(csl: str) -> str:
    """The style's own name, from its ``<title>``."""
    m = re.search(r"<title>([^<]+)</title>", (CSL_DIR / csl).read_text("utf-8"))
    return m.group(1).strip() if m else csl.removesuffix(".csl")


CiteStyle = Literal["super", "paren_italic", "square", "author_date"]


@dataclass(frozen=True)
class CitationStyle:
    """How citations look in the text and in the reference list. ``csl`` is a file in
    ``plato/publish/csl``; ``cite`` is the in-text form: numbered (superscript, italic in
    parentheses, square brackets) or author-date, which citeproc renders in full."""

    key: str
    name: str
    csl: str
    cite: CiteStyle
    after_punctuation: bool = False
    description: str = ""

    @property
    def numeric(self) -> bool:
        return self.cite != "author_date"


# Styles a package can use instead of the journal's own (all official CSL styles).
STYLES: dict[str, CitationStyle] = {
    s.key: s
    for s in (
        CitationStyle(
            "apa",
            "APA 7th edition",
            "apa.csl",
            "author_date",
            description="Author-date: (Smith & Jones, 2020); references A-Z.",
        ),
        CitationStyle(
            "harvard",
            "Harvard (Cite Them Right 12th edition)",
            "harvard-cite-them-right.csl",
            "author_date",
            description="Author-date: (Smith and Jones, 2020); references A-Z.",
        ),
        CitationStyle(
            "chicago",
            "Chicago 18th edition (author-date)",
            "chicago-author-date.csl",
            "author_date",
            description="Author-date: (Smith and Jones 2020); references A-Z.",
        ),
        CitationStyle(
            "vancouver",
            "Vancouver / NLM (Citing Medicine)",
            "nlm-citation-sequence-brackets.csl",
            "square",
            description="Numbered in order of citation: [1]; the style PubMed indexes.",
        ),
        CitationStyle(
            "ama",
            "AMA 11th edition",
            "american-medical-association.csl",
            "super",
            after_punctuation=True,
            description="Numbered superscripts after punctuation.",
        ),
        CitationStyle(
            "nature",
            "Nature",
            "nature.csl",
            "super",
            description="Numbered superscripts.",
        ),
        CitationStyle(
            "acs",
            "ACS (American Chemical Society)",
            "american-chemical-society.csl",
            "super",
            description="Numbered superscripts; references (1), (2).",
        ),
        CitationStyle(
            "ieee",
            "IEEE",
            "ieee.csl",
            "square",
            description="Numbered in square brackets: [1].",
        ),
    )
}


@dataclass(frozen=True)
class AbstractSpec:
    """How the journal wants the abstract: one paragraph, or labelled sections."""

    max_words: int | None
    headings: tuple[str, ...] = ()  # empty: a single unlabelled paragraph
    citations_allowed: bool = False
    label: str = "Abstract"


@dataclass(frozen=True)
class Journal:
    key: str
    name: str
    publisher: str
    article_type: str
    source: str  # the author-instructions page these rules were read from
    verified: str
    csl: str  # file in plato/publish/csl
    cite: CiteStyle
    cite_after_punctuation: bool
    abstract: AbstractSpec
    title_max_chars: int | None = None
    title_max_words: int | None = None
    main_text_max_words: int | None = None
    references_max: int | None = None
    display_items_max: int | None = None
    methods_max_words: int | None = None
    legend_max_words: int | None = None
    double_spaced: bool = False
    line_numbers: bool = False
    paper: Literal["letterpaper", "a4paper"] = "letterpaper"
    font_pt: int = 12
    # The manuscript file the journal asks for at first submission, in order of preference.
    manuscript_formats: tuple[str, ...] = ("pdf", "docx")
    # Body section headings, in order. The adapter maps the paper's sections onto them.
    sections: tuple[str, ...] = ("Introduction", "Results", "Discussion", "Methods")
    methods_in_supplement: bool = False
    # Extra front matter the journal requires (generated by the adapter).
    key_points: bool = False
    highlights: bool = False  # Cell: 3-4 bullets of <= 85 characters
    etoc_blurb: bool = False
    research_in_context: bool = False  # The Lancet panel
    keywords: tuple[int, int] | None = None  # (min, max)
    # Statements printed after the main text, in the journal's order and wording.
    back_matter: tuple[str, ...] = ()
    figure_label: str = "Figure"
    decimal_midpoint: bool = False  # The Lancet prints decimals as 0·5
    template_note: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)
    # False when the venue prescribes no reference style (arXiv): any style passes.
    style_required: bool = True
    # JAMA: the title page carries the main-text word count; text is ragged right; each
    # part starts on a new page; figures are separate files with their legends at the end.
    title_page_word_count: bool = False
    ragged_right: bool = False
    section_page_breaks: bool = False
    figures_separate: bool = False
    # Nature: figures beyond the main display items are Extended Data (separate files,
    # legends at the end of the manuscript); the Supplementary Information has no figures.
    extended_data_max: int | None = None
    # What the cover letter must say beyond the standard declarations (None: no letter).
    cover_letter: tuple[str, ...] | None = ()
    # Forms the authors complete themselves: (name, official URL).
    forms: tuple[tuple[str, str], ...] = ()

    @property
    def style(self) -> CitationStyle:
        """The journal's own citation style."""
        return CitationStyle(
            "journal",
            csl_title(self.csl),
            self.csl,
            self.cite,
            self.cite_after_punctuation,
        )


AI_NOTE = (
    "This manuscript was drafted by an automated research system (Plato). Journals require "
    "human authors who take responsibility for the work and a disclosure of AI use; the AI "
    "system cannot be listed as an author. Replace the author placeholders and review every "
    "claim before submitting."
)

JOURNALS: dict[str, Journal] = {
    j.key: j
    for j in (
        Journal(
            key="nature",
            name="Nature",
            publisher="Springer Nature",
            article_type="Article",
            source="https://www.nature.com/nature/for-authors/formatting-guide",
            verified="2026-11-18",
            csl="nature.csl",
            cite="super",
            cite_after_punctuation=False,
            abstract=AbstractSpec(
                max_words=200, citations_allowed=True, label="Summary paragraph"
            ),
            title_max_chars=75,
            main_text_max_words=4300,  # 8-page Article with 5-6 display items
            references_max=50,
            display_items_max=6,
            methods_max_words=3000,
            legend_max_words=300,
            double_spaced=True,
            line_numbers=True,
            manuscript_formats=("pdf", "docx", "tex"),
            sections=("Introduction", "Results", "Discussion", "Methods"),
            back_matter=(
                "Data availability",
                "Code availability",
                "Acknowledgements",
                "Author contributions",
                "Competing interests",
                "Additional information",
            ),
            template_note=(
                "Nature accepts LaTeX (all text, references, tables and legends in one .tex "
                "file) and a single PDF up to 30 MB at first submission; it converts to Word "
                "after acceptance. There is no Nature-specific class to install."
            ),
            notes=(
                "Summary paragraph: ideally no more than 200 words, fully referenced.",
                "Title: at most 75 characters including spaces.",
                "About 2,500 words for a 6-page Article, 4,300 for 8 pages.",
                (
                    "Methods typically no more than 3,000 words, with separate Data and Code "
                    "availability statements."
                ),
                "Typically no more than 50 references (Methods references not counted).",
                "Double-spaced, line-numbered, 12-point Times New Roman.",
                "Life-science Articles also need a Reporting Summary.",
            ),
            extended_data_max=10,
            cover_letter=(
                "Explain why the work is of interest to a broad scientific readership.",
            ),
            forms=(
                (
                    "Reporting Summary (life sciences and behavioural and social sciences)",
                    "https://www.nature.com/documents/nr-reporting-summary.pdf",
                ),
            ),
        ),
        Journal(
            key="nature-communications",
            name="Nature Communications",
            publisher="Springer Nature",
            article_type="Article",
            source="https://www.nature.com/ncomms/submit/article",
            verified="2026-11-18",
            csl="nature.csl",
            cite="super",
            cite_after_punctuation=False,
            abstract=AbstractSpec(max_words=200, citations_allowed=False),
            title_max_words=15,
            main_text_max_words=5000,
            references_max=70,
            display_items_max=10,
            methods_max_words=3000,
            legend_max_words=350,
            double_spaced=True,
            line_numbers=True,
            manuscript_formats=("pdf", "docx", "tex"),
            sections=("Introduction", "Results", "Discussion", "Methods"),
            back_matter=(
                "Data availability",
                "Code availability",
                "Acknowledgements",
                "Author contributions",
                "Competing interests",
            ),
            template_note=(
                "Initial submissions are format-free; the editor sends formatting "
                "instructions at revision. Nature Portfolio reference style is used."
            ),
            notes=(
                "Abstract: no more than 200 words and no references.",
                "Title: at most 15 words.",
                "Main text ideally at most 5,000 words; Methods typically under 3,000.",
                "At most 70 references and up to 10 display items.",
                "Discussion has no subheadings.",
            ),
        ),
        Journal(
            key="science",
            name="Science",
            publisher="AAAS",
            article_type="Research Article",
            source="https://www.science.org/content/page/instructions-preparing-initial-manuscript",
            verified="2026-11-18",
            csl="science.csl",
            cite="paren_italic",
            cite_after_punctuation=False,
            abstract=AbstractSpec(max_words=125, citations_allowed=False),
            title_max_chars=96,
            main_text_max_words=3000,
            references_max=50,
            display_items_max=5,
            legend_max_words=200,
            double_spaced=False,
            line_numbers=False,
            paper="letterpaper",
            manuscript_formats=("docx", "pdf"),
            sections=("Introduction", "Results", "Discussion"),
            methods_in_supplement=True,
            back_matter=(
                "Acknowledgments",
                "Funding",
                "Author contributions",
                "Competing interests",
                "Data, code, and materials availability",
                "Supplementary Materials",
            ),
            figure_label="Fig.",
            template_note=(
                "Science prefers one .docx with figures and tables embedded. LaTeX users "
                "should convert to .docx, or use Science's own LaTeX template and upload "
                "a PDF. Materials and Methods go in the Supplementary Materials."
            ),
            notes=(
                (
                    "Research Article: main text at most 3,000 words, 3 to 5 display items, "
                    "about 50 main-text references."
                ),
                "Abstract: 125 words or less, no citations or abbreviations.",
                "Title: at most 96 characters including spaces.",
                "Single-spaced, US letter, Times New Roman.",
                (
                    "Citations are italic numbers in parentheses, e.g. (18, 19); reference "
                    "lists give every author (no et al.)."
                ),
                "Figure captions: bold one-line title, at most 200 words.",
                "Data underlying figures as Data S1, a multi-sheet Excel workbook.",
            ),
        ),
        Journal(
            key="cell",
            name="Cell",
            publisher="Cell Press",
            article_type="Research article",
            source="https://www.cell.com/cell/information-for-authors/article-types",
            verified="2026-11-18",
            csl="cell.csl",
            cite="super",
            cite_after_punctuation=False,
            abstract=AbstractSpec(
                max_words=150, citations_allowed=False, label="Summary"
            ),
            main_text_max_words=7000,  # includes main figure legends
            display_items_max=7,
            double_spaced=True,
            line_numbers=True,
            manuscript_formats=("docx", "pdf"),
            sections=(
                "Introduction",
                "Results",
                "Discussion",
                "Limitations of the study",
            ),
            highlights=True,
            etoc_blurb=True,
            keywords=(3, 10),
            back_matter=(
                "Resource availability",
                "Acknowledgments",
                "Author contributions",
                "Declaration of interests",
                "Declaration of generative AI and AI-assisted technologies",
                "STAR Methods",
            ),
            template_note=(
                "Cell takes a single PDF or Word file at first submission. Cell Press "
                "offers an optional template; LaTeX is converted to Word for copyediting. "
                "STAR Methods formatting is finalised with the editor at acceptance."
            ),
            notes=(
                (
                    "Under 7,000 words including main figure legends (STAR Methods, "
                    "supplemental legends and references excluded); at most 7 figures and/or "
                    "tables."
                ),
                (
                    "Summary of at most 150 words; 3-4 Highlights of at most 85 characters; "
                    "eTOC blurb of at most 50 words."
                ),
                (
                    "Section order: Summary, Keywords, Introduction, Results, Limitations of "
                    "the study, Discussion, Resource availability, then STAR Methods."
                ),
                "References are numbered (Cell style; up to 10 authors, then et al.).",
            ),
        ),
        Journal(
            key="nejm",
            name="The New England Journal of Medicine",
            publisher="Massachusetts Medical Society",
            article_type="Original Article",
            source="https://www.nejm.org/author-center/new-manuscripts",
            verified="2026-11-18",
            csl="the-new-england-journal-of-medicine.csl",
            cite="super",
            cite_after_punctuation=True,
            abstract=AbstractSpec(
                max_words=250,
                headings=("Background", "Methods", "Results", "Conclusions"),
            ),
            main_text_max_words=2700,
            references_max=40,
            display_items_max=5,
            double_spaced=True,
            line_numbers=False,
            manuscript_formats=("docx", "pdf"),
            sections=("Introduction", "Methods", "Results", "Discussion"),
            back_matter=("Acknowledgments", "Disclosures", "Data sharing statement"),
            template_note=(
                "NEJM wants one double-spaced file (preferably Word) with text, "
                "references, legends and tables. The Supplementary Appendix must be sent "
                "as both PDF and Word, paginated with a table of contents."
            ),
            notes=(
                (
                    "Original Article: at most 2,700 words (introduction to discussion), "
                    "at most 5 tables and figures, up to 40 references."
                ),
                (
                    "Abstract: at most 250 words in four labelled paragraphs (Background, "
                    "Methods, Results, Conclusions), plus a trial registration number if any."
                ),
                (
                    "References double-spaced; six or fewer authors listed in full, seven or "
                    "more as the first three and et al."
                ),
                "Submit the protocol and statistical analysis plan when applicable.",
            ),
        ),
        Journal(
            key="lancet",
            name="The Lancet",
            publisher="Elsevier",
            article_type="Article",
            source="https://www.thelancet.com/pb-assets/Lancet/authors/tl-info-for-authors-1787150940677.pdf",
            verified="2026-11-18",
            csl="the-lancet.csl",
            cite="super",
            cite_after_punctuation=True,
            abstract=AbstractSpec(
                max_words=300,
                headings=(
                    "Background",
                    "Methods",
                    "Findings",
                    "Interpretation",
                    "Funding",
                ),
                label="Summary",
            ),
            main_text_max_words=3500,  # 4,500 for randomised controlled trials
            references_max=30,
            double_spaced=True,
            line_numbers=False,
            paper="a4paper",
            manuscript_formats=("docx", "pdf"),
            sections=("Introduction", "Methods", "Results", "Discussion"),
            research_in_context=True,
            back_matter=(
                "Contributors",
                "Declaration of interests",
                "Data sharing",
                "Acknowledgments",
                "Role of the funding source",
            ),
            decimal_midpoint=True,
            template_note=(
                "The Lancet has no LaTeX class; this follows its Information for Authors "
                "(Vancouver superscript citations after punctuation, mid-line decimal "
                "points, Research in context panel). Supplementary material goes in one "
                "PDF with a table of contents."
            ),
            notes=(
                "Article: up to 3,500 words (4,500 for randomised trials) and 30 references.",
                (
                    "Summary: at most 300 words in five paragraphs (Background, Methods, "
                    "Findings, Interpretation, Funding), no references."
                ),
                (
                    "Research in context panel (Evidence before this study, Added value of "
                    "this study, Implications of all the available evidence), no references."
                ),
                "Data sharing statement required at the end of the manuscript.",
                "Seven or more authors: first three, then et al.",
            ),
        ),
        Journal(
            key="jama",
            name="JAMA",
            publisher="American Medical Association",
            article_type="Original Investigation",
            source="https://jamanetwork.com/journals/jama/pages/instructions-for-authors",
            verified="2026-11-18",
            csl="american-medical-association.csl",
            cite="super",
            cite_after_punctuation=True,
            abstract=AbstractSpec(
                max_words=350,
                headings=(
                    "Importance",
                    "Objective",
                    "Design, Setting, and Participants",
                    "Exposures",
                    "Main Outcomes and Measures",
                    "Results",
                    "Conclusions and Relevance",
                ),
            ),
            main_text_max_words=3000,
            references_max=75,
            display_items_max=5,
            double_spaced=True,
            line_numbers=False,
            manuscript_formats=("docx",),
            sections=(
                "Introduction",
                "Methods",
                "Results",
                "Discussion",
                "Conclusions",
            ),
            key_points=True,
            back_matter=(
                "Article information",
                "Conflict of interest disclosures",
                "Funding/support",
                "Data sharing statement",
            ),
            template_note=(
                "JAMA takes the manuscript as a Word document only (no PDF), double-spaced "
                "in 10-12 point type with a ragged right margin. The PDF here is for your "
                "own review."
            ),
            notes=(
                "Original Investigation: at most 3,000 words and 5 tables/figures.",
                "Structured abstract of at most 350 words.",
                (
                    "Key Points (Question, Findings, Meaning) of 75-100 words before the "
                    "abstract."
                ),
                (
                    "AMA Manual of Style, 11th edition (references: first three authors and "
                    "et al. when there are more than six)."
                ),
                "Individual files ideally at most 1 MB; all files at most 5 MB.",
            ),
            title_page_word_count=True,
            ragged_right=True,
            section_page_breaks=True,
            figures_separate=True,
            cover_letter=(
                (
                    "Give the corresponding author's affiliation, postal address, email and "
                    "telephone."
                ),
                (
                    "State whether the authors have published, posted or submitted any related "
                    "papers from the same study."
                ),
            ),
        ),
        Journal(
            key="genes",
            name="Genes (MDPI)",
            publisher="MDPI",
            article_type="Article",
            source="https://www.mdpi.com/journal/genes/instructions",
            verified="2026-11-18",
            csl="multidisciplinary-digital-publishing-institute.csl",
            cite="square",
            cite_after_punctuation=False,
            abstract=AbstractSpec(
                max_words=250,
                headings=("Background/Objectives", "Methods", "Results", "Conclusions"),
            ),
            double_spaced=False,
            line_numbers=False,
            paper="a4paper",
            manuscript_formats=("docx", "pdf", "tex"),
            sections=(
                "Introduction",
                "Materials and Methods",
                "Results",
                "Discussion",
                "Conclusions",
            ),
            keywords=(3, 10),
            back_matter=(
                "Supplementary Materials",
                "Author Contributions",
                "Funding",
                "Institutional Review Board Statement",
                "Informed Consent Statement",
                "Data Availability Statement",
                "Acknowledgments",
                "Conflicts of Interest",
            ),
            template_note=(
                "MDPI publishes Word and LaTeX templates, but their terms forbid "
                "reposting them, so they are not bundled. MDPI accepts free-format "
                "first submissions that contain the required sections; LaTeX submissions "
                "are a ZIP of all sources and images."
            ),
            notes=(
                (
                    "Structured abstract of about 250 words (Background/Objectives, Methods, "
                    "Results, Conclusions)."
                ),
                "3 to 10 keywords.",
                "Citations in square brackets before punctuation, e.g. [1], [1-3].",
                "Total submission at most 120 MB.",
            ),
        ),
        Journal(
            key="arxiv",
            name="arXiv",
            publisher="Cornell University",
            article_type="Preprint",
            source="https://info.arxiv.org/help/submit_tex.html",
            verified="2026-11-18",
            # arXiv prescribes no reference style; IEEE's numbered style reads well in preprints.
            csl="ieee.csl",
            cite="square",
            cite_after_punctuation=False,
            abstract=AbstractSpec(max_words=None, citations_allowed=False),
            double_spaced=False,
            line_numbers=False,
            manuscript_formats=("tex", "pdf"),
            sections=(
                "Introduction",
                "Methods",
                "Results",
                "Discussion",
                "Limitations",
            ),
            back_matter=("Data and code availability", "Acknowledgments"),
            template_note=(
                "Upload the arxiv/ folder as a .tar.gz or .zip: arXiv compiles main.tex "
                "itself with pdfLaTeX. The bibliography is inlined, so no .bbl or BibTeX "
                "run is needed. Data and code ride along as ancillary files in anc/."
            ),
            notes=(
                "Single-spaced (arXiv asks authors not to submit in referee mode).",
                "Figures are PDF/PNG/JPEG for pdfLaTeX.",
                "No hidden files, no build outputs (.aux, .log, .pdf) in the upload.",
            ),
            style_required=False,
            cover_letter=None,
        ),
    )
}


def get(key: str) -> Journal:
    try:
        return JOURNALS[key]
    except KeyError:
        raise KeyError(f"unknown journal {key!r}") from None


def style_for(j: Journal, key: str | None = None) -> CitationStyle:
    """The style a package uses: the journal's own unless another one is chosen."""
    if not key or key == "journal":
        return j.style
    try:
        return STYLES[key]
    except KeyError:
        raise KeyError(f"unknown citation style {key!r}") from None


def styles_catalogue() -> list[dict]:
    return [
        {"key": s.key, "name": s.name, "description": s.description}
        for s in STYLES.values()
    ]


def catalogue() -> list[dict]:
    """The public description of every profile (served to the UI)."""
    out = []
    for j in JOURNALS.values():
        out.append(
            {
                "key": j.key,
                "name": j.name,
                "publisher": j.publisher,
                "article_type": j.article_type,
                "source": j.source,
                "verified": j.verified,
                "formats": list(j.manuscript_formats),
                "limits": {
                    "title_chars": j.title_max_chars,
                    "title_words": j.title_max_words,
                    "abstract_words": j.abstract.max_words,
                    "main_text_words": j.main_text_max_words,
                    "references": j.references_max,
                    "display_items": j.display_items_max,
                },
                "template_note": j.template_note,
                "notes": list(j.notes),
                "style_required": j.style_required,
                "citation_style": j.style.name,
            }
        )
    return out
