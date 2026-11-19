"""The cover letter to the editor, written from the package itself (no model call).

Every journal here except arXiv asks for a cover letter at submission. The letter states
what is submitted, what it found (the front matter's conclusions), its size, and the
declarations editors expect; what only the authors can say is left as bracketed
placeholders, which the submission checklist lists. Journal-specific contents
(``Journal.cover_letter``) come from the journal's own instructions.
"""

from __future__ import annotations

from .adapt import JournalAdaptation
from .journals import Journal
from .texsafe import plain_text


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def cover_letter_md(
    j: Journal,
    adaptation: JournalAdaptation,
    *,
    words: int,
    display_items: int,
    references: int,
    style_name: str,
    model: str,
    supplement: list[str],
) -> str:
    title = plain_text(adaptation.title)
    summary = plain_text(adaptation.conclusions) or " ".join(
        plain_text(s.text) for s in adaptation.abstract
    )
    contact = (
        "[name, highest academic degree, affiliation, postal address, email, telephone]"
        if j.title_page_word_count
        else "[name, affiliation, email]"
    )
    asks = [f"[{a}]" for a in (j.cover_letter or ())]
    lines = [
        "[Date]",
        "",
        "[Editor's name]  ",
        f"{j.name}  ",
        j.publisher,
        "",
        "Dear [Editor's name],",
        "",
        (
            f'We submit our manuscript "{title}" for consideration as '
            f"{_article(j.article_type)} {j.article_type} in {j.name}."
        ),
        "",
        summary,
        "",
        (
            "[Explain in two or three sentences why these findings matter to the readers "
            f"of {j.name}.]"
        ),
    ]
    if asks:
        lines += ["", *asks]
    lines += [
        "",
        (
            f"The manuscript has {words:,} words of main text, {display_items} display "
            f"item{'s' if display_items != 1 else ''} and {references} "
            f"reference{'s' if references != 1 else ''} (cited in {style_name}), "
            "formatted to "
            f"{j.name}'s instructions for authors. "
            + (
                "It is accompanied by "
                + ", ".join(supplement)
                + ", the source data and the analysis code."
                if supplement
                else "The source data and the analysis code accompany it."
            )
        ),
        "",
        "We confirm that:",
        "",
        (
            "- the manuscript has not been published and is not under consideration "
            "elsewhere [list any related manuscripts, preprints or posted versions from "
            "the same study];"
        ),
        (
            "- all authors have read and approved the submission and take responsibility "
            "for its content;"
        ),
        (
            "- [Declare any competing interests, or state that the authors declare no "
            "competing interests.];"
        ),
        (
            "- the experiments, analyses and first draft were produced with Plato, an "
            f"automated research system using the {model} language model, and [State how "
            "the authors checked the code, the results and the text.]."
        ),
        "",
        f"Corresponding author: {contact}",
        "",
        "Sincerely,",
        "",
        "[Corresponding author]",
        "",
    ]
    return "\n".join(lines)


__all__ = ["cover_letter_md"]
