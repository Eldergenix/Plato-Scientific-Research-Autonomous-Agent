"""Library materials given to a new research thread: reference files become citable papers,
documents become framed background the agents read, and a bad file never stops the thread."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest
from test_end_to_end import FakeModel, _new_campaign, fake_retriever

from plato.publish.journals import catalogue
from plato.publish.materials import Material, ingest, parse_nbib
from plato.scientist.graph import run_campaign
from plato.scientist.nodes import ScientistContext, user_materials

needs_pandoc = pytest.mark.skipif(
    not (shutil.which("pandoc") and shutil.which("pdftotext")),
    reason="pandoc and pdftotext are required",
)

BIB = b"""@article{smith2020,
  title = {Heteroskedasticity-consistent covariance estimators in small samples},
  author = {Smith, Jane and Doe, John},
  journal = {Journal of Econometrics},
  year = {2020},
  volume = {214},
  pages = {1--20},
  doi = {10.1016/j.jeconom.2019.01.001}
}
"""

RIS = b"""TY  - JOUR
TI  - The wild bootstrap for regression with unknown heteroskedasticity
AU  - Wu, C. F. J.
PY  - 1986
JO  - Annals of Statistics
DO  - 10.1214/aos/1176350142
ER  -
"""

NBIB = """PMID- 12345678
TI  - Robust standard errors in clinical regression models.
FAU - Garcia, Maria
FAU - Chen, Li
DP  - 2019 Mar
JT  - Statistics in Medicine
VI  - 38
PG  - 100-110
LID - 10.1002/sim.8000 [doi]
AB  - We compare HC0 to HC3.

PMID- 87654321
FAU - Nobody, A
DP  - 2001
"""

DOC = (
    b"# Lab notes\n\nOur previous study saw coverage of 0.91 with HC0. "
    b"QUOKKA-MARKER-7 should appear in the agents' context.\n"
)


def test_parse_nbib_reads_pubmed_records():
    items = parse_nbib(NBIB)
    assert len(items) == 1  # the record without a title is skipped
    it = items[0]
    assert it["title"] == "Robust standard errors in clinical regression models."
    assert it["author"][0] == {"family": "Garcia", "given": "Maria"}
    assert it["issued"] == {"date-parts": [[2019]]}
    assert it["DOI"] == "10.1002/sim.8000"
    assert it["PMID"] == "12345678"
    assert it["container-title"] == "Statistics in Medicine"


def test_journal_catalogue_matches_the_worker_copy():
    worker = Path(__file__).parents[2] / "cloudflare/plato-scientist/src/journals.json"
    assert json.loads(worker.read_text()) == catalogue(), (
        "regenerate src/journals.json from plato.publish.journals.catalogue()"
    )


@needs_pandoc
async def test_materials_reach_the_campaign_and_the_agents(store):
    program, cid, _, _ = await _new_campaign(store)
    out = await ingest(
        store,
        program,
        cid,
        [
            Material("refs.bib", BIB, "reference"),
            Material("refs.ris", RIS, "reference"),
            Material("pubmed.nbib", NBIB.encode(), "reference"),
            Material("notes.md", DOC, "document"),
            Material("broken.bib", b"\xff\xfe not bibtex {{{", "reference"),
            Material("empty.txt", b"   \n", "document"),
        ],
    )
    assert out["references"] == 3, out
    assert out["documents"] == 1, out
    assert any("empty.txt" in e for e in out["errors"]), out

    papers, docs = await user_materials(store, cid)
    titles = {p["metadata"]["title"] for p in papers}
    assert "The wild bootstrap for regression with unknown heteroskedasticity" in titles
    assert any(p["metadata"]["doi"] == "10.1016/j.jeconom.2019.01.001" for p in papers)
    assert all(p["metadata"]["user_supplied"] for p in papers)
    assert len(docs) == 1 and "QUOKKA-MARKER-7" in docs[0]["metadata"]["excerpt"]

    # Ingesting the same files again does not duplicate them.
    again = await ingest(store, program, cid, [Material("refs.bib", BIB, "reference")])
    assert again["references"] == 1
    assert len((await user_materials(store, cid))[0]) == 3

    model = FakeModel(store)
    summary = await run_campaign(
        ScientistContext(store=store, model=model, retriever=fake_retriever), cid
    )
    assert summary["campaign"]["status"] == "completed", summary["campaign"]
    prompts = "\n".join(model.prompts.values())
    # The document reaches the agents framed as untrusted data, and user papers are offered.
    assert "QUOKKA-MARKER-7" in prompts
    assert "untrusted" in prompts.lower()
    assert "wild bootstrap" in prompts.lower()


def test_worker_citation_styles_match_the_python_catalogue():
    from plato.publish.journals import styles_catalogue

    worker = (
        Path(__file__).resolve().parents[2]
        / "cloudflare/plato-scientist/src/citation_styles.json"
    )
    assert json.loads(worker.read_text()) == styles_catalogue(), (
        "regenerate src/citation_styles.json from plato.publish.journals.styles_catalogue()"
    )


@needs_pandoc
async def test_document_import_cannot_read_other_files(tmp_path):
    """An uploaded LaTeX file must not pull in files outside itself (pandoc --sandbox)."""
    from plato.publish.materials import extract_text

    # World-readable, like /etc/passwd: the tool's dropped privileges alone do not hide it.
    shared = Path(tempfile.mkdtemp(prefix="plato-shared-"))
    shared.chmod(0o755)
    secret = shared / "secret.tex"
    secret.write_text("SECRET-WALRUS-42\n")
    secret.chmod(0o644)
    work = tmp_path / "work"
    work.mkdir()
    tex = f"\\documentclass{{article}}\\begin{{document}}Visible text. \\input{{{secret}}}\\end{{document}}\n"
    m = Material(kind="document", file_name="notes.tex", content=tex.encode())
    text = await extract_text(m, work)
    try:
        assert "Visible text." in text
        assert "SECRET-WALRUS-42" not in text
    finally:
        shutil.rmtree(shared)
