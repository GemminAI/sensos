"""MCP tool handlers — RFC-NVS42 v0.3 §9."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from runtime.api.deps import db_session
from runtime.models.enums import AgentProvider, RuntimeEventType
from runtime.models.schemas import AgentCreate, EventIngestRequest, ExperimentType, SessionCreate
from runtime.services.agent_service import AgentService
from runtime.services.event_service import EventService
from runtime.services.session_service import SessionService

LAYER3_STUBS = {
    "nvs_forecast_transition": "RFC-NVS30",
    "nvs_check_integrity": "RFC-NVS31",
    "nvs_get_alignment_profile": "RFC-NVS32",
    "nvs_check_boundary_status": "RFC-NVS33",
}

_agent_service = AgentService()
_session_service = SessionService()
_event_service = EventService()


def stub_response(tool_name: str) -> dict[str, Any]:
    return {"status": "NOT_IMPLEMENTED", "rfc": LAYER3_STUBS[tool_name]}


def nvs_register_agent(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = AgentProvider(arguments.get("provider", "custom"))
    data = AgentCreate(
        display_name=arguments.get("display_name"),
        provider=provider,
        model=arguments["model"],
        capabilities=arguments.get("capabilities", []),
        metadata=arguments.get("metadata", {}),
    )
    with db_session() as db:
        result = _agent_service.create(db, data)
    return result.model_dump(mode="json")


def nvs_create_session(arguments: dict[str, Any]) -> dict[str, Any]:
    participants = [UUID(p) for p in arguments.get("participants", [])]
    data = SessionCreate(
        label=arguments.get("label"),
        participants=participants,
        options=arguments.get("options", {}),
    )
    with db_session() as db:
        result = _session_service.create(db, data)
    return result.model_dump(mode="json")


def nvs_emit_sep_event(arguments: dict[str, Any]) -> dict[str, Any]:
    session_id = UUID(arguments["session_id"])
    agent_id = UUID(arguments["agent_id"])
    runtime_type = arguments.get("runtime_event_type", "sep.excitation")
    sep_inner = arguments["sep_payload"]

    request = EventIngestRequest(
        event_type=RuntimeEventType(runtime_type),
        agent_id=agent_id,
        experiment_id=UUID(arguments["experiment_id"]) if arguments.get("experiment_id") else None,
        source_provider=arguments.get("source_provider"),
        source_model=arguments.get("source_model"),
        parent_event_id=UUID(arguments["parent_event_id"]) if arguments.get("parent_event_id") else None,
        payload=sep_inner,
    )
    with db_session() as db:
        result = _event_service.ingest(db, session_id, request)
    return result.model_dump(mode="json")


def nvs_query_events(arguments: dict[str, Any]) -> dict[str, Any]:
    session_id = UUID(arguments["session_id"])
    limit = int(arguments.get("limit", 100))
    offset = int(arguments.get("offset", 0))
    with db_session() as db:
        events = _event_service.list_events(db, session_id, limit=limit, offset=offset)
    return {"events": [e.model_dump(mode="json") for e in events], "count": len(events)}
