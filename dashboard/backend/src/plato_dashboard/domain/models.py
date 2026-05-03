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
    # 256-char cap on free-form strings — these end up in meta.json on
    # disk; an unbounded label/model from a buggy run-result writer
    # would silently produce a bloated metadata row.
    label: str = Field(max_length=256)
    status: StageStatus = "empty"
    model: Optional[str] = Field(default=None, max_length=256)
    duration_ms: Optional[int] = Field(default=None, ge=0)
    last_run_at: Optional[datetime] = None
    origin: Optional[Literal["ai", "edited"]] = None
    progress_label: Optional[str] = Field(default=None, max_length=256)


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
    # Iter-24: per-project tenant binding. Set on creation from the
    # request's ``X-Plato-User`` header so every project-level endpoint
    # can refuse cross-tenant reads/writes/launches without depending on
    # a per-run manifest.json (which doesn't exist yet at create time).
    # ``None`` means "legacy un-namespaced project" — accessible only
    # when ``PLATO_DASHBOARD_AUTH_REQUIRED=1`` is unset.
    user_id: Optional[str] = None

    @classmethod
    def empty(cls, name: str = "Untitled project", user_id: str | None = None) -> "Project":
        return cls(
            name=name,
            user_id=user_id,
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


class JsonObjectResponse(BaseModel):
    """Generic free-form JSON-object response.

    Used as the ``response_model`` for endpoints whose payload is a
    JSON sidecar produced by the agent graphs (manifests, critiques,
    citation graphs, etc.). The shape varies with the LLM workflow,
    so we don't pin inner fields — but declaring an envelope object
    gives FastAPI's OpenAPI generator something concrete instead of
    an empty schema (``{}``).
    """

    model_config = {"extra": "allow"}


class CreateProjectRequest(BaseModel):
    """Body for ``POST /api/v1/projects``.

    The 255-char cap on ``name`` mirrors common filesystem display
    constraints; the 16k cap on ``data_description`` keeps a
    runaway client from filling project_dir with a megabyte of text
    before any LLM call has happened.
    """

    name: str = Field("Untitled project", max_length=255, min_length=1)
    data_description: Optional[str] = Field(default=None, max_length=16384)


class StageContent(BaseModel):
    stage: StageId
    markdown: str
    updated_at: datetime
    origin: Literal["ai", "edited"] = "ai"


class WriteStageRequest(BaseModel):
    """Body for ``PUT /api/v1/projects/{pid}/state/{stage}``.

    Cap markdown at 256 KiB — generous for a section but enough to
    prevent unbounded payloads from a buggy editor or an attacker.
    """

    markdown: str = Field("", max_length=262144)


class KeysPayload(BaseModel):
    OPENAI: Optional[str] = None
    GEMINI: Optional[str] = None
    ANTHROPIC: Optional[str] = None
    PERPLEXITY: Optional[str] = None
    SEMANTIC_SCHOLAR: Optional[str] = None
    LANGFUSE_PUBLIC: Optional[str] = None
    LANGFUSE_SECRET: Optional[str] = None
    LANGFUSE_HOST: Optional[str] = None


class KeysStatus(BaseModel):
    OPENAI: Literal["unset", "from_env", "in_app"] = "unset"
    GEMINI: Literal["unset", "from_env", "in_app"] = "unset"
    ANTHROPIC: Literal["unset", "from_env", "in_app"] = "unset"
    PERPLEXITY: Literal["unset", "from_env", "in_app"] = "unset"
    SEMANTIC_SCHOLAR: Literal["unset", "from_env", "in_app"] = "unset"
    LANGFUSE_PUBLIC: Literal["unset", "from_env", "in_app"] = "unset"
    LANGFUSE_SECRET: Literal["unset", "from_env", "in_app"] = "unset"
    LANGFUSE_HOST: Literal["unset", "from_env", "in_app"] = "unset"


class Capabilities(BaseModel):
    """What the current session is allowed to do."""

    is_demo: bool
    allowed_stages: list[StageId]
    max_concurrent_runs: int
    session_budget_cents: Optional[int] = None
    session_used_cents: int = 0
    notes: list[str] = Field(default_factory=list)
