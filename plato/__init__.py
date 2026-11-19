import warnings

warnings.filterwarnings(
    "ignore",
    message=r"The default value of `allowed_objects` will change in a future version\..*",
    category=Warning,
)

from .config import REPO_DIR
from .domain import (
    DomainProfile,
    get_domain,
    list_domains,
    register_domain,
)

__all__ = [
    "LLM",
    "REPO_DIR",
    "DomainProfile",
    "Journal",
    "KeyManager",
    "Plato",
    "Research",
    "get_domain",
    "list_domains",
    "models",
    "register_domain",
]

from importlib.metadata import PackageNotFoundError, version

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
