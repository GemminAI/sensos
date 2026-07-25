from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .enums import (
    AgentProvider,
    AgentStatus,
    ExperimentStatus,
    ExperimentType,
    ForwardStatus,
    RuntimeEventType,
    SCHEMA_VERSION,
)


class AgentCreate(BaseModel):
    display_name: Optional[str] = None
    provider: AgentProvider
    model: str
    transport: str = "mcp"
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    agent_id: UUID
    display_name: Optional[str]
    provider: str
    model: str
    transport: str
    capabilities: list[str]
    status: str
    metadata: dict[str, Any]
    registered_at: datetime
    last_seen_at: Optional[datetime]

    model_config = {"from_attributes": True}


class SessionCreate(BaseModel):
    label: Optional[str] = None
    participants: list[UUID] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


class SessionJoin(BaseModel):
    agent_id: UUID
    role: str = "participant"


class SessionResponse(BaseModel):
    session_id: UUID
    label: Optional[str]
    status: str
    kernel_run_ids: dict[str, Any]
    options: dict[str, Any]
    created_at: datetime
    closed_at: Optional[datetime]
    participants: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ExperimentCreate(BaseModel):
    experiment_type: ExperimentType = ExperimentType.SEP
    label: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExperimentResponse(BaseModel):
    experiment_id: UUID
    session_id: UUID
    experiment_type: str
    label: Optional[str]
    status: str
    metadata: dict[str, Any]
    started_at: datetime
    ended_at: Optional[datetime]

    model_config = {"from_attributes": True}


class RuntimeEventEnvelope(BaseModel):
    schema_version: str = SCHEMA_VERSION
    event_id: UUID
    event_type: RuntimeEventType | str
    experiment_id: Optional[UUID] = None
    session_id: UUID
    agent_id: UUID
    source_provider: str
    source_model: Optional[str] = None
    parent_event_id: Optional[UUID] = None
    timestamp: datetime
    sequence_id: Optional[int] = None
    correlation_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class EventIngestRequest(BaseModel):
    event_type: RuntimeEventType | str
    experiment_id: Optional[UUID] = None
    agent_id: UUID
    source_provider: Optional[str] = None
    source_model: Optional[str] = None
    parent_event_id: Optional[UUID] = None
    correlation_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class EventResponse(BaseModel):
    event_id: UUID
    schema_version: str
    event_type: str
    experiment_id: Optional[UUID]
    session_id: UUID
    agent_id: Optional[UUID]
    source_provider: Optional[str]
    source_model: Optional[str]
    parent_event_id: Optional[UUID]
    sequence_id: int
    sep_event_type: Optional[str]
    payload: dict[str, Any]
    forward_status: str
    kernel_run_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class EventIngestResponse(BaseModel):
    accepted: int
    event_ids: list[UUID]
    forward_status: ForwardStatus


class CapabilitiesResponse(BaseModel):
    service: str
    version: str
    rfc: str
    features: list[str]
    mcp_tools: list[str]
    layer3_stubs: list[str]


class GenerateRequest(BaseModel):
    article: str
    origin: str = "us"


class GenerateResponse(BaseModel):
    state_hash: str
    narrative: str
    tags: dict[str, Any]
    subject_origin: str
    schema_version: str
    epistemic_diffusion_state: str
    article: str
    provider: str
    created_at: str | None = None


class StateListItem(BaseModel):
    state_hash: str
    subject_origin: str
    created_at: datetime
    schema_version: str
    epistemic_diffusion_state: str

    model_config = {"from_attributes": True}


class StateResponse(BaseModel):
    state_hash: str
    narrative: str
    tags: dict[str, Any]
    subject_origin: str
    schema_version: str
    epistemic_diffusion_state: str
    article: str
    provider: str
    created_at: str | None = None


class TimelineItem(BaseModel):
    state_hash: str
    created_at: datetime
    subject_origin: str
    schema_version: str
    epistemic_diffusion_state: str


class StateNeighborsResponse(BaseModel):
    previous: str | None = None
    next: str | None = None


class TagBeforeAfter(BaseModel):
    before: Any
    after: Any


class NarrativeDiff(BaseModel):
    added: list[str]
    removed: list[str]
    changed: list[str]


class StateDiffResponse(BaseModel):
    current_hash: str
    previous_hash: str
    narrative: NarrativeDiff
    tags: dict[str, TagBeforeAfter]


class EventListItem(BaseModel):
    event_id: str
    state_count: int
    origins: list[str]
    latest_created_at: str


class CompareStateItem(BaseModel):
    origin: str
    state_hash: str
    narrative: str
    tags: dict[str, Any]
    epistemic_diffusion_state: str
    narrative_length: int
    t09: dict[str, float]


class CompareResponse(BaseModel):
    event_id: str
    states: list[CompareStateItem]


class TrajectoryPoint(BaseModel):
    state_hash: str
    created_at: str
    origin: str
    x: float
    y: float
    z: float
    diffusion: str


class TrajectoryResponse(BaseModel):
    event_id: str
    points: list[TrajectoryPoint]
