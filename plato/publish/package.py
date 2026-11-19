"""Build a journal-ready publication package for a completed campaign.

One call produces a deterministic zip:

    <name>/
      README.md                   what is in the package and how to submit it
      SUBMISSION_CHECKLIST.md     the journal's limits against this paper, and every
                                  placeholder the authors must fill
      manuscript/                 manuscript.pdf, .tex, .docx, .jats.xml (PubMed Central),
                                  references.bib, references.json (CSL-JSON), figures/
      supplement/                 supplementary_information.pdf and .tex
      data/                       CSV tables, data_S1.xlsx, metrics.json, input datasets
      code/  logs/  review/       each experiment's code and log, automated reviews
      arxiv/                      (arXiv only) upload-ready source with anc/
      PROVENANCE.json  CITATION.cff  MANIFEST.json (SHA-256 of every file)

The body text is the campaign's own manuscript; only journal front matter is written
by the model (``adapt``). TeX and pandoc run sandboxed (``tools.run_tool``).
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plato.scientist.db.migrate import advisory_key
from plato.scientist.db.store import DualGraphStore

from . import convert
from .adapt import (
    JournalAdaptation,
    adapt,
    fallback,
    normalise,
    unsupported_numbers,
)
from .collect import Materials, collect
from .document import (
    Doc,
    Figure,
    Table,
    latex_pandoc,
    latex_pdf,
    statements,
    supplement_latex,
)
from .enrich import enrich
from .figures import SUMMARY_FILE, experiment_plots, summary_chart, summary_rows
from .journals import AI_NOTE, Journal, get
from .references import (
    bibtex,
    cited_keys_in_order,
    csl_items,
    render_bibliography,
    thebibliography,
)
from .supplement import FIXED_TIME, dumps, provenance, safe_name, write_data
from .texsafe import normalise_citations, plain_text, sanitize, word_count
from .tools import ToolError, hand_to_sandbox_user, run_tool

logger = logging.getLogger(__name__)

DEFAULT_DISPLAY_ITEMS = 6
MAX_PACKAGE_BYTES = 100 * 1024 * 1024
_ZIP_TIME = FIXED_TIME.timetuple()[:6]
_PLACEHOLDER_RE = re.compile(r"\[(?:[A-Z][^\[\]]{2,240})\]")


@dataclass
class Check:
    id: str
    label: str
    status: str  # pass | warn | fail | info
    detail: str = ""


@dataclass
class Package:
    journal: str
    name: str
    zip_bytes: bytes
    sha256: str
    files: list[dict[str, Any]]
    checks: list[Check]
    adaptation_source: str
    pdf_ok: bool
    pages: int | None
    counts: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "journal": self.journal,
            "name": self.name,
            "bytes": len(self.zip_bytes),
            "sha256": self.sha256,
            "files": self.files,
            "checks": [c.__dict__ for c in self.checks],
            "adaptation_source": self.adaptation_source,
            "pdf_ok": self.pdf_ok,
            "pages": self.pages,
            "counts": self.counts,
        }


# ----------------------------------------------------------------------------- adaptation
async def _cached_adaptation(
    pool, campaign_id: uuid.UUID, journal: str
) -> JournalAdaptation | None:
    row = await pool.fetchrow(
        "SELECT adaptation FROM plato.publication_adaptations WHERE campaign_id = $1 AND journal = $2",
        campaign_id,
        journal,
    )
    if row is None:
        return None
    data = row["adaptation"]
    return JournalAdaptation.model_validate(
        json.loads(data) if isinstance(data, str) else data
    )


async def front_matter(
    store: DualGraphStore,
    model,
    m: Materials,
    j: Journal,
    figure_notes: list[str],
    cap: int | None,
) -> tuple[JournalAdaptation, str]:
    """The journal's front matter: cached per campaign and journal, written once by the
    model under a lock so concurrent exports never pay twice."""
    pool, cid = store.pool, m.campaign["id"]
    cached = await _cached_adaptation(pool, cid, j.key)
    if cached is not None:
        return normalise(cached, m, j, len(figure_notes)), "model (cached)"
    key = advisory_key(b"plato.publication:" + cid.bytes + j.key.encode())
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_lock($1)", key)
        try:
            cached = await _cached_adaptation(conn, cid, j.key)
            if cached is not None:
                return normalise(cached, m, j, len(figure_notes)), "model (cached)"
            a, source = await adapt(model, pool, m, j, figure_notes, cap=cap)
            if source == "model":
                await conn.execute(
                    """
                    INSERT INTO plato.publication_adaptations(campaign_id, journal, adaptation, model)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (campaign_id, journal) DO NOTHING
                    """,
                    cid,
                    j.key,
                    a.model_dump(mode="json"),
                    getattr(model, "model", None),
                )
            return a, source
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", key)


# ----------------------------------------------------------------------------- figures
@dataclass
class FigurePlan:
    main: list[Figure]
    supplementary: list[Figure]
    table: Table | None
    notes: list[str]  # one line per main figure, given to the model for titles
    files: dict[str, bytes]  # manuscript/figures/<name> -> bytes


def _finding_table(m: Materials) -> Table | None:
    rows = []
    for f in m.by_status("finding", "verified"):
        metrics = f.get("metrics") or {}
        key = metrics.get("primary_metric")
        value = metrics.get(key) if isinstance(key, str) else None
        shown = (
            f"{value:.6g}"
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else "--"
        )
        conf = (
            f"{float(f['confidence_score']):.2f}"
            if f["confidence_score"] is not None
            else "--"
        )
        rows.append([f["title"], key or "--", shown, conf])
    if not rows:
        return None
    return Table(
        caption="Verified findings: primary metric as measured by the experiment code, and skeptic confidence.",
        header=["Finding", "Primary metric", "Value", "Confidence"],
        rows=rows,
        notes="Values are copied from the experiments' machine-readable output (data/findings.csv).",
    )


def _all_findings_table(m: Materials) -> Table | None:
    rows = []
    for f in (n for n in m.nodes if n["node_type"] == "finding"):
        metrics = f.get("metrics") or {}
        key = metrics.get("primary_metric")
        value = metrics.get(key) if isinstance(key, str) else None
        shown = (
            f"{value:.6g}"
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else "--"
        )
        conf = (
            f"{float(f['confidence_score']):.2f}"
            if f["confidence_score"] is not None
            else "--"
        )
        rows.append([f["title"], f["status"], key or "--", shown, conf])
    if not rows:
        return None
    return Table(
        caption="All findings with their verification status.",
        header=["Finding", "Status", "Primary metric", "Value", "Confidence"],
        rows=rows,
    )


def plan_figures(m: Materials, j: Journal, workdir: Path) -> FigurePlan:
    table = _finding_table(m)
    limit = j.display_items_max or DEFAULT_DISPLAY_ITEMS
    room = max(limit - (1 if table else 0), 1)
    files: dict[str, bytes] = {}
    candidates: list[tuple[Figure, str]] = []
    chart_dir = workdir / "chart"
    if summary_chart(summary_rows(m), chart_dir):
        files[f"{SUMMARY_FILE}.pdf"] = (chart_dir / f"{SUMMARY_FILE}.pdf").read_bytes()
        files[f"{SUMMARY_FILE}.png"] = (chart_dir / f"{SUMMARY_FILE}.png").read_bytes()
        candidates.append(
            (
                Figure(
                    f"figures/{SUMMARY_FILE}.pdf",
                    "Summary of findings",
                    "Bars give the skeptic agent's confidence in each finding; colour gives its "
                    "verification status; the label gives the primary metric measured by the "
                    "experiment code. Source data: data/figure_summary.csv.",
                ),
                "Bar chart of skeptic confidence per finding, coloured by verification status.",
            )
        )
    for i, p in enumerate(experiment_plots(m), 1):
        name = f"plot{i:02d}.png"
        files[name] = p.png
        candidates.append(
            (
                Figure(
                    f"figures/{name}",
                    p.finding_title or f"Experiment result {i}",
                    f"Plot written by the experiment code behind \u201c{p.finding_title}\u201d "
                    f"(experiment {str(p.node_id)[:8]}). Code and log: code/ and logs/; "
                    "metrics: data/metrics.json.",
                    str(p.node_id),
                ),
                f"Experiment plot for: {p.finding_title}",
            )
        )
    main = [f for f, _ in candidates[:room]]
    notes = [n for _, n in candidates[:room]]
    supplementary = [f for f, _ in candidates[room:]]
    return FigurePlan(main, supplementary, table, notes, files)


# ----------------------------------------------------------------------------- compile
async def _pdflatex(tex: str, name: str, workdir: Path) -> tuple[bool, str, int | None]:
    (workdir / f"{name}.tex").write_text(tex, encoding="utf-8")
    hand_to_sandbox_user(workdir)
    log = ""
    argv = [
        "pdflatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-no-shell-escape",
        f"{name}.tex",
    ]
    for _ in range(2):  # second run resolves references and figure numbers
        try:
            res = await run_tool(argv, workdir, check=False)
        except ToolError as exc:
            return False, str(exc), None
        log = res.output
        if res.code != 0:
            return False, log[-3000:], None
    m = re.search(r"Output written on .*?\((\d+) pages?", log)
    return (workdir / f"{name}.pdf").exists(), "", int(m.group(1)) if m else None


async def _pandoc_normalise(text: str, workdir: Path) -> str:
    """Rewrite a LaTeX fragment through pandoc's reader and writer: drops anything the
    reader does not understand, keeps citations (as natbib) and maths."""
    if not text.strip():
        return text
    res = await run_tool(
        ["pandoc", "-f", "latex", "-t", "latex", "--natbib", "--wrap=none"],
        workdir,
        stdin=text.encode("utf-8"),
        check=False,
    )
    return (
        sanitize(normalise_citations(res.output))
        if res.code == 0
        else sanitize(plain_text(text))
    )


@dataclass
class Compiled:
    tex: str
    items: list[dict[str, Any]]
    bibliography: str
    scrub: Any  # Callable[[str], str]: drops citation keys the graph does not hold
    pdf_ok: bool
    error: str
    pages: int | None
    pdf_dir: Path


async def _compile_manuscript(
    store,
    m: Materials,
    j: Journal,
    doc: Doc,
    build: Path,
    ms_dir: Path,
    work: Path,
    crossref: bool,
) -> Compiled:
    """References in the journal's CSL style, then pdfLaTeX (with a pandoc-normalised
    retry when the model's LaTeX does not compile). ``ms_dir`` holds the figures."""
    # Cited keys in order of first appearance across everything that is printed.
    probe = latex_pdf(doc, "")
    sup_methods = j.methods_in_supplement
    keys = cited_keys_in_order(
        probe, doc.sections.get("methods", "") if sup_methods else ""
    )
    drop = {k for k in keys if k not in m.papers}
    keys = [k for k in keys if k not in drop]

    def scrub(t: str) -> str:
        """Remove citation keys the graph does not hold (never print "?")."""
        if not drop:
            return t

        def repl(mm: re.Match[str]) -> str:
            ok = [
                k.strip()
                for k in mm.group(1).split(",")
                if k.strip() and k.strip() not in drop
            ]
            return "\\cite{" + ",".join(ok) + "}" if ok else ""

        return re.sub(r"\\cite\{([^}]*)\}", repl, t)

    if crossref and keys:
        try:
            await enrich(store.pool, m.papers, keys)
        except Exception:  # never block an export on Crossref
            logger.warning("crossref enrichment failed", exc_info=True)
    items = csl_items(keys, m.papers)
    (build / "refs.json").write_text(
        json.dumps(items, ensure_ascii=False), encoding="utf-8"
    )
    convert.style_file(j, build)
    bib_entries = await render_bibliography(items, j.csl, build)
    bibliography = thebibliography(bib_entries)

    # ---- manuscript PDF (with a normalised retry if the model's LaTeX does not compile)
    tex = scrub(latex_pdf(doc, bibliography))
    pdf_dir = work / "pdf"
    shutil.copytree(ms_dir, pdf_dir)
    pdf_ok, err, pages = await _pdflatex(tex, "manuscript", pdf_dir)
    if not pdf_ok:
        logger.warning(
            "manuscript did not compile, retrying normalised: %s", err[-500:]
        )
        doc.sections = {
            k: await _pandoc_normalise(v, build) for k, v in doc.sections.items()
        }
        tex = scrub(latex_pdf(doc, bibliography))
        shutil.rmtree(pdf_dir)
        shutil.copytree(ms_dir, pdf_dir)
        pdf_ok, err, pages = await _pdflatex(tex, "manuscript", pdf_dir)
    return Compiled(tex, items, bibliography, scrub, pdf_ok, err, pages, pdf_dir)


# ----------------------------------------------------------------------------- checks
def _words(text: str) -> int:
    return word_count(text)


def checks_for(
    doc: Doc, j: Journal, m: Materials, n_refs: int, pdf_ok: bool, numbers: list[str]
) -> list[Check]:
    a = doc.adaptation
    out: list[Check] = []

    def limit(cid: str, label: str, value: int, maximum: int | None, unit: str) -> None:
        if maximum is None:
            out.append(
                Check(cid, label, "info", f"{value} {unit}; the journal sets no limit")
            )
        else:
            ok = value <= maximum
            out.append(
                Check(
                    cid,
                    label,
                    "pass" if ok else "warn",
                    f"{value} of at most {maximum} {unit}",
                )
            )

    if j.title_max_chars:
        limit(
            "title_chars",
            "Title length",
            len(plain_text(a.title)),
            j.title_max_chars,
            "characters",
        )
    if j.title_max_words:
        limit(
            "title_words", "Title length", _words(a.title), j.title_max_words, "words"
        )
    abstract_words = sum(_words(s.text) for s in a.abstract)
    limit(
        "abstract_words",
        f"{j.abstract.label} length",
        abstract_words,
        j.abstract.max_words,
        "words",
    )
    if j.abstract.headings:
        have = {s.heading: s.text.strip() for s in a.abstract}
        missing = [h for h in j.abstract.headings if not have.get(h)]
        out.append(
            Check(
                "abstract_structure",
                "Structured abstract headings",
                "pass" if not missing else "fail",
                "all present: " + "; ".join(j.abstract.headings)
                if not missing
                else "missing or empty: " + "; ".join(missing),
            )
        )
    main_words = sum(
        _words(doc.sections.get(k, ""))
        for k in ("introduction", "results", "discussion", "limitations")
    )
    limit("main_words", "Main text length", main_words, j.main_text_max_words, "words")
    if j.methods_max_words:
        limit(
            "methods_words",
            "Methods length",
            _words(doc.sections.get("methods", "")),
            j.methods_max_words,
            "words",
        )
    limit("references", "References", n_refs, j.references_max, "references")
    display = len(doc.figures) + (1 if doc.table else 0)
    limit(
        "display_items",
        "Display items (figures and tables)",
        display,
        j.display_items_max,
        "items",
    )
    if j.legend_max_words:
        longest = max(
            (_words(f.legend) + _words(f.title) for f in doc.figures), default=0
        )
        limit(
            "legend_words",
            "Longest figure legend",
            longest,
            j.legend_max_words,
            "words",
        )
    if j.highlights:
        long_ = [h for h in a.highlights if len(plain_text(h)) > 85]
        n = len(a.highlights)
        out.append(
            Check(
                "highlights",
                "Highlights",
                "pass" if 3 <= n <= 4 and not long_ else "warn",
                f"{n} highlights"
                + (f"; {len(long_)} longer than 85 characters" if long_ else ""),
            )
        )
    if j.key_points:
        kp = a.key_points
        words = sum(
            _words(t) for t in ([kp.question, kp.findings, kp.meaning] if kp else [])
        )
        out.append(
            Check(
                "key_points",
                "Key Points",
                "pass" if kp and words <= 100 else "warn",
                f"{words} of at most 100 words",
            )
        )
    if j.research_in_context:
        out.append(
            Check(
                "research_in_context",
                "Research in context panel",
                "pass" if a.research_in_context else "warn",
                "present"
                if a.research_in_context
                else "missing: write it before submitting",
            )
        )
    if j.keywords:
        lo, hi = j.keywords
        out.append(
            Check(
                "keywords",
                "Keywords",
                "pass" if lo <= len(a.keywords) <= hi else "warn",
                f"{len(a.keywords)} (needs {lo} to {hi})",
            )
        )
    out.append(
        Check(
            "numbers",
            "Numbers in the front matter",
            "pass" if not numbers else "warn",
            "every number appears in the manuscript or the measured metrics"
            if not numbers
            else "not found in the manuscript or metrics, check before submitting: "
            + ", ".join(numbers[:12]),
        )
    )
    out.append(
        Check(
            "pdf",
            "Manuscript PDF compiles",
            "pass" if pdf_ok else "fail",
            "pdfLaTeX" if pdf_ok else "see the .tex and the build log",
        )
    )
    verified = len(m.by_status("finding", "verified"))
    out.append(
        Check(
            "verified_findings",
            "Verified findings",
            "pass" if verified else "warn",
            f"{verified} finding(s) passed verification"
            if verified
            else "no finding passed verification; the paper reports negative or preliminary results",
        )
    )
    out.append(
        Check(
            "authors",
            "Authors and affiliations",
            "fail",
            "placeholders: add the human authors who take responsibility for the work",
        )
    )
    out.append(Check("ai_disclosure", "AI disclosure", "info", AI_NOTE))
    if j.template_note:
        out.append(Check("template", "Journal template", "info", j.template_note))
    return out


def checklist_md(j: Journal, checks: list[Check], placeholders: list[str]) -> str:
    icon = {"pass": "[x]", "warn": "[ ] (check)", "fail": "[ ] (required)", "info": "-"}
    lines = [
        f"# Submission checklist: {j.name} ({j.article_type})",
        "",
        f"Rules read from {j.source} on {j.verified}.",
        "",
        "## Journal requirements",
        "",
    ]
    for c in checks:
        lines.append(f"- {icon[c.status]} **{c.label}**: {c.detail}")
    lines += ["", "## Placeholders to complete", ""]
    lines += [f"- [ ] {p}" for p in placeholders] or ["- none"]
    if j.notes:
        lines += ["", "## Journal notes", ""] + [f"- {n}" for n in j.notes]
    return "\n".join(lines) + "\n"


def readme_md(j: Journal, title: str, formats: list[str], has_arxiv: bool) -> str:
    lines = [
        f"# {title}",
        "",
        f"Publication package for **{j.name}** ({j.article_type}), generated by Plato.",
        "",
        "## Contents",
        "",
        "| Path | What it is |",
        "| --- | --- |",
        "| `manuscript/manuscript.pdf` | The manuscript, formatted to the journal's rules |",
        "| `manuscript/manuscript.tex` | Its single-file LaTeX source (bibliography inlined) |",
        "| `manuscript/manuscript.docx` | Word version with the journal's reference style |",
        "| `manuscript/manuscript.jats.xml` | JATS XML, the format PubMed Central ingests |",
        "| `manuscript/references.bib`, `references.json` | References as BibTeX and CSL-JSON |",
        "| `manuscript/figures/` | Figures (vector PDF and 300 dpi PNG) |",
        "| `supplement/supplementary_information.pdf` | Supplementary Information |",
        "| `data/` | Source data as CSV and one Excel workbook (`data_S1.xlsx`), metrics, input datasets |",
        "| `code/`, `logs/` | Each experiment's code and execution log |",
        "| `review/` | Automated peer review and figure critiques |",
        "| `PROVENANCE.json` | How every finding was reached |",
        "| `MANIFEST.json` | SHA-256 checksum of every file |",
    ]
    if has_arxiv:
        lines.append(
            "| `arxiv/` | Upload-ready arXiv source: `main.tex`, figures, `anc/` ancillary files |"
        )
    lines += [
        "",
        f"The journal asks for: {', '.join(formats)} at first submission.",
        "",
        "## Before you submit",
        "",
        "1. Read `SUBMISSION_CHECKLIST.md` and fix every unchecked item.",
        "2. Replace every bracketed placeholder (authors, affiliations, statements).",
        "3. Check every claim, number and reference yourself.",
        "",
        AI_NOTE,
        "",
    ]
    return "\n".join(lines)


def citation_cff(title: str, campaign_id: uuid.UUID) -> str:
    t = title.replace('"', "'")
    return (
        "cff-version: 1.2.0\n"
        'message: "If you use this data or code, please cite it as below."\n'
        f'title: "{t}"\n'
        "type: dataset\n"
        "authors:\n"
        '  - name: "[Author names]"\n'
        f'identifiers:\n  - type: other\n    value: "plato-campaign-{campaign_id}"\n'
        "    description: Plato campaign identifier\n"
    )


def _zip(root: Path, top: str) -> tuple[bytes, list[dict[str, Any]]]:
    buf = io.BytesIO()
    files = []
    paths = sorted(p for p in root.rglob("*") if p.is_file())
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in paths:
            rel = p.relative_to(root).as_posix()
            data = p.read_bytes()
            info = zipfile.ZipInfo(f"{top}/{rel}", date_time=_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
            files.append({"path": rel, "bytes": len(data)})
    return buf.getvalue(), files


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60].rstrip("-") or "paper"


# ----------------------------------------------------------------------------- build
async def build_package(
    store: DualGraphStore,
    model,
    campaign_id: uuid.UUID,
    journal_key: str,
    *,
    cap: int | None = None,
    model_name: str = "",
    crossref: bool = True,
) -> Package:
    j = get(journal_key)
    m = await collect(store, campaign_id)
    model_name = model_name or getattr(model, "model", "") or "a large language model"
    work = Path(tempfile.mkdtemp(prefix="plato-export-"))
    try:
        return await _build(store, model, m, j, cap, model_name, crossref, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


async def _build(
    store,
    model,
    m: Materials,
    j: Journal,
    cap,
    model_name: str,
    crossref: bool,
    work: Path,
) -> Package:
    root = work / "pkg"
    ms_dir = root / "manuscript"
    fig_dir = ms_dir / "figures"
    fig_dir.mkdir(parents=True)
    build = work / "build"
    build.mkdir()

    plan = plan_figures(m, j, work)
    for name, data in plan.files.items():
        (fig_dir / name).write_bytes(data)

    adaptation, source = await front_matter(store, model, m, j, plan.notes, cap)
    for f, t in zip(plan.main, adaptation.figure_titles):
        if t.strip():
            f.title = t.strip().rstrip(".")

    sections = {k: sanitize(v) for k, v in m.sections.items() if k != "abstract"}
    supplement_items = [
        "Supplementary Information (supplementary_information.pdf)",
        "Data S1 (data_S1.xlsx)",
    ]
    doc = Doc(
        j,
        m.title,
        adaptation,
        sections,
        plan.main,
        plan.table,
        model_name,
        supplement_items,
    )

    compiled = await _compile_manuscript(
        store, m, j, doc, build, ms_dir, work, crossref
    )
    tex, items, bibliography, scrub = (
        compiled.tex,
        compiled.items,
        compiled.bibliography,
        compiled.scrub,
    )
    pdf_ok, err, pages, pdf_dir = (
        compiled.pdf_ok,
        compiled.error,
        compiled.pages,
        compiled.pdf_dir,
    )
    sup_methods = j.methods_in_supplement
    (ms_dir / "manuscript.tex").write_text(tex, encoding="utf-8")
    if pdf_ok:
        shutil.copy(pdf_dir / "manuscript.pdf", ms_dir / "manuscript.pdf")
    else:
        (ms_dir / "BUILD_LOG.txt").write_text(err, encoding="utf-8")

    # ---- Word and JATS from the same content, references by the journal's CSL style
    for name in plan.files:
        shutil.copy(fig_dir / name, build / name)
    (build / "figures").mkdir(exist_ok=True)
    for name in plan.files:
        shutil.copy(fig_dir / name, build / "figures" / name)
    hand_to_sandbox_user(build)
    word_ok = jats_ok = True
    try:
        ast = await convert.to_ast(scrub(latex_pandoc(doc)), build)
        try:
            shutil.copy(await convert.docx(ast, j, build), ms_dir / "manuscript.docx")
        except ToolError as exc:
            word_ok = False
            logger.warning("docx conversion failed: %s %s", exc, exc.output[-500:])
        try:
            shutil.copy(await convert.jats(ast, build), ms_dir / "manuscript.jats.xml")
        except ToolError as exc:
            jats_ok = False
            logger.warning("jats conversion failed: %s %s", exc, exc.output[-500:])
    except ToolError as exc:
        word_ok = jats_ok = False
        logger.warning(
            "pandoc could not read the manuscript: %s %s", exc, exc.output[-500:]
        )
    (ms_dir / "references.bib").write_text(bibtex(items), encoding="utf-8")
    (ms_dir / "references.json").write_text(
        json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # ---- Supplementary Information
    sup_dir = root / "supplement"
    sup_dir.mkdir()
    sup_tables = [t for t in (_all_findings_table(m),) if t]
    sup_figs = [
        Figure(f.file, f.title, f.legend, f.source_node) for f in plan.supplementary
    ]
    sup_tex = scrub(
        supplement_latex(
            doc, sup_figs, sup_tables, sup_methods, bibliography if sup_methods else ""
        )
    )
    sup_build = work / "sup"
    shutil.copytree(ms_dir / "figures", sup_build / "figures")
    sup_ok, sup_err, _ = await _pdflatex(
        sup_tex, "supplementary_information", sup_build
    )
    (sup_dir / "supplementary_information.tex").write_text(sup_tex, encoding="utf-8")
    if sup_ok:
        shutil.copy(
            sup_build / "supplementary_information.pdf",
            sup_dir / "supplementary_information.pdf",
        )
    else:
        logger.warning("supplement did not compile: %s", sup_err[-500:])
    if sup_figs:
        (sup_dir / "figures").mkdir()
        for f in sup_figs:
            shutil.copy(ms_dir / f.file, sup_dir / "figures" / Path(f.file).name)

    # ---- data, code, logs, provenance
    write_data(m, root)
    (root / "PROVENANCE.json").write_text(
        dumps(provenance(m, model_name)), encoding="utf-8"
    )
    (root / "CITATION.cff").write_text(
        citation_cff(m.title, m.campaign["id"]), encoding="utf-8"
    )

    # ---- arXiv source tree
    if j.key == "arxiv":
        ax = root / "arxiv"
        shutil.copytree(ms_dir / "figures", ax / "figures")
        (ax / "main.tex").write_text(tex, encoding="utf-8")
        anc = ax / "anc"
        for sub in ("data", "code"):
            if (root / sub).exists():
                shutil.copytree(root / sub, anc / sub)

    numbers = unsupported_numbers(adaptation, m)
    checks = checks_for(doc, j, m, len(items), pdf_ok, numbers)
    if not word_ok:
        checks.append(
            Check(
                "docx",
                "Word version",
                "fail",
                "pandoc could not convert the manuscript",
            )
        )
    if not jats_ok:
        checks.append(
            Check("jats", "JATS XML", "warn", "pandoc could not convert the manuscript")
        )
    if not sup_ok:
        checks.append(
            Check(
                "supplement",
                "Supplementary Information PDF",
                "warn",
                "did not compile; the .tex is included",
            )
        )
    if source.startswith("fallback"):
        checks.append(
            Check(
                "front_matter",
                "Journal front matter",
                "warn",
                source.removeprefix("fallback: "),
            )
        )
    placeholders = sorted(
        set(_PLACEHOLDER_RE.findall(tex))
        | {f"[{n}]" for n, t in statements(doc) if t.startswith("[")}
    )
    (root / "SUBMISSION_CHECKLIST.md").write_text(
        checklist_md(j, checks, placeholders), encoding="utf-8"
    )
    title = plain_text(adaptation.title) or m.title
    (root / "README.md").write_text(
        readme_md(j, title, list(j.manuscript_formats), j.key == "arxiv"),
        encoding="utf-8",
    )

    manifest = {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }
    (root / "MANIFEST.json").write_text(
        dumps({"algorithm": "sha256", "files": manifest}), encoding="utf-8"
    )

    name = f"{_slug(title)}-{j.key}"
    data, files = _zip(root, name)
    if len(data) > MAX_PACKAGE_BYTES:
        raise ValueError(
            f"the package is {len(data) / 1e6:.0f} MB, above the {MAX_PACKAGE_BYTES // 2**20} MiB limit"
        )
    counts = {
        "abstract_words": sum(word_count(s.text) for s in adaptation.abstract),
        "main_text_words": sum(
            word_count(doc.sections.get(k, ""))
            for k in ("introduction", "results", "discussion", "limitations")
        ),
        "references": len(items),
        "figures": len(doc.figures),
        "supplementary_figures": len(sup_figs),
        "tables": 1 if doc.table else 0,
    }
    return Package(
        journal=j.key,
        name=name,
        zip_bytes=data,
        sha256=hashlib.sha256(data).hexdigest(),
        files=files,
        checks=checks,
        adaptation_source=source,
        pdf_ok=pdf_ok,
        pages=pages,
        counts=counts,
    )


__all__ = ["Package", "build_package", "safe_name"]


# ----------------------------------------------------------------------------- preview
PREVIEW_JOURNAL = "arxiv"


class PreviewFailed(RuntimeError):
    """pdfLaTeX could not compile the manuscript; ``log`` is the tail of its output."""

    def __init__(self, log: str) -> None:
        super().__init__("the manuscript did not compile")
        self.log = log


async def preview_pdf(
    store: DualGraphStore, campaign_id: uuid.UUID, *, model_name: str = ""
) -> tuple[bytes, int | None]:
    """The paper typeset as a preprint (the arXiv profile): the campaign's own text,
    figures and references, compiled with pdfLaTeX. No model call: the arXiv front
    matter is reused when an export already wrote it, otherwise the deterministic
    fallback is used. No Crossref lookups, so it compiles in seconds."""
    j = get(PREVIEW_JOURNAL)
    m = await collect(store, campaign_id)
    work = Path(tempfile.mkdtemp(prefix="plato-preview-"))
    try:
        ms_dir = work / "manuscript"
        fig_dir = ms_dir / "figures"
        fig_dir.mkdir(parents=True)
        build = work / "build"
        build.mkdir()
        plan = plan_figures(m, j, work)
        for name, data in plan.files.items():
            (fig_dir / name).write_bytes(data)
        cached = await _cached_adaptation(store.pool, campaign_id, j.key)
        adaptation = (
            normalise(cached, m, j, len(plan.notes))
            if cached is not None
            else fallback(m, j, len(plan.notes))
        )
        for f, t in zip(plan.main, adaptation.figure_titles):
            if t.strip():
                f.title = t.strip().rstrip(".")
        sections = {k: sanitize(v) for k, v in m.sections.items() if k != "abstract"}
        doc = Doc(
            j,
            m.title,
            adaptation,
            sections,
            plan.main,
            plan.table,
            model_name or "a large language model",
            [
                "Supplementary Information (supplementary_information.pdf)",
                "Data S1 (data_S1.xlsx)",
            ],
        )
        out = await _compile_manuscript(
            store, m, j, doc, build, ms_dir, work, crossref=False
        )
        if not out.pdf_ok:
            raise PreviewFailed(out.error[-3000:])
        return (out.pdf_dir / "manuscript.pdf").read_bytes(), out.pages
    finally:
        shutil.rmtree(work, ignore_errors=True)
