from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


StageId = Literal["data", "idea", "literature", "method", "results", "paper", "referee"]
StageStatus = Literal["empty", "pending", "running", "done", "stale", "failed"]
RunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
Mode = Literal["fast", "cmbagent"]


class Journal(str, Enum):
    NONE = "NONE"
    AAS = "AAS"
    APS = "APS"
    ICML = "ICML"
    JHEP = "JHEP"
    NeurIPS = "NeurIPS"
    PASJ = "PASJ"


class Stage(BaseModel):
    id: StageId
    label: str
    status: StageStatus = "empty"
    model: Optional[str] = None
    duration_ms: Optional[int] = None
    last_run_at: Optional[datetime] = None
    origin: Optional[Literal["ai", "edited"]] = None
    progress_label: Optional[str] = None


class ActiveRun(BaseModel):
    run_id: str
    stage: StageId
    started_at: datetime
    step: Optional[int] = None
    total_steps: Optional[int] = None
    attempt: Optional[int] = None
    total_attempts: Optional[int] = None


class Project(BaseModel):
    id: str = Field(default_factory=lambda: new_id("prj"))
    name: str = "Untitled project"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    journal: Journal = Journal.NONE
    stages: dict[StageId, Stage]
    active_run: Optional[ActiveRun] = None
    total_tokens: int = 0
    total_cost_cents: int = 0

    @classmethod
    def empty(cls, name: str = "Untitled project") -> "Project":
        return cls(
            name=name,
            stages={
                "data": Stage(id="data", label="Data"),
                "idea": Stage(id="idea", label="Idea"),
                "literature": Stage(id="literature", label="Lit"),
                "method": Stage(id="method", label="Method"),
                "results": Stage(id="results", label="Results"),
                "paper": Stage(id="paper", label="Paper"),
                "referee": Stage(id="referee", label="Referee"),
            },
        )


class Run(BaseModel):
    id: str = Field(default_factory=lambda: new_id("run"))
    project_id: str
    stage: StageId
    mode: Mode = "fast"
    status: RunStatus = "queued"
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    config: dict = Field(default_factory=dict)
    pid: Optional[int] = None
    token_input: int = 0
    token_output: int = 0


class StageRunRequest(BaseModel):
    mode: Mode = "fast"
    models: dict[str, str] = Field(default_factory=dict)
    journal: Optional[Journal] = None
    add_citations: bool = True
    iterations: Optional[int] = None
    extra: dict = Field(default_factory=dict)


class StageContent(BaseModel):
    stage: StageId
    markdown: str
    updated_at: datetime
    origin: Literal["ai", "edited"] = "ai"


class KeysPayload(BaseModel):
    OPENAI: Optional[str] = None
    GEMINI: Optional[str] = None
    ANTHROPIC: Optional[str] = None
    PERPLEXITY: Optional[str] = None
    SEMANTIC_SCHOLAR: Optional[str] = None


class KeysStatus(BaseModel):
    OPENAI: Literal["unset", "from_env", "in_app"] = "unset"
    GEMINI: Literal["unset", "from_env", "in_app"] = "unset"
    ANTHROPIC: Literal["unset", "from_env", "in_app"] = "unset"
    PERPLEXITY: Literal["unset", "from_env", "in_app"] = "unset"
    SEMANTIC_SCHOLAR: Literal["unset", "from_env", "in_app"] = "unset"


class Capabilities(BaseModel):
    """What the current session is allowed to do."""

    is_demo: bool
    allowed_stages: list[StageId]
    max_concurrent_runs: int
    session_budget_cents: Optional[int] = None
    session_used_cents: int = 0
    notes: list[str] = Field(default_factory=list)
