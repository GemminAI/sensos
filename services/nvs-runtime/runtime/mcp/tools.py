"""MCP tool handlers — RFC-NVS42 v0.3 §9."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from runtime.api.deps import db_session
from runtime.gateway.hekb_client import HekbClient, build_hekb_object_from_port_result
from runtime.gateway.kernel_gateway import KernelGateway
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
_kernel_gateway = KernelGateway()
_hekb_client = HekbClient()


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


# ---------------------------------------------------------------------------
# 38-Port capability tools — the MCP Capability Bus surface for the
# already-real, already-verified Port invoke contract. Async (unlike the
# tools above, which use sync SQLAlchemy sessions), because
# KernelGateway/HekbClient are httpx-async clients — see server.py's
# ASYNC_TOOLS dispatch. No new invocation logic, no new capability schema,
# no automatic trigger: these wrap KernelGateway.get_port_capability() /
# invoke_port() and the existing Port-Evidence-to-HEKB pipeline exactly as
# already implemented and tested (test_kernel_gateway.py, test_forward_worker.py).
# ---------------------------------------------------------------------------


async def nvs_get_port_capability(arguments: dict[str, Any]) -> dict[str, Any]:
    """capability_available? — live GET /ports/{port_id}_Port, nvs-kernel's
    own capability descriptor schema. Read-only, no invocation."""
    return await _kernel_gateway.get_port_capability(arguments["port_id"])


async def nvs_invoke_port(arguments: dict[str, Any]) -> dict[str, Any]:
    """invoke_capability() — the existing, already-verified real 38-Port
    invoke contract (POST /ports/{port_id}_Port/invoke)."""
    return await _kernel_gateway.invoke_port(arguments["port_id"], arguments.get("body", {}))


async def nvs_persist_port_evidence(arguments: dict[str, Any]) -> dict[str, Any]:
    """record_result() — invoke a Port and persist its raw result to HEKB
    as Evidence. Same logic as ForwardWorker.persist_port_evidence(); called
    directly here (not via a ForwardWorker instance) since this MCP tool
    has no queue/DB session of its own to route one through.

    `session_id`/`cycle` are optional, exactly as in
    ForwardWorker.persist_port_evidence() and build_hekb_object_from_port_result().
    """
    port_id = arguments["port_id"]
    body = arguments.get("body", {})
    port_result = await _kernel_gateway.invoke_port(port_id, body)
    hekb_object = build_hekb_object_from_port_result(
        port_id,
        port_result,
        session_id=arguments.get("session_id"),
        cycle=arguments.get("cycle"),
    )
    return await _hekb_client.store(hekb_object)
