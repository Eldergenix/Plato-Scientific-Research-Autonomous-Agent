"""Structured-output schemas for every model call in the scientist swarm."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GoalSpec(BaseModel):
    title: str = Field(description="Short name of the sub-problem (max ~12 words).")
    objective: str = Field(description="What answering this sub-problem establishes.")


class ResearchPlan(BaseModel):
    refined_question: str = Field(description="A precise, testable research question.")
    domain: str = Field(
        description="Snake_case field, e.g. ml_systems, computational_biology."
    )
    search_queries: list[str] = Field(description="1 to 4 literature search queries.")
    goals: list[GoalSpec] = Field(
        description="2 to 4 sub-problems that together answer the question."
    )


class HintSpec(BaseModel):
    title: str
    rationale: str = Field(
        description="Why this gap or anomaly is worth testing, citing paper numbers like [3]."
    )
    cited_papers: list[int] = Field(
        description="Indices of the papers in the provided list that support the hint."
    )


class LiteratureHints(BaseModel):
    hints: list[HintSpec] = Field(
        description="Up to 5 unexplored directions grounded in the literature."
    )


class IntentSpec(BaseModel):
    title: str
    hypothesis: str = Field(description="Falsifiable claim the experiment tests.")
    protocol: str = Field(
        description="Concrete computational protocol: data, procedure, controls, metric."
    )
    primary_metric: str = Field(
        description=(
            "snake_case key (e.g. 'ci_coverage') of the single numeric metric that decides the "
            "outcome; the experiment prints its value under exactly this key."
        )
    )
    test_kind: Literal["difference", "equivalence"] = Field(
        default="difference",
        description=(
            "'difference' when the hypothesis claims an effect or a difference (p_value tests the "
            "null of no effect); 'equivalence' when it claims agreement with a reference value "
            "within a tolerance, e.g. 'coverage is 0.95' or 'RMSE matches theory' (p_value comes "
            "from a TOST equivalence test against that tolerance)."
        ),
    )
    success_criterion: str = Field(
        description=(
            "Threshold on the primary metric that supports the hypothesis. Express tolerances "
            "relative to the estimate's standard error or Monte Carlo error (e.g. 'within 3 SE "
            "of the analytical value'), never tighter than the sampling noise the protocol can resolve. "
            "For equivalence claims, state the tolerance as a number."
        )
    )
    priority: float = Field(description="0 to 1: expected information gain.")
    goal_index: int = Field(description="Index of the goal this intent serves.")
    source_hint_index: int | None = Field(
        default=None, description="Index of the hint it derives from, if any."
    )


class IntentBatch(BaseModel):
    intents: list[IntentSpec]


class ExperimentCode(BaseModel):
    code: str = Field(description="Complete, self-contained Python 3 script.")
    notes: str = Field(description="One paragraph on design choices and limitations.")


class Observation(BaseModel):
    title: str = Field(description="Short statement of what was observed.")
    observation: str = Field(
        description="Factual description of the result with numbers."
    )
    supports_hypothesis: Literal["yes", "no", "inconclusive"]
    follow_up_hints: list[str] = Field(
        description="0 to 2 anomalies or unexplored parameter ranges worth a new experiment."
    )


class SkepticVerdict(BaseModel):
    decision: Literal["promote", "reject"]
    confidence: float = Field(
        description="0 to 1 confidence that the finding is real and correctly stated."
    )
    rationale: str
    finding_title: str
    finding_statement: str = Field(
        description="The claim as it may appear in a paper, with its numbers and caveats."
    )


class FigureCritique(BaseModel):
    quality_score: float = Field(
        description="0 to 1: is the figure readable, labelled, and faithful to the data?"
    )
    issues: list[str]


class Manuscript(BaseModel):
    title: str
    abstract: str
    introduction: str
    methods: str
    results: str
    discussion: str
    limitations: str


class PeerReview(BaseModel):
    soundness: int = Field(description="1 to 4")
    presentation: int = Field(description="1 to 4")
    contribution: int = Field(description="1 to 4")
    decision: Literal["accept", "minor_revision", "major_revision", "reject"]
    summary: str
    required_changes: list[str]
