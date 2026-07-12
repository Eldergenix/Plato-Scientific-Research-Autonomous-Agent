#!/usr/bin/env python3
"""Generate the Plato-Bio LaTeX manuscript and supplement from canonical data."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PREPRINT = ROOT / "preprint"
LATEX = PREPRINT / "latex"
MANUSCRIPT = PREPRINT / "manuscript.md"

PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[letterpaper,margin=0.85in]{geometry}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{array}
\usepackage{xcolor}
\usepackage{hyperref}
\usepackage{lineno}
\usepackage{microtype}
\usepackage{caption}
\usepackage{enumitem}
\usepackage{float}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.65em}
\setlength{\emergencystretch}{2em}
\definecolor{PlatoBlue}{HTML}{1F4D78}
\hypersetup{colorlinks=true,linkcolor=PlatoBlue,urlcolor=PlatoBlue,citecolor=PlatoBlue}
\captionsetup{font=small,labelfont=bf}
\renewcommand{\arraystretch}{1.18}
\modulolinenumbers[5]
\graphicspath{{../figures/}}
"""

TABLE_CAPTIONS = (
    "Deterministic software-validation results. Targeted suites overlap with the full Python suite.",
    "AlphaFold-to-experiment structural agreement in the declared globin panel.",
)


def _escape_chars(text: str) -> str:
    mapping = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "α": r"$\alpha$",
        "β": r"$\beta$",
        "ρ": r"$\rho$",
        "≤": r"$\leq$",
        "Å": r"\AA{}",
        "×": r"$\times$",
        "−": r"$-$",
        "→": r"$\rightarrow$",
        "–": "--",
        "—": "---",
        "“": "``",
        "”": "''",
        "’": "'",
    }
    return "".join(mapping.get(char, char) for char in text)


SPECIAL_RE = re.compile(r"(10⁻⁵|\[\d+(?:,\d+)*\])")


def escape_plain(text: str) -> str:
    output: list[str] = []
    position = 0
    for match in SPECIAL_RE.finditer(text):
        output.append(_escape_chars(text[position : match.start()]))
        token = match.group(0)
        if token == "10⁻⁵":
            output.append(r"$10^{-5}$")
        else:
            keys = ",".join(f"ref{number}" for number in token[1:-1].split(","))
            output.append(r"~\cite{" + keys + "}")
        position = match.end()
    output.append(_escape_chars(text[position:]))
    return "".join(output)


TOKEN_RE = re.compile(r"(\*\*.+?\*\*|\*.+?\*|`.+?`|https?://[^\s)]+)")


def inline(text: str) -> str:
    parts: list[str] = []
    position = 0
    for match in TOKEN_RE.finditer(text):
        parts.append(escape_plain(text[position : match.start()]))
        token = match.group(0)
        if token.startswith("**"):
            parts.append(r"\textbf{" + inline(token[2:-2]) + "}")
        elif token.startswith("*"):
            parts.append(r"\emph{" + inline(token[1:-1]) + "}")
        elif token.startswith("`"):
            parts.append(r"\texttt{" + escape_plain(token[1:-1]) + "}")
        else:
            trailing = ""
            while token and token[-1] in ".,;":
                trailing = token[-1] + trailing
                token = token[:-1]
            parts.append(r"\url{" + token + "}" + escape_plain(trailing))
        position = match.end()
    parts.append(escape_plain(text[position:]))
    return "".join(parts)


def table_tex(rows: list[list[str]], table_number: int) -> str:
    columns = len(rows[0])
    alignment = "l" + "r" * (columns - 1)
    body = [r"\begin{table}[H]", r"\centering"]
    body.append(r"\caption{" + TABLE_CAPTIONS[table_number - 1] + "}")
    body.append(rf"\label{{tab:table-{table_number}}}")
    body.extend([r"\small", r"\resizebox{\textwidth}{!}{%", rf"\begin{{tabular}}{{{alignment}}}", r"\toprule"])
    for row_index, row in enumerate(rows):
        body.append(" & ".join(inline(cell) for cell in row) + r" \\")
        if row_index == 0:
            body.append(r"\midrule")
    body.extend([r"\bottomrule", r"\end{tabular}%", r"}", r"\end{table}"])
    return "\n".join(body)


def figure_tex(alt: str, relative_path: str) -> str:
    match = re.match(r"Figure\s+(\d+)\.\s*(.*)", alt)
    if not match:
        raise ValueError(f"Figure caption lacks a number: {alt}")
    number, caption = match.groups()
    label = f"fig:figure-{number}"
    path = "../" + relative_path
    return "\n".join(
        [
            r"\begin{figure}[H]",
            r"\centering",
            rf"\includegraphics[width=0.96\textwidth]{{{path}}}",
            r"\caption{" + inline(caption) + "}",
            rf"\label{{{label}}}",
            r"\end{figure}",
        ]
    )


def render_body(lines: list[str]) -> str:
    output: list[str] = []
    index = 0
    table_number = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("## "):
            output.append(r"\section{" + inline(stripped[3:]) + "}")
            index += 1
            continue
        if stripped.startswith("### "):
            output.append(r"\subsection{" + inline(stripped[4:]) + "}")
            index += 1
            continue
        if stripped == "<!-- PAGE BREAK -->":
            index += 1
            continue
        image = re.fullmatch(r"!\[(.+?)\]\((.+?)\)", stripped)
        if image:
            output.append(figure_tex(*image.groups()))
            index += 1
            continue
        if stripped.startswith("| "):
            raw_rows: list[list[str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                raw_rows.append(
                    [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                )
                index += 1
            rows = [raw_rows[0], *raw_rows[2:]]
            table_number += 1
            output.append(table_tex(rows, table_number))
            continue
        if re.match(r"^\d+\.\s+", stripped):
            output.append(r"\begin{enumerate}[leftmargin=*]")
            while index < len(lines):
                item = re.match(r"^\d+\.\s+(.*)", lines[index].strip())
                if not item:
                    break
                output.append(r"\item " + inline(item.group(1)))
                index += 1
            output.append(r"\end{enumerate}")
            continue
        if stripped.startswith("- "):
            output.append(r"\begin{itemize}[leftmargin=*]")
            while index < len(lines) and lines[index].strip().startswith("- "):
                output.append(r"\item " + inline(lines[index].strip()[2:]))
                index += 1
            output.append(r"\end{itemize}")
            continue

        paragraph = [stripped]
        index += 1
        while index < len(lines) and lines[index].strip():
            candidate = lines[index].strip()
            if (
                candidate.startswith("#")
                or candidate.startswith("|")
                or candidate.startswith("![")
                or candidate.startswith("- ")
                or candidate == "<!-- PAGE BREAK -->"
                or re.match(r"^\d+\.\s+", candidate)
            ):
                break
            paragraph.append(candidate)
            index += 1
        output.append(inline(" ".join(paragraph)))
    return "\n\n".join(output)


def build_main() -> Path:
    lines = MANUSCRIPT.read_text(encoding="utf-8").splitlines()
    title = lines[0].removeprefix("# ")
    abstract_start = lines.index("## Abstract") + 1
    introduction_start = lines.index("## Introduction")
    references_start = lines.index("## References")
    legends_start = lines.index("## Figure legends")

    abstract_lines = [line for line in lines[abstract_start:introduction_start] if line.strip()]
    body_lines = lines[introduction_start:references_start]
    reference_lines = [line for line in lines[references_start + 1 : legends_start] if line.strip()]
    legend_lines = lines[legends_start:]

    references = [r"\begin{thebibliography}{99}"]
    for reference in reference_lines:
        match = re.match(r"(\d+)\.\s+(.*)", reference)
        if match:
            number, citation = match.groups()
            references.append(rf"\bibitem{{ref{number}}} " + inline(citation))
    references.append(r"\end{thebibliography}")

    document = [PREAMBLE]
    document.extend(
        [
            r"\title{" + inline(title) + "}",
            r"\author{Stefan Creadore\\\small Eldergenix, United States}",
            r"\date{}",
            r"\begin{document}",
            r"\maketitle",
            r"\begin{center}\small Correspondence: \url{https://github.com/Eldergenix/Plato-Scientific-Research-Autonomous-Agent}\\Article category: New Results \quad Subject area: Bioinformatics\end{center}",
            r"\begin{abstract}",
            "\n\n".join(inline(line) for line in abstract_lines),
            r"\end{abstract}",
            r"\textbf{Keywords:} scientific agents; bioinformatics; reproducibility; citation validation; evidence provenance; AlphaFold; structural biology",
            r"\linenumbers",
            render_body(body_lines),
            "\n".join(references),
            render_body(legend_lines),
            r"\end{document}",
        ]
    )
    output = LATEX / "plato-bio.tex"
    output.write_text("\n\n".join(document) + "\n", encoding="utf-8")
    return output


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latex_table(rows: list[list[str]], alignment: str) -> str:
    body = [r"\resizebox{\textwidth}{!}{%", rf"\begin{{tabular}}{{{alignment}}}", r"\toprule"]
    for index, row in enumerate(rows):
        body.append(" & ".join(inline(value) for value in row) + r" \\")
        if index == 0:
            body.append(r"\midrule")
    body.extend([r"\bottomrule", r"\end{tabular}%", r"}"])
    return "\n".join(body)


def build_supplement() -> Path:
    results_dir = PREPRINT / "results" / "globin_benchmark"
    targets = list(csv.DictReader((results_dir / "target_summary.csv").open()))
    validation = json.loads((PREPRINT / "results" / "software_validation.json").read_text())
    raw_rows = [["File", "Bytes", "SHA-256"]]
    for path in sorted((results_dir / "raw").glob("*.pdb")):
        raw_rows.append([path.name, str(path.stat().st_size), sha256(path)])
    target_rows = [["Target", "Matched", "Identity", "RMSD (Å)", "Median (Å)", "Within 2 Å", "ρ", "P"]]
    for row in targets:
        target_rows.append(
            [
                row["target"],
                row["matched_residues"],
                f"{float(row['sequence_identity']):.3f}",
                f"{float(row['ca_rmsd_angstrom']):.3f}",
                f"{float(row['median_ca_error_angstrom']):.3f}",
                f"{float(row['fraction_within_2a']):.3f}",
                f"{float(row['spearman_plddt_vs_negative_error']):.3f}",
                f"{float(row['spearman_pvalue']):.3g}",
            ]
        )
    validation_rows = [["Suite", "Tests", "Passed", "Skipped", "Failures", "Errors", "Wall s"]]
    for name, suite in validation["suites"].items():
        passed = suite["tests"] - suite["skipped"] - suite["failures"] - suite["errors"]
        validation_rows.append(
            [name, str(suite["tests"]), str(passed), str(suite["skipped"]), str(suite["failures"]), str(suite["errors"]), f"{suite['wall_seconds']:.2f}"]
        )

    content = [PREAMBLE, r"\title{Supplementary Material: Plato-Bio}", r"\author{Stefan Creadore}", r"\date{}", r"\begin{document}", r"\maketitle", r"\section*{S1. Reproduction commands}", r"\begin{verbatim}", ".venv/bin/python preprint/experiments/run_globin_structure_benchmark.py\n.venv/bin/python preprint/experiments/run_software_validation.py\n.venv/bin/python preprint/experiments/build_summary_figures.py", r"\end{verbatim}", r"\section*{S2. Structural input inventory}", latex_table(raw_rows, "lrl"), r"\section*{S3. Target-level structural results}", latex_table(target_rows, "lrrrrrrr"), r"The residue-level CSV contains 433 matched positions.", r"\section*{S4. Deterministic validation results}", latex_table(validation_rows, "lrrrrrr"), r"Targeted suites overlap with the full Python suite. Counts are not additive. Skips remain unvalidated live or platform-specific paths.", r"\section*{S5. Measurement-repair acceptance criteria}", r"\begin{itemize}[leftmargin=*]", r"\item A biology GoldenTask constructs Plato with the biology domain.", r"\item Method-signal recall is computed from methods.md and included in summary metrics.", r"\item Evidence JSONL persists drafted Claim rows before EvidenceLink rows.", r"\item A claim with no supporting source remains in the denominator.", r"\item A synthetic rigid transformation is recovered by the Kabsch implementation within numerical tolerance.", r"\end{itemize}", r"\section*{S6. Interpretation boundary}", r"The default evaluator executes idea and method stages only. Live LLM, E2B, Modal, hosted PostgreSQL, and authenticated Hugging Face paths require external credentials or services. Same-model reviewer roles are self-critique, not peer review. The autonomous-loop adapters do not establish autonomous scientific improvement.", r"\section*{S7. bioRxiv packaging notes}", r"The main manuscript is supplied as one PDF with embedded figures and tables. Supplemental data are separate. No clinical, human-subject, animal, or identifiable-person data are included. Generative AI assistance is disclosed, and the human author remains accountable.", r"\end{document}"]
    output = LATEX / "plato-bio-supplement.tex"
    output.write_text("\n\n".join(content) + "\n", encoding="utf-8")
    return output


def main() -> int:
    LATEX.mkdir(parents=True, exist_ok=True)
    print(build_main())
    print(build_supplement())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
