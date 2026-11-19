"""Which Claude model each agent role uses, and what its tokens cost against budgets.

Roles
-----
The project agent (``orchestrator``, run by the Worker) plans the research and talks with
the person; every role inside a research thread is a task sub-agent. Defaults: Claude Opus
5.5 for the orchestrator, Claude Haiku 5.5 for every sub-agent. Configuration:

* ``PLATO_ORCHESTRATOR_MODEL``: the project agent (read by the Worker).
* ``PLATO_SCIENTIST_MODEL``: every sub-agent role without an override.
* ``PLATO_ROLE_MODELS``: optional JSON object of per-role overrides, e.g.
  ``{"skeptic": "claude-sonnet-5-5"}``. Unknown roles and non-string values are rejected.

A research thread freezes its role map when it is created (``config["models"]``), so a
deploy that changes the defaults never switches models under a running thread.

Allowance tokens
----------------
Budgets and the monthly allowance count *allowance tokens*: tokens priced as Claude Haiku
5.5 tokens. A call's token count is multiplied by its model's weight, the ratio of the
model's per-token price to Claude Haiku 5.5's (input and output ratios are equal for every
model listed). Haiku 5.5 calls count exactly as before; a Claude Opus 5.5 call counts 40x,
so the allowance keeps bounding what the shared key spends whatever the models are. A
model missing from the table gets the highest listed weight, so a new or mistyped model
can never be undercharged. ``cloudflare/plato-scientist/src/models.json`` must equal
:func:`catalogue` (a test enforces it).
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping

ORCHESTRATOR_DEFAULT = "claude-opus-5-5"
WORKER_DEFAULT = "claude-haiku-5-5"

# Price per token relative to Claude Haiku 5.5 ($0.10 / $0.50 per MTok input / output for
# prompts up to 100K tokens). Source: Anthropic's published API prices, November 2026.
WEIGHTS: dict[str, int] = {
    "claude-haiku-5-5": 1,  # $0.10 / $0.50
    "claude-haiku-4-5": 10,  # $1 / $5
    "claude-sonnet-5-5": 20,  # $2 / $10
    "claude-sonnet-5": 20,  # $2 / $10
    "claude-sonnet-4-6": 30,  # $3 / $15
    "claude-opus-5-5": 40,  # $4 / $20
    "claude-opus-5": 50,  # $5 / $25
    "claude-opus-4-8": 50,
    "claude-opus-4-7": 50,
    "claude-opus-4-6": 50,
    "claude-fable-5-2": 80,  # $8 / $40
    "claude-fable-5-1": 100,  # $10 / $50
    "claude-fable-5": 100,
}
UNKNOWN_WEIGHT = max(WEIGHTS.values())

# Sub-agent roles inside a research thread, and the call purposes each one makes.
ROLE_PURPOSES: dict[str, tuple[str, ...]] = {
    "planner": ("plan", "hints", "plan_intents"),
    "experiment_writer": ("write_experiment",),
    "workspace_engineer": ("workspace_engineer",),
    "observer": ("observe",),
    "figure_critic": ("figure_critique",),
    "skeptic": ("skeptic",),
    "paper_writer": ("manuscript", "manuscript_revision"),
    "peer_reviewer": ("peer_review",),
    "evidence_checker": ("evidence_matrix",),
    "review_panel": (
        "review_methodology",
        "review_statistics",
        "review_novelty",
        "review_writing",
    ),
    # Journal front matter for a publication export.
    "publication_formatter": ("publication_format",),
}
WORKER_ROLES: tuple[str, ...] = tuple(ROLE_PURPOSES)
ROLES: tuple[str, ...] = ("orchestrator", *WORKER_ROLES)
_PURPOSE_ROLE = {p: role for role, ps in ROLE_PURPOSES.items() for p in ps}


class ModelConfigError(ValueError):
    """``PLATO_ROLE_MODELS`` (or a frozen role map) is malformed."""


def weight(model: str) -> int:
    return WEIGHTS.get(model, UNKNOWN_WEIGHT)


def allowance_tokens(model: str, tokens: int) -> int:
    """``tokens`` of ``model`` expressed in allowance (Claude Haiku 5.5) tokens."""
    return max(0, tokens) * weight(model)


def role_for(purpose: str) -> str | None:
    return _PURPOSE_ROLE.get(purpose)


def _model_name(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 100:
        raise ModelConfigError(f"{where} must be a model id string")
    return value.strip()


def role_overrides(env: Mapping[str, str] | None = None) -> dict[str, str]:
    raw = (env if env is not None else os.environ).get("PLATO_ROLE_MODELS", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModelConfigError(f"PLATO_ROLE_MODELS is not valid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise ModelConfigError("PLATO_ROLE_MODELS must be a JSON object of role -> model")
    unknown = sorted(set(data) - set(WORKER_ROLES))
    if unknown:
        raise ModelConfigError(
            f"PLATO_ROLE_MODELS has unknown roles {unknown}; known: {list(WORKER_ROLES)}"
        )
    return {role: _model_name(m, f"PLATO_ROLE_MODELS[{role!r}]") for role, m in data.items()}


def worker_default(env: Mapping[str, str] | None = None) -> str:
    value = (env if env is not None else os.environ).get("PLATO_SCIENTIST_MODEL", "")
    return value.strip() or WORKER_DEFAULT


def role_models(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """The model of every sub-agent role under the current configuration."""
    default = worker_default(env)
    return {role: default for role in WORKER_ROLES} | role_overrides(env)


def frozen_role_models(config: Mapping[str, object] | None) -> dict[str, str] | None:
    """The role map a research thread was created with (None for older threads)."""
    models = (config or {}).get("models")
    if models is None:
        return None
    if not isinstance(models, dict):
        raise ModelConfigError("campaign config 'models' must be an object")
    return {str(role): _model_name(m, f"models[{role!r}]") for role, m in models.items()}


def catalogue() -> dict[str, object]:
    """What the Worker needs: defaults, roles and weights (mirrored in models.json)."""
    return {
        "orchestrator_default": ORCHESTRATOR_DEFAULT,
        "worker_default": WORKER_DEFAULT,
        "roles": list(WORKER_ROLES),
        "weights": dict(WEIGHTS),
        "unknown_weight": UNKNOWN_WEIGHT,
    }

