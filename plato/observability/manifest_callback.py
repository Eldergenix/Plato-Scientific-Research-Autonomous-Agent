"""ManifestCallbackHandler — drains LLM token-usage events into a ManifestRecorder.

LangChain dispatches ``on_llm_end(response, ...)`` after every chat completion.
We extract the provider's token-usage block, sum into the recorder's running
``tokens_in``/``tokens_out`` totals, and accrue an estimated ``cost_usd`` against
a small per-model price table. Unknown models contribute zero cost (no crash —
the manifest still records token counts).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.callbacks.base import BaseCallbackHandler

if TYPE_CHECKING:
    from ..state.manifest import ManifestRecorder


# Per-million-token prices (input, output) snapshotted 2026-04. Only models
# Plato actually wires today are listed; unknown models silently fall through.
_PRICE_PER_M: dict[str, tuple[float, float]] = {
    "gpt-4o-mini":          (0.15,  0.60),
    "gpt-4o":               (2.50, 10.00),
    "gpt-4.1":              (3.00, 12.00),
    "gpt-4.1-mini":         (0.40,  1.60),
    "gpt-5":                (5.00, 25.00),
    "o3-mini":              (1.10,  4.40),
    "claude-sonnet-4-5":    (3.00, 15.00),
    "claude-4.1-opus":      (15.00, 75.00),
    "gemini-2.5-flash":     (0.075, 0.30),
    "gemini-2.5-pro":       (1.25,  5.00),
}


def _extract_usage(llm_output: dict[str, Any]) -> tuple[int, int]:
    """Return ``(input_tokens, output_tokens)`` from a provider llm_output dict.

    Handles three conventions:
    - OpenAI/Azure: ``prompt_tokens`` / ``completion_tokens``
    - Anthropic:    ``input_tokens``  / ``output_tokens``
    - Google Gemini: ``prompt_token_count`` / ``candidates_token_count``
    """
    tu = llm_output.get("token_usage") or llm_output.get("usage") or llm_output
    if not isinstance(tu, dict):
        return 0, 0

    inp = (
        tu.get("prompt_tokens")
        or tu.get("input_tokens")
        or tu.get("prompt_token_count")
        or 0
    )
    out = (
        tu.get("completion_tokens")
        or tu.get("output_tokens")
        or tu.get("candidates_token_count")
        or 0
    )
    try:
        return int(inp), int(out)
    except (TypeError, ValueError):
        return 0, 0


def _compute_cost(model: str, inp: int, out: int) -> float:
    """Estimate cost in USD for ``inp``+``out`` tokens at ``model``'s price."""
    prices = _PRICE_PER_M.get(model)
    if prices is None:
        return 0.0
    price_in, price_out = prices
    return (inp * price_in + out * price_out) / 1_000_000


class ManifestCallbackHandler(BaseCallbackHandler):
    """LangChain handler that forwards token usage to a :class:`ManifestRecorder`."""

    def __init__(self, recorder: "ManifestRecorder") -> None:
        super().__init__()
        self._recorder = recorder

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:  # noqa: ARG002
        llm_output = getattr(response, "llm_output", None)
        if not isinstance(llm_output, dict):
            return

        inp, out = _extract_usage(llm_output)
        if inp == 0 and out == 0:
            return

        # Best-effort model name from the response or from the recorder's
        # manifest (which has whatever the workflow registered at start).
        model = (
            llm_output.get("model_name")
            or llm_output.get("model")
            or next(iter(self._recorder.manifest.models.values()), "")
        )
        cost = _compute_cost(model, inp, out)
        try:
            self._recorder.add_tokens(
                input_tokens=inp, output_tokens=out, cost_usd=cost
            )
        except Exception:  # noqa: BLE001
            # Recorder failures must never crash the LLM call path.
            pass


__all__ = ["ManifestCallbackHandler"]
