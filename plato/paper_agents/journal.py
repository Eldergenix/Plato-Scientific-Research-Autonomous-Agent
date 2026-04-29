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
