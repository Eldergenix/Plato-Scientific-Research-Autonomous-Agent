# Citation styles

These Citation Style Language files come from the official CSL style repository
(<https://github.com/citation-style-language/styles>, the styles Zotero and Mendeley use).
Each file keeps its original `<info>` block with its authors, its `rel="self"` link and its
licence: **Creative Commons Attribution-ShareAlike 3.0**
(<http://creativecommons.org/licenses/by-sa/3.0/>). Changes to them are shared under the same
licence.

| File | Style | Used for |
|---|---|---|
| `nature.csl` | Nature | Nature, Nature Communications |
| `science.csl` | Science | Science |
| `cell.csl` | Cell | Cell |
| `the-new-england-journal-of-medicine.csl` | The New England Journal of Medicine | NEJM |
| `the-lancet.csl` | The Lancet | The Lancet |
| `american-medical-association.csl` | AMA Manual of Style, 11th edition | JAMA |
| `multidisciplinary-digital-publishing-institute.csl` | MDPI | Genes |
| `ieee.csl` | IEEE | arXiv (numeric, compact) |
| `apa.csl` | APA 7th edition | selectable style (author-date) |
| `harvard-cite-them-right.csl` | Harvard (Cite Them Right) | selectable style (author-date) |
| `chicago-author-date.csl` | Chicago author-date | selectable style (author-date) |
| `nlm-citation-sequence-brackets.csl` | NLM/Vancouver, numbered in brackets | selectable style |
| `american-chemical-society.csl` | ACS | selectable style |

Any style can be chosen for any journal at export (`style=` on the export endpoint). A
journal's own style is the default; choosing another is built and flagged in the checks.

## Local changes

`american-medical-association.csl`: the `author` and `editor` `<names>` elements got an
explicit `<name/>` child. Without it pandoc's citeproc (3.1.x) printed the role label but no
names for those variables. The rendered output otherwise matches the upstream style.

`nlm-citation-sequence-brackets.csl`: the same `<name/>` fix for the `author`, `editor` and
`collection-editor` `<names>`; without it citeproc printed full given names instead of initials.

`cell.csl`: the final access macro is skipped for `article`, `dataset` and `software` items,
which already print their DOI; upstream printed the DOI twice for preprints.

`multidisciplinary-digital-publishing-institute.csl`: an `article` (preprint) branch prints
"Title. Server Year, Identifier."; upstream dropped the arXiv identifier.
