"""Make model-written LaTeX safe and portable before it is compiled or converted.

The manuscript body was written by a model that read untrusted text (paper abstracts,
experiment output), so it is treated as hostile input:

* control sequences that read or write files, run commands or redefine the language
  (``\\input``, ``\\write18``, ``\\catcode``, ``\\def`` ...) are removed;
* non-ASCII characters pdfLaTeX cannot typeset with T1 fonts are mapped to LaTeX;
* citation commands are normalised to ``\\cite{...}``.

This is defence in depth: the TeX and pandoc runs also execute as an unprivileged user
with a scrubbed environment and ``openin_any=p`` (see ``tools.run_tool``).
"""

from __future__ import annotations

import re
import unicodedata

# Primitives and macros that touch files, the shell, catcodes or definitions.
_FORBIDDEN = (
    "input",
    "include",
    "includeonly",
    "InputIfFileExists",
    "openin",
    "openout",
    "read",
    "readline",
    "write",
    "immediate",
    "closein",
    "closeout",
    "newread",
    "newwrite",
    "catcode",
    "lccode",
    "uccode",
    "def",
    "edef",
    "gdef",
    "xdef",
    "let",
    "futurelet",
    "newcommand",
    "renewcommand",
    "providecommand",
    "DeclareRobustCommand",
    "newenvironment",
    "renewenvironment",
    "csname",
    "endcsname",
    "expandafter",
    "special",
    "pdfobj",
    "pdfliteral",
    "pdffiledump",
    "pdfmdfivesum",
    "directlua",
    "usepackage",
    "RequirePackage",
    "documentclass",
    "begin{document}",
    "end{document}",
    "verbatiminput",
    "lstinputlisting",
    "includegraphics",
    "includepdf",
    "makeatletter",
    "makeatother",
    "scantokens",
    "endinput",
    "batchmode",
    "errorstopmode",
    "nonstopmode",
    "scrollmode",
    "loop",
    "repeat",
)
_FORBIDDEN_RE = re.compile(
    r"\\(?:"
    + "|".join(re.escape(c) for c in sorted(_FORBIDDEN, key=len, reverse=True))
    + r")(?![A-Za-z])"
)
# Environments that typeset raw file contents or define code.
_FORBIDDEN_ENV_RE = re.compile(
    r"\\begin\{(filecontents\*?|verbatim\*?|lstlisting|minted|comment)\}.*?\\end\{\1\}",
    re.DOTALL,
)
_CITE_RE = re.compile(
    r"\\(?:cite|citep|citet|citealp|citeauthor|citeyear|parencite|textcite|autocite)\*?(?:\[[^\]]*\]){0,2}\{([^}]*)\}"
)

# Characters pdfLaTeX (T1 + utf8 inputenc) cannot typeset on its own.
_UNICODE = {
    "\u00b1": r"\ensuremath{\pm}",
    "\u00d7": r"\ensuremath{\times}",
    "\u00f7": r"\ensuremath{\div}",
    "\u00b7": r"\ensuremath{\cdot}",
    "\u2212": r"\ensuremath{-}",
    "\u2264": r"\ensuremath{\leq}",
    "\u2265": r"\ensuremath{\geq}",
    "\u2260": r"\ensuremath{\neq}",
    "\u2248": r"\ensuremath{\approx}",
    "\u221e": r"\ensuremath{\infty}",
    "\u2192": r"\ensuremath{\rightarrow}",
    "\u2190": r"\ensuremath{\leftarrow}",
    "\u2194": r"\ensuremath{\leftrightarrow}",
    "\u21d2": r"\ensuremath{\Rightarrow}",
    "\u2208": r"\ensuremath{\in}",
    "\u2211": r"\ensuremath{\sum}",
    "\u221a": r"\ensuremath{\surd}",
    "\u2202": r"\ensuremath{\partial}",
    "\u2207": r"\ensuremath{\nabla}",
    "\u223c": r"\ensuremath{\sim}",
    "\u2032": r"\ensuremath{'}",
    "\u00b0": r"\ensuremath{^\circ}",
    "\u2009": r"\,",
    "\u202f": r"\,",
    "\u00a0": "~",
    "\u2013": "--",
    "\u2014": "---",
    "\u2018": "`",
    "\u2019": "'",
    "\u201c": "``",
    "\u201d": "''",
    "\u2026": r"\ldots{}",
    "\u2022": r"\textbullet{}",
    "\u2020": r"\textdagger{}",
    "\u2021": r"\textdaggerdbl{}",
    "\u00a7": r"\S{}",
    "\u00b6": r"\P{}",
    "\u00a9": r"\textcopyright{}",
    "\u00ae": r"\textregistered{}",
    "\u2122": r"\texttrademark{}",
    "\u00b2": r"\ensuremath{^2}",
    "\u00b3": r"\ensuremath{^3}",
    "\u00b9": r"\ensuremath{^1}",
    "\u2070": r"\ensuremath{^0}",
    "\u2074": r"\ensuremath{^4}",
    "\u207b": r"\ensuremath{^-}",
    "\u2080": r"\ensuremath{_0}",
    "\u2081": r"\ensuremath{_1}",
    "\u2082": r"\ensuremath{_2}",
    "\u00b5": r"\ensuremath{\mu}",
    "\u212b": r"\AA{}",
}
_GREEK = {
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
    "δ": "delta",
    "ε": "epsilon",
    "ζ": "zeta",
    "η": "eta",
    "θ": "theta",
    "ι": "iota",
    "κ": "kappa",
    "λ": "lambda",
    "μ": "mu",
    "ν": "nu",
    "ξ": "xi",
    "π": "pi",
    "ρ": "rho",
    "σ": "sigma",
    "τ": "tau",
    "υ": "upsilon",
    "φ": "phi",
    "χ": "chi",
    "ψ": "psi",
    "ω": "omega",
    "Γ": "Gamma",
    "Δ": "Delta",
    "Θ": "Theta",
    "Λ": "Lambda",
    "Ξ": "Xi",
    "Π": "Pi",
    "Σ": "Sigma",
    "Φ": "Phi",
    "Ψ": "Psi",
    "Ω": "Omega",
}
for _ch, _name in _GREEK.items():
    _UNICODE[_ch] = rf"\ensuremath{{\{_name}}}"


def _latin1_ok(ch: str) -> bool:
    # T1-encoded Latin letters (é, ü, ø, ...) typeset with utf8 inputenc.
    return ord(ch) < 0x250 and unicodedata.category(ch)[0] == "L"


def unicode_to_latex(text: str) -> str:
    out = []
    for ch in text:
        if ord(ch) < 128 or _latin1_ok(ch):
            out.append(ch)
        elif ch in _UNICODE:
            out.append(_UNICODE[ch])
        else:
            decomposed = (
                unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode()
            )
            out.append(decomposed if decomposed else "?")
    return "".join(out)


def normalise_citations(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        keys = ",".join(k.strip() for k in m.group(1).split(",") if k.strip())
        return f"\\cite{{{keys}}}" if keys else ""

    return _CITE_RE.sub(repl, text)


def strip_citations(text: str) -> str:
    """Remove citations (for abstracts and panels where the journal forbids them)."""
    text = re.sub(r"\s*\\cite\{[^}]*\}", "", normalise_citations(text))
    return re.sub(r"\s+([.,;:])", r"\1", text)


# Segments left untouched when escaping text-mode specials: maths, tables/arrays (where
# & is a column separator), and arguments that are keys or URLs.
_PROTECTED_RE = re.compile(
    r"(\$\$.*?\$\$|\$(?:\\.|[^$\\])*\$|\\\(.*?\\\)|\\\[.*?\\\]"
    r"|\\begin\{(equation|align|gather|multline|eqnarray|math|displaymath|tabular|tabularx|array)\*?\}.*?\\end\{\2\*?\}"
    r"|\\(?:cite|ref|eqref|label|url|href)\{[^}]*\})",
    re.DOTALL,
)


def escape_text_specials(text: str) -> str:
    """Escape ``_``, ``#`` and ``&`` that appear in running text (``mean_y``), where TeX
    would otherwise stop with "Missing $ inserted"."""
    parts = _PROTECTED_RE.split(text)
    out = []
    i = 0
    while i < len(parts):
        out.append(re.sub(r"(?<!\\)([_#&])", r"\\\1", parts[i]))
        if i + 1 < len(parts):
            out.append(parts[i + 1])  # the protected segment
        i += 3  # split() also returns the inner environment-name group
    return "".join(out)


def sanitize(text: str) -> str:
    """Body text safe to compile: no file/shell access, no redefinitions, portable chars."""
    text = text.replace("\r\n", "\n").replace("\x00", "")
    text = _FORBIDDEN_ENV_RE.sub("", text)
    text = normalise_citations(text)
    # Drop a forbidden command together with an immediately following argument group.
    text = re.sub(
        _FORBIDDEN_RE.pattern + r"\s*(?:\[[^\]]*\])?(?:\{[^{}]*\})?", "", text
    )
    # Escape stray % that would comment out the rest of a line (unescaped percent signs
    # in model text are almost always literal percentages).
    text = re.sub(r"(?<!\\)%", r"\\%", text)
    text = escape_text_specials(text)
    text = unicode_to_latex(text)
    # Section commands inside a section body would break the journal's structure.
    text = re.sub(r"\\(chapter|part)\*?\{", r"\\subsection*{", text)
    text = re.sub(r"\\section\*?\{", r"\\subsection*{", text)
    return text.strip()


def plain_text(tex: str) -> str:
    """Approximate reading text of a LaTeX fragment (for word counts and checks)."""
    t = re.sub(r"\\cite\{[^}]*\}", "", tex)
    t = re.sub(r"\$[^$]*\$", " x ", t)
    t = re.sub(
        r"\\begin\{(table|figure)\*?\}.*?\\end\{\1\*?\}", " ", t, flags=re.DOTALL
    )
    t = re.sub(
        r"\\(textbf|textit|emph|texttt|textsc|underline|mbox|text)\{([^}]*)\}", r"\2", t
    )
    t = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", t)
    t = re.sub(r"[{}~\\]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def word_count(tex: str) -> int:
    return len([w for w in plain_text(tex).split(" ") if re.search(r"[A-Za-z0-9]", w)])


def move_citations_after_punctuation(text: str) -> str:
    """'... shown \\cite{a}.' -> '... shown.\\cite{a}' (Lancet, NEJM, AMA style)."""
    return re.sub(r"\s*(\\cite\{[^}]*\})([.,;:])", r"\2\1", text)


def tighten_superscript_citations(text: str) -> str:
    """No space before a superscript citation: 'shown \\cite{a}' -> 'shown\\cite{a}'."""
    return re.sub(r"[ \t]+(\\cite\{)", r"\1", text)


_DECIMAL_RE = re.compile(r"(?<=\d)\.(?=\d)")


def lancet_decimals(text: str) -> str:
    """The Lancet prints decimal points mid-line (0·5). Applied to running text only:
    maths, citation keys and commands are left untouched."""
    parts = re.split(r"(\$[^$]*\$|\\cite\{[^}]*\}|\\[A-Za-z]+(?:\{[^}]*\})?)", text)
    return "".join(
        p if i % 2 else _DECIMAL_RE.sub(r"\\textperiodcentered{}", p)
        for i, p in enumerate(parts)
    )
