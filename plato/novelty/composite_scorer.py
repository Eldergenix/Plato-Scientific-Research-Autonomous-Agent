"""
Composite novelty scorer that blends an LLM verdict with the embedding score.

The LLM (``novelty_decider`` node) judges whether an idea is *conceptually*
new; the embedding scorer asks whether anything in the retrieved corpus is
already a near-paraphrase. They disagree often enough that fusing them
catches both kinds of false positive.

The caller passes the LLM score in; this scorer doesn't run an LLM itself.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from plato.novelty.embedding_scorer import EmbeddingScorer
from plato.state.models import Source


_AGREEMENT_THRESHOLD = 0.3


class CompositeNoveltyScore(BaseModel):
    """LLM + embedding fusion for one idea/corpus pair."""

    llm_score: float = Field(ge=0.0, le=1.0)
    embedding_score: float = Field(ge=0.0, le=1.0)
    combined: float = Field(ge=0.0, le=1.0)
    agreement: bool = Field(
        description=(
            "True when LLM and embedding scores are within "
            f"{_AGREEMENT_THRESHOLD} of each other."
        ),
    )


class CompositeNoveltyScorer:
    """Combine a caller-supplied LLM novelty score with the embedding score."""

    def __init__(
        self,
        embedding_scorer: EmbeddingScorer | None = None,
        *,
        llm_weight: float = 0.5,
    ) -> None:
        if not 0.0 <= llm_weight <= 1.0:
            raise ValueError(
                f"llm_weight must be in [0, 1]; got {llm_weight!r}"
            )
        self.embedding_scorer = embedding_scorer or EmbeddingScorer()
        self.llm_weight = llm_weight

    async def score(
        self,
        *,
        idea: str,
        corpus: list[Source],
        llm_score: float,
    ) -> CompositeNoveltyScore:
        if not 0.0 <= llm_score <= 1.0:
            raise ValueError(
                f"llm_score must be in [0, 1]; got {llm_score!r}"
            )

        embedding_result = await self.embedding_scorer.score(idea, corpus)
        embedding_score = embedding_result.score

        combined = (
            self.llm_weight * llm_score
            + (1.0 - self.llm_weight) * embedding_score
        )
        agreement = abs(llm_score - embedding_score) < _AGREEMENT_THRESHOLD

        return CompositeNoveltyScore(
            llm_score=llm_score,
            embedding_score=embedding_score,
            combined=combined,
            agreement=agreement,
        )


__all__ = ["CompositeNoveltyScore", "CompositeNoveltyScorer"]
