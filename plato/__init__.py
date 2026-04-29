from .plato import Plato, Research, Journal, LLM, models, KeyManager
from .config import REPO_DIR
from .domain import DomainProfile, register_domain, get_domain, list_domains

__all__ = [
    'Plato', 'Research', 'Journal', 'REPO_DIR', 'LLM', 'models', 'KeyManager',
    'DomainProfile', 'register_domain', 'get_domain', 'list_domains',
]

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("plato")
except PackageNotFoundError:
    # fallback for editable installs, local runs, etc.
    __version__ = "0.0.0"
