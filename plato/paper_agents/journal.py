from typing import Callable
from pydantic import BaseModel
from enum import Enum

class Journal(str, Enum):
    """Enum which includes the different journals considered."""
    NONE = None
    """No journal, use standard latex presets with unsrt for bibliography style."""
    AAS  = "AAS"
    """American Astronomical Society journals, including the Astrophysical Journal."""
    APS = "APS"
    """Physical Review Journals from the American Physical Society, including Physical Review Letters, PRA, etc."""
    ICML = "ICML"
    """ICML - International Conference on Machine Learning."""
    JHEP = "JHEP"
    """Journal of High Energy Physics, including JHEP, JCAP, etc."""
    NeurIPS = "NeurIPS"
    """NeurIPS - Conference on Neural Information Processing Systems."""
    PASJ = "PASJ"
    """Publications of the Astronomical Society of Japan."""
    NATURE = "NATURE"
    """Nature journal (Springer Nature). Requires naturemag.cls from TeX Live publishers bundle (or article fallback)."""
    CELL = "CELL"
    """Cell journal (Cell Press). No standard CTAN class; falls back to article with double spacing + line numbers."""
    SCIENCE = "SCIENCE"
    """Science journal (AAAS). No standard CTAN class; falls back to article."""
    PLOS_BIO = "PLOS_BIO"
    """PLOS Biology (Public Library of Science). Requires plos2015.cls from TeX Live extras (or article fallback)."""
    ELIFE = "ELIFE"
    """eLife journal. Requires elife.cls (``tlmgr install elife``) — falls back to article."""

class LatexPresets(BaseModel):
    """Latex presets to be set depending on the journal"""
    article: str
    """Article preset or .cls file."""
    layout: str = ""
    """Layout, twocolumn or singlecolum layout."""
    title: str = r"\title"
    """Title setter of the article."""
    author: Callable[[str], str] = lambda x: f"\\author{{{x}}}"
    """Author command of the article."""
    bibliographystyle: str = ""
    """Bibliography style, indicated by a .bst file."""
    usepackage: str = ""
    """Extra packages, including those from .sty files."""
    affiliation: Callable[[str], str] = lambda x: rf"\affiliation{{{x}}}"
    """Command for affiliations."""
    abstract: Callable[[str], str]
    """Command for abstract. Include maketitle here if needed since some journals require before or after the abstract."""
    files: list[str] = []
    """Files to be included in the latex: .bst, .cls and .sty."""
    keywords: Callable[[str], str] = lambda x: ""
    """Keywords of the research."""
