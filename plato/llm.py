from pydantic import BaseModel
from typing import Dict


class LLM(BaseModel):
    """LLM base model"""

    name: str
    """Name/identifier of the model."""
    max_output_tokens: int
    """Maximum output tokens allowed."""
    temperature: float | None
    """Temperature of the model."""


gemini20flash = LLM(name="gemini-2.0-flash", max_output_tokens=8192, temperature=0.7)
"""`gemini-2.0-flash` model."""

gemini25flash = LLM(name="gemini-2.5-flash", max_output_tokens=65536, temperature=0.7)
"""`gemini-2.5-flash` model."""

gemini25pro = LLM(name="gemini-2.5-pro", max_output_tokens=65536, temperature=0.7)
"""`gemini-2.5-pro` model."""

o3mini = LLM(name="o3-mini-2025-01-31", max_output_tokens=100000, temperature=None)
"""`o3-mini` model."""

gpt4o = LLM(name="gpt-4o-2024-11-20", max_output_tokens=16384, temperature=0.5)
"""`gpt-4o` model."""

gpt41 = LLM(name="gpt-4.1-2025-04-14", max_output_tokens=16384, temperature=0.5)
"""`gpt-4.1` model."""

gpt41mini = LLM(name="gpt-4.1-mini", max_output_tokens=16384, temperature=0.5)
"""`gpt-4.1-mini` model."""

gpt4omini = LLM(name="gpt-4o-mini-2024-07-18", max_output_tokens=16384, temperature=0.5)
"""`gpt-4o-mini` model."""

gpt45 = LLM(name="gpt-4.5-preview-2025-02-27", max_output_tokens=16384, temperature=0.5)
"""`gpt-4.5-preview` model."""

gpt5 = LLM(name="gpt-5", max_output_tokens=128000, temperature=None)
"""`gpt-5` model """

gpt5mini = LLM(name="gpt-5-mini", max_output_tokens=128000, temperature=None)
"""`gpt-5-mini` model."""

gpt55 = LLM(name="gpt-5.5-2026-04-23", max_output_tokens=128000, temperature=None)
"""`gpt-5.5` current snapshot model."""

gpt55pro = LLM(name="gpt-5.5-pro", max_output_tokens=128000, temperature=None)
"""`gpt-5.5-pro` model."""

claude47opus = LLM(name="claude-opus-4-7", max_output_tokens=32000, temperature=None)
"""`claude-4.7-Opus` model."""

# Current Claude models. They reject non-default sampling parameters, so temperature
# stays None. max_output_tokens stays at 32K so non-streaming calls stay within the
# SDK's request-duration guard (the models allow up to 128K when streaming).
claude55opus = LLM(name="claude-opus-5-5", max_output_tokens=32000, temperature=None)
"""`claude-opus-5-5` model."""

claude55sonnet = LLM(name="claude-sonnet-5-5", max_output_tokens=32000, temperature=None)
"""`claude-sonnet-5-5` model."""

claude55haiku = LLM(name="claude-haiku-5-5", max_output_tokens=32000, temperature=None)
"""`claude-haiku-5-5` model: the default for the autonomous scientist swarm."""

# Registry keys whose models were retired by Anthropic (the API now rejects them):
# claude-3-7-sonnet-20250219 (2026-02-19), claude-opus-4-20250514 (2026-06-15) and
# claude-opus-4-1-20250805 (2026-08-05). They resolve to the documented successor so
# existing configs keep running; ``plato.utils.llm_parser`` warns when one is used.
RETIRED_ALIASES: Dict[str, str] = {
    "claude-3.7-sonnet": "claude-sonnet-5.5",
    "claude-4-opus": "claude-opus-5.5",
    "claude-4.1-opus": "claude-opus-5.5",
}

deepseekv4 = LLM(
    name="deepseek-ai/DeepSeek-V4-Flash", max_output_tokens=65536, temperature=0.7
)
"""`deepseek-ai/DeepSeek-V4-Flash` model served through Hugging Face."""

deepseekv4pro = LLM(
    name="deepseek-ai/DeepSeek-V4-Pro", max_output_tokens=65536, temperature=0.7
)
"""`deepseek-ai/DeepSeek-V4-Pro` model served through Hugging Face."""

qwen36_27b = LLM(name="Qwen/Qwen3.6-27B", max_output_tokens=65536, temperature=0.7)
"""`Qwen/Qwen3.6-27B` model served through Hugging Face."""

llama33_70b = LLM(
    name="meta-llama/Llama-3.3-70B-Instruct", max_output_tokens=32768, temperature=0.7
)
"""`meta-llama/Llama-3.3-70B-Instruct` model served through Hugging Face."""

kimi_k26 = LLM(name="moonshotai/Kimi-K2.6", max_output_tokens=65536, temperature=0.7)
"""`moonshotai/Kimi-K2.6` model served through Hugging Face."""

nemotron3_super = LLM(
    name="nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4",
    max_output_tokens=32768,
    temperature=0.7,
)
"""`nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4` model served through Hugging Face."""

gemini31pro = LLM(name="gemini-3.1-pro", max_output_tokens=65536, temperature=0.7)
"""`gemini-3.1-pro` model."""

models: Dict[str, LLM] = {
    "gemini-2.0-flash": gemini20flash,
    "gemini-2.5-flash": gemini25flash,
    "gemini-2.5-pro": gemini25pro,
    "o3-mini": o3mini,
    "gpt-4o": gpt4o,
    "gpt-4.1": gpt41,
    "gpt-4.1-mini": gpt41mini,
    "gpt-4o-mini": gpt4omini,
    "gpt-4.5": gpt45,
    "gpt-5": gpt5,
    "gpt-5-mini": gpt5mini,
    "gpt-5.5": gpt55,
    "gpt-5.5-2026-04-23": gpt55,
    "gpt-5.5-pro": gpt55pro,
    "claude-4.7-opus": claude47opus,
    "claude-opus-5.5": claude55opus,
    "claude-opus-5-5": claude55opus,
    "claude-sonnet-5.5": claude55sonnet,
    "claude-sonnet-5-5": claude55sonnet,
    "claude-haiku-5.5": claude55haiku,
    "claude-haiku-5-5": claude55haiku,
    "deepseek-v4": deepseekv4,
    "deepseek-v4-pro": deepseekv4pro,
    "Qwen/Qwen3.6-27B": qwen36_27b,
    "qwen3.6-27b": qwen36_27b,
    "meta-llama/Llama-3.3-70B-Instruct": llama33_70b,
    "llama-3.3-70b-instruct": llama33_70b,
    "moonshotai/Kimi-K2.6": kimi_k26,
    "kimi-k2.6": kimi_k26,
    "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4": nemotron3_super,
    "nemotron-3-super": nemotron3_super,
    "gemini-3.1-pro": gemini31pro,
}
"""Dictionary with the available models."""

models.update({old: models[new] for old, new in RETIRED_ALIASES.items()})
