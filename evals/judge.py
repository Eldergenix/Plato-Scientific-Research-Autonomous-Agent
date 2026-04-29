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
        """Stub model call — overridden in production, mocked in tests.

        The base implementation deliberately returns a neutral score so
        that running the harness without a real LLM provider does not
        crash; tests should always mock this method.
        """
        return JudgeResult(
            coherence=0,
            grounding=0,
            novelty=0,
            rigor=0,
            rationale=f"stub judge response from {model}",
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
