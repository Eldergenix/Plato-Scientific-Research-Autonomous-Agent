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
    intents: list[IntentSpec] = Field(
        description="The proposed experiments: no more than the number asked for."
    )


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


ManuscriptSection = Literal[
    "title",
    "abstract",
    "introduction",
    "methods",
    "results",
    "discussion",
    "limitations",
]
Decision = Literal["accept", "minor_revision", "major_revision", "reject"]


class ClaimAssessment(BaseModel):
    """The editor's verdict on one claim of the manuscript, tied to its exact words."""

    section: ManuscriptSection
    quote: str = Field(
        description=(
            "The claim exactly as the manuscript states it: one sentence or clause copied "
            "verbatim from that section (5 to 60 words, LaTeX included as written)."
        )
    )
    category: Literal[
        "result",
        "statistics",
        "methodology",
        "interpretation",
        "citation",
        "reproducibility",
        "presentation",
    ]
    verdict: Literal["approved", "needs_revision", "rejected"] = Field(
        description=(
            "approved: the evidence supports the claim as written. needs_revision: the "
            "claim is broadly right but overstated, imprecise, or missing a number, "
            "uncertainty or caveat. rejected: the evidence contradicts it, does not "
            "establish it, or it reports a number that is not in the evidence."
        )
    )
    severity: Literal["minor", "major", "critical"] = Field(
        description="How much the problem matters to the paper's conclusions (minor when approved)."
    )
    evidence: str = Field(
        description=(
            "What the evidence shows for this claim, with the exact measured values "
            "(metric, estimate, interval or standard error, p-value, n, seeds), or what "
            "is missing from it."
        )
    )
    critique: str = Field(description="Why the verdict, in one to three sentences.")
    fix: str = Field(
        description="The concrete edit that would make the claim acceptable; empty when approved."
    )


class PeerReview(BaseModel):
    summary: str = Field(
        description="What the paper claims and the editor's overall judgement, three sentences at most."
    )
    strengths: list[str] = Field(description="At most 5, most important first.")
    assessments: list[ClaimAssessment] = Field(
        description=(
            "Between 6 and 20 claims: every quantitative result, every statement about a "
            "verified finding, refuted hypothesis or preliminary observation, and the main "
            "conclusions of the abstract and discussion. Most consequential first."
        )
    )
    soundness: int = Field(description="1 to 4")
    presentation: int = Field(description="1 to 4")
    contribution: int = Field(description="1 to 4")
    decision: Decision
    required_changes: list[str]


class RevisionOutcome(BaseModel):
    assessment: int = Field(description="Index of the assessment in the review.")
    status: Literal["resolved", "partially_resolved", "unresolved", "removed"] = Field(
        description=(
            "resolved: the revised text fixes the problem (or the approved claim still "
            "stands). partially_resolved: improved but not fully. unresolved: the problem "
            "remains. removed: the claim no longer appears."
        )
    )
    final_quote: str = Field(
        description=(
            "Where the claim now appears: one sentence or clause copied verbatim from the "
            "revised manuscript. Empty when removed."
        )
    )
    note: str = Field(description="One sentence on what changed.")


class RevisionCheck(BaseModel):
    outcomes: list[RevisionOutcome]
    final_summary: str = Field(
        description="Two sentences at most on the revised paper."
    )
    final_decision: Decision


class CitationSupport(BaseModel):
    pair_index: int = Field(
        description="Index of the claim-citation pair being judged."
    )
    support: Literal["supports", "refutes", "neutral", "unclear"] = Field(
        description=(
            "Does the cited abstract support the claim? 'neutral' when it is related but "
            "does not bear on the claim; 'unclear' when the abstract is too thin to tell."
        )
    )
    strength: Literal["weak", "moderate", "strong"]
    quote: str = Field(
        description=(
            "For supports/refutes: the shortest verbatim span of the abstract (copied "
            "exactly, 5 to 60 words) that supports or contradicts the claim. Empty otherwise."
        )
    )
    rationale: str = Field(description="One sentence.")


class EvidenceMatrix(BaseModel):
    links: list[CitationSupport]


class ReviewIssue(BaseModel):
    section: str = Field(description="Manuscript section the issue is in.")
    issue: str
    fix: str = Field(description="Concrete change that resolves the issue.")


class PanelCritique(BaseModel):
    severity: int = Field(
        description="0 (no problems) to 5 (fatal) for this reviewer's angle only."
    )
    summary: str = Field(description="Two sentences at most.")
    issues: list[ReviewIssue] = Field(description="At most 6, most important first.")
