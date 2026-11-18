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

## Local change

`american-medical-association.csl`: the `author` and `editor` `<names>` elements got an
explicit `<name/>` child. Without it pandoc's citeproc (3.1.x) printed the role label but no
names for those variables. The rendered output otherwise matches the upstream style.
