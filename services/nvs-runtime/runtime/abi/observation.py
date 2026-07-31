"""Observation ABI — the canonical Reality -> R0 entry contract.

This is a client-side model of nvs-kernel's real, existing `/observe` API
(nvs-kernel/docs/API.md, nvs-kernel/docs/OBSERVATION.md). It defines no new
vocabulary of its own: `EventKind` and the request/response shapes mirror the
kernel's published contract exactly, per Greenfield Priority (adopt the
mature, tested ABI rather than inventing a parallel one).

Only the response fields KernelGateway callers need today are modeled.
nvs-kernel's full `/observe` response also carries geometry, belief, field,
trajectory, prediction, and hext blocks — deliberately not modeled yet, since
nothing downstream consumes them in this PR.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class EventKind(StrEnum):
    """nvs-kernel's Observation ABI event taxonomy (docs/OBSERVATION.md)."""

    THOUGHT = "THOUGHT"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"
    OBSERVATION = "OBSERVATION"
    CONTEXT_UPDATE = "CONTEXT_UPDATE"
    NETWORK = "NETWORK"
    SENSOR = "SENSOR"
    USER = "USER"
    SYSTEM = "SYSTEM"


class ObservationEvent(BaseModel):
    """One event inside an /observe request (docs/API.md POST /observe)."""

    step: int
    timestamp_ns: int
    kind: EventKind
    text: str
    source: str | None = None
    agent_id: str | None = None
    tool: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)


class ObserveRequest(BaseModel):
    """The full request body for POST /observe."""

    session_id: str
    events: list[ObservationEvent]
    adapter: str = "generic"
    approval_token: str | None = None
    horizon_steps: int | None = None
    include_vectors: bool = False


class ControlDecision(BaseModel):
    """The `control` block of an /observe response (docs/CONTROL.md)."""

    tier: int
    tier_label: str
    intervention: str
    actionable: bool
    requires_approval: bool
    authorized: bool
    reason: str


class ObserveResponse(BaseModel):
    """The subset of an /observe response this gateway consumes today."""

    session_id: str
    cycle: int
    control: ControlDecision
