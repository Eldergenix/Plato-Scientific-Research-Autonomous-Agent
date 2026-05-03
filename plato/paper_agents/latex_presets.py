from .journal import Journal, LatexPresets

#---
# Latex journal presets definition
#---

latex_none = LatexPresets(article="article",
                         affiliation=lambda x: rf"\date{{{x}}}",
                         abstract=lambda x: f"\\maketitle\n\\begin{{abstract}}\n{x}\n\\end{{abstract}}\n",
                         bibliographystyle=r"\bibliographystyle{unsrt}",
                         )
"""No Latex preset"""

latex_aas = LatexPresets(article="aastex631",
                         layout="twocolumn",
                         usepackage=r"\usepackage{aas_macros}",
                         abstract=lambda x: f"\\begin{{abstract}}\n{x}\n\\end{{abstract}}\n",
                         keywords=lambda x: f"\\keywords{{{x}}}",
                         bibliographystyle=r"\bibliographystyle{aasjournal}",
                         files=['aasjournal.bst', 'aastex631.cls', 'aas_macros.sty'],
                         )
"""AAS Latex preset"""

latex_aps = LatexPresets(article="revtex4-2",
                         layout="aps",
                         abstract=lambda x: f"\\begin{{abstract}}\n{x}\n\\end{{abstract}}\n\\maketitle",
                         )
"""APS Latex preset"""

latex_icml = LatexPresets(article="article",
                        title="\\twocolumn[\n\\icmltitle",
                        author=lambda x: f"\\begin{{icmlauthorlist}}\n\\icmlauthor{{{x}}}{{aff}}\n\\end{{icmlauthorlist}}",
                        usepackage=r"\usepackage[accepted]{icml2025}",
                        affiliation=lambda x: f"\\icmlaffiliation{{aff}}{{{x}}}\n",
                        abstract=lambda x: f"]\n\\printAffiliationsAndNotice{{}}\n\\begin{{abstract}}\n{x}\n\\end{{abstract}}\n",
                        keywords=lambda x: f"\\icmlkeywords{{{x}}}",
                        bibliographystyle=r"\bibliographystyle{icml2025}",
                        files=['icml2025.sty',"icml2025.bst","fancyhdr.sty"],
                         )
"""ICML Latex preset"""

latex_jhep = LatexPresets(article="article",
                         usepackage=r"\usepackage{jcappub}",
                         abstract=lambda x: f"\\abstract{{\n{x}\n}}\n\\maketitle",
                         bibliographystyle=r"\bibliographystyle{JHEP}",
                         files=['JHEP.bst', 'jcappub.sty'],
                         )
"""JHEP Latex preset"""

latex_neurips = LatexPresets(article="article",
                        usepackage=r"\usepackage[final]{neurips_2025}",
                        author=lambda x: f"\\author{{\n{x}\\\\",
                        affiliation=lambda x: f"{x}\n}}",
                        abstract=lambda x: f"\\maketitle\n\\begin{{abstract}}\n{x}\n\\end{{abstract}}\n",
                        bibliographystyle=r"\bibliographystyle{unsrt}",
                        files=['neurips_2025.sty']
                         )
"""NeurIPS Latex preset"""

latex_pasj = LatexPresets(article="pasj01",
                         layout="twocolumn",
                         usepackage=r"\usepackage{aas_macros}",
                         affiliation=lambda x: rf"\altaffiltext{{1}}{{{x}}}",
                         abstract=lambda x: f"\\maketitle\n\\begin{{abstract}}\n{x}\n\\end{{abstract}}",
                         bibliographystyle=r"\bibliographystyle{aasjournal}",
                         files=['aasjournal.bst', 'pasj01.cls', 'aas_macros.sty'],
                         )
"""PASJ Latex preset"""

# Biology presets — none ship .cls/.bst with Plato today, so all fall back
# to the standard ``article`` class. See LaTeX/README.md for manual-install
# instructions for the native journal classes.

latex_nature = LatexPresets(
    article="article",
    usepackage="\\usepackage{lineno}\n\\linenumbers",
    abstract=lambda x: f"\\maketitle\n\\begin{{abstract}}\n{x}\n\\end{{abstract}}\n",
    bibliographystyle=r"\bibliographystyle{naturemag}",
)
"""Nature LaTeX preset (article fallback; install naturemag.cls for native formatting)"""

latex_cell = LatexPresets(
    article="article",
    usepackage="\\usepackage{lineno}\n\\linenumbers\n\\usepackage{setspace}\n\\doublespacing",
    abstract=lambda x: f"\\maketitle\n\\begin{{abstract}}\n{x}\n\\end{{abstract}}\n",
    bibliographystyle=r"\bibliographystyle{unsrt}",
)
"""Cell LaTeX preset (article fallback; Cell Press has no public CTAN class)"""

latex_science = LatexPresets(
    article="article",
    usepackage="\\usepackage{lineno}\n\\linenumbers",
    abstract=lambda x: f"\\maketitle\n\\begin{{abstract}}\n{x}\n\\end{{abstract}}\n",
    bibliographystyle=r"\bibliographystyle{Science}",
)
"""Science (AAAS) LaTeX preset (article fallback; no public CTAN class)"""

latex_plos_bio = LatexPresets(
    article="article",
    usepackage="\\usepackage{lineno}\n\\linenumbers",
    abstract=lambda x: f"\\maketitle\n\\begin{{abstract}}\n{x}\n\\end{{abstract}}\n",
    bibliographystyle=r"\bibliographystyle{plos2015}",
)
"""PLOS Biology LaTeX preset (article fallback; install plos2015.cls for native formatting)"""

latex_elife = LatexPresets(
    article="article",
    usepackage="\\usepackage{lineno}\n\\linenumbers",
    abstract=lambda x: f"\\maketitle\n\\begin{{abstract}}\n{x}\n\\end{{abstract}}\n",
    bibliographystyle=r"\bibliographystyle{unsrt}",
)
"""eLife LaTeX preset (article fallback; install elife.cls via ``tlmgr install elife``)"""

#---

journal_dict = {
    Journal.NONE: latex_none,
    Journal.AAS: latex_aas,
    Journal.APS: latex_aps,
    Journal.ICML: latex_icml,
    Journal.JHEP: latex_jhep,
    Journal.NeurIPS: latex_neurips,
    Journal.PASJ: latex_pasj,
    Journal.NATURE: latex_nature,
    Journal.CELL: latex_cell,
    Journal.SCIENCE: latex_science,
    Journal.PLOS_BIO: latex_plos_bio,
    Journal.ELIFE: latex_elife,
}
"""Dictionary to relate the journal with their presets."""
