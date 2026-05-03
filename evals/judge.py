"""
Phase 3 — R7: LLM-as-judge for paper evaluation.

``LLMJudge`` runs a panel of judge models against a generated paper and
aggregates their scores. Per the design plan §7.3, the safeguard is:
*never use the model that drafted the paper to judge it.* This module
enforces that with a runtime ``ValueError`` so a misconfigured eval
cannot silently bias its own scores.

The actual model call is encapsulated in ``LLMJudge._call_judge`` so
unit tests can mock it without any network I/O.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass
class JudgeResult:
    """Per-axis judge scores (each 0..5) plus a free-form rationale."""

    coherence: int
    grounding: int
    novelty: int
    rigor: int
    rationale: str = ""


_JUDGE_PROMPT_TEMPLATE = """\
You are a peer reviewer for a scientific paper drafted by an AI agent.
Score the paper on four axes, each 0..5 (higher is better):

  - coherence: how well the paper hangs together as an argument.
  - grounding: how well claims are tied to cited evidence.
  - novelty: whether the contribution is genuinely new vs. derivative.
  - rigor: methodological soundness and quantitative care.

Respond with one sentence per axis explaining your score, then a JSON
object with the integer scores. Paper text follows.

---
{paper_text}
---
"""


class LLMJudge:
    """Multi-model LLM judge that aggregates scores by median/majority.

    Parameters
    ----------
    judges:
        Identifiers of the judge models, e.g.
        ``["gpt-4o", "claude-sonnet-4", "gemini-1.5-pro"]``. Three is
        the default panel size; the aggregate is the per-axis median so
        a single outlier cannot swing the score.
    """

    def __init__(self, judges: list[str]) -> None:
        if not judges:
            raise ValueError("LLMJudge requires at least one judge model.")
        self.judges = list(judges)

    async def judge(
        self,
        *,
        paper_text: str,
        drafting_model: str,
    ) -> JudgeResult:
        """Run the judge panel on ``paper_text`` and aggregate the scores.

        Raises
        ------
        ValueError
            If ``drafting_model`` is one of the judge models. Per plan
            §7.3, a model must never grade its own output.
        """
        if drafting_model in self.judges:
            raise ValueError(
                f"drafting_model={drafting_model!r} is in the judge list "
                f"{self.judges!r}; a model must never grade its own output."
            )
        prompt = _JUDGE_PROMPT_TEMPLATE.format(paper_text=paper_text)

        # Run each judge sequentially. Parallelism is fine to add later;
        # for now we keep the loop simple so tests can mock predictably.
        results: list[JudgeResult] = []
        for model in self.judges:
            result = await self._call_judge(model=model, prompt=prompt)
            results.append(result)

        return _aggregate(results)

    async def _call_judge(self, *, model: str, prompt: str) -> JudgeResult:
        """Invoke the judge model and parse its scores.

        Falls back to a neutral 0/0/0/0 result with the failure mode
        captured in the ``rationale`` field if any of:
        - the model name is unknown to ``plato.llm.models``,
        - the underlying provider key is unset,
        - the LLM call raises (rate limit, network, etc.),
        - the response can't be JSON-parsed.

        Tests that don't want to touch the network override this method.
        """
        try:
            return await self._real_call_judge(model=model, prompt=prompt)
        except Exception as exc:  # noqa: BLE001
            return JudgeResult(
                coherence=0,
                grounding=0,
                novelty=0,
                rigor=0,
                rationale=f"judge {model} failed: {exc!r}",
            )

    async def _real_call_judge(self, *, model: str, prompt: str) -> JudgeResult:
        """Concrete LLM invocation — split out so the public method can wrap it
        in a single try/except without tangling the happy-path logic."""
        import json
        import re

        # Lazy import so ``evals`` stays importable on installs that
        # haven't pulled the LLM provider extras.
        from plato.llm import models as _models, llm_parser

        if model not in _models:
            raise KeyError(
                f"Unknown judge model {model!r}. "
                f"Add it to plato.llm.models or pick one of {sorted(_models)}."
            )
        client = llm_parser(model)
        # ``client`` is a BaseChatModel — ainvoke is async and returns
        # a Message; .content is the raw string.
        from langchain_core.messages import HumanMessage

        result = await client.llm.ainvoke([HumanMessage(content=prompt)])
        text = getattr(result, "content", "") or ""

        # Find the trailing JSON object — the prompt asks for prose
        # then JSON, so we scan from the back.
        match = re.search(r"\{[^{}]*?\"coherence\"[^{}]*?\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError(f"no JSON object in response: {text[:200]!r}")
        payload = json.loads(match.group(0))

        def _score(key: str) -> int:
            v = payload.get(key, 0)
            try:
                n = int(v)
            except (TypeError, ValueError):
                n = 0
            return max(0, min(5, n))

        return JudgeResult(
            coherence=_score("coherence"),
            grounding=_score("grounding"),
            novelty=_score("novelty"),
            rigor=_score("rigor"),
            rationale=text[: match.start()].strip(),
        )


def _aggregate(results: list[JudgeResult]) -> JudgeResult:
    """Aggregate per-axis scores by integer median (majority for ties)."""
    if not results:
        raise ValueError("Cannot aggregate empty judge results.")

    def med(field: str) -> int:
        # ``statistics.median_low`` returns one of the data points so the
        # aggregate is always an int even for an even-sized panel.
        return int(statistics.median_low(getattr(r, field) for r in results))

    rationale = "\n---\n".join(r.rationale for r in results if r.rationale)
    return JudgeResult(
        coherence=med("coherence"),
        grounding=med("grounding"),
        novelty=med("novelty"),
        rigor=med("rigor"),
        rationale=rationale,
    )


__all__ = ["LLMJudge", "JudgeResult"]
