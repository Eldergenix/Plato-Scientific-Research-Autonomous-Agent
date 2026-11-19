"""Sandbox workspaces where agents run real computational work (E2B in production).

* :mod:`.backend`: the sandbox primitives (E2B microVM, or a local directory for tests).
* :mod:`.tools`: the agent's tools (shell, files, search, packages, datasets, jobs,
  compile, submit) and the recorded setup recipe.
* :mod:`.agent`: the tool-use loop for the research engineer.
* :mod:`.runtime`: backend selection and the reproducible experiment runner.
* :mod:`.compile`: LaTeX/pandoc document compilation in a sandbox.
* :mod:`.lab`: what the ``plato-lab`` template contains.
"""

from .agent import SessionLimits, SessionOutcome, run_session
from .backend import CommandOutcome, E2BBackend, LocalBackend, SandboxBackend
from .compile import CompileError, CompileResult, compile_document
from .runtime import BackendFactory, default_backend_factory, e2b_configured, run_recipe
from .tools import TOOL_SPECS, ToolResult, Workspace

__all__ = [
    "TOOL_SPECS",
    "BackendFactory",
    "CommandOutcome",
    "CompileError",
    "CompileResult",
    "E2BBackend",
    "LocalBackend",
    "SandboxBackend",
    "SessionLimits",
    "SessionOutcome",
    "ToolResult",
    "Workspace",
    "compile_document",
    "default_backend_factory",
    "e2b_configured",
    "run_recipe",
    "run_session",
]
