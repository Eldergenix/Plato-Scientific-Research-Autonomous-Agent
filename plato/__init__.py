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

_LAZY_EXPORTS = {
    "Plato": (".plato", "Plato"),
    "Research": (".research", "Research"),
    "Journal": (".paper_agents.journal", "Journal"),
    "LLM": (".llm", "LLM"),
    "models": (".llm", "models"),
    "KeyManager": (".key_manager", "KeyManager"),
}


def __getattr__(name: str):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from importlib import import_module

    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value
