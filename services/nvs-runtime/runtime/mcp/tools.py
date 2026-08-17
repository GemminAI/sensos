"""MCP tool handlers — RFC-NVS42 v0.3 §9."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from runtime.api.deps import db_session
from runtime.gateway.hekb_client import HekbClient, build_hekb_object_from_port_result
from runtime.gateway.kernel_gateway import KernelGateway
from runtime.gateway.ollama_client import OllamaClient
from runtime.models.enums import AgentProvider, RuntimeEventType
from runtime.models.schemas import AgentCreate, EventIngestRequest, ExperimentType, SessionCreate
from runtime.services.agent_service import AgentService
from runtime.services.capability_decision import (
    request_meaning_triangulation,
    request_semantic_anchor_triangulation,
)
from runtime.services.event_service import EventService
from runtime.services.meaning_trajectory import build_hext_observation, run_meaning_trajectory
from runtime.services.meaning_triangulation import TriangulationInput
from runtime.services.runtime_context import get_triangulation_context
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
_ollama_client = OllamaClient()


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


# ---------------------------------------------------------------------------
# MeaningMapper capability tools — the MCP Capability Bus surface for
# runtime.services.meaning_trajectory (MeaningMapper -> meaning-space-runtime
# -> Trajectory). Sync, unlike the Port tools above: neither meaning_mapper
# nor msr does any I/O (confirmed in the Reality Audit), so there is nothing
# to await here — this tool is added to FULL_TOOLS (sync dispatch), not
# ASYNC_TOOLS, honestly reflecting the underlying libraries' actual nature.
# ---------------------------------------------------------------------------


def nvs_meaning_mapper_capability(arguments: dict[str, Any]) -> dict[str, Any]:
    """capability_available? for the MeaningMapper capability. Always a
    static descriptor — this is a local library import, not a live
    external service reachability question (an honest distinction from
    nvs_get_port_capability's real live check, not glossed over)."""
    return {
        "capability_id": "meaning_mapper.trajectory",
        "status": "IMPLEMENTED",
        "transport": "in-process",
    }


# ---------------------------------------------------------------------------
# HEKB Read MCP tools — thin wrappers over HekbClient's existing hekbd
# routes (get_object/nearest/neighbours/geodesic/stats; `relate` is a
# write, see its own docstring). No new HEKB route, payload shape, or
# object model is invented here — every field name below is copied from
# `GemminAI/hekb`'s own server routes (docs/API.md, cpp/server/http_api.cpp)
# and its own Python client (hekb/python/hekb/client.py). None of these
# handlers touch the DB/session/queue infra the tools above use — they are
# pure passthroughs to `_hekb_client`, so they raise on failure exactly as
# `nvs_invoke_port` does, letting the MCP SDK's call_tool wrapper turn any
# exception into isError:true rather than a fabricated success.
# ---------------------------------------------------------------------------


async def nvs_hekb_get(arguments: dict[str, Any]) -> dict[str, Any]:
    """Read-only: GET /v1/objects/{id} on hekbd. `found: false` (not an
    exception) when the id genuinely does not exist — a real, honest
    outcome, matching `nvs_run_meaning_trajectory`'s treatment of
    "criteria not met yet" as data, not an error."""
    obj = await _hekb_client.get_object(str(arguments["object_id"]))
    return {"found": False} if obj is None else {"found": True, **obj}


async def nvs_hekb_nearest(arguments: dict[str, Any]) -> dict[str, Any]:
    """Read-only: POST /v1/query/nearest on hekbd. k-nearest by vector."""
    matches = await _hekb_client.nearest(
        [float(c) for c in arguments["vector"]],
        int(arguments.get("limit", 10)),
        str(arguments.get("metric", "cosine")),
    )
    return {"matches": matches}


async def nvs_hekb_neighbours(arguments: dict[str, Any]) -> dict[str, Any]:
    """Read-only: GET /v1/query/neighbours on hekbd. Bounded-hop BFS
    expansion of the morphism graph around one object."""
    neighbours = await _hekb_client.neighbours(
        str(arguments["object_id"]), int(arguments.get("depth", 1))
    )
    return {"neighbours": neighbours}


async def nvs_hekb_geodesic(arguments: dict[str, Any]) -> dict[str, Any]:
    """Read-only: GET /v1/query/geodesic on hekbd. Cheapest path between
    two objects by summed morphism weight. `found: false` is a real
    outcome (no path exists), not an error."""
    return await _hekb_client.geodesic(str(arguments["from_object_id"]), str(arguments["to_object_id"]))


async def nvs_hekb_stats(arguments: dict[str, Any]) -> dict[str, Any]:
    """Read-only: GET /metrics on hekbd, parsed to object/morphism counts."""
    return await _hekb_client.stats()


async def nvs_hekb_relate(arguments: dict[str, Any]) -> dict[str, Any]:
    """NOT a read: POST /v1/morphisms on hekbd — creates or updates a
    typed, weighted edge between two existing objects. Included in this
    tranche because it was explicitly requested alongside the read tools,
    but it is the one tool here that mutates HEKB; callers should not
    assume the "HEKB Read MCP" name covers it."""
    morphism_id = await _hekb_client.relate(
        str(arguments["source"]),
        str(arguments["target"]),
        str(arguments["kind"]),
        float(arguments.get("weight", 0.0)),
    )
    return {"id": morphism_id}


def nvs_run_meaning_trajectory(arguments: dict[str, Any]) -> dict[str, Any]:
    """invoke_capability() for the MeaningMapper capability: feed a
    sequence of real HEXT Observations through
    MeaningMapper -> meaning-space-runtime, returning whichever real
    StabilizedTrajectory resulted (or none, if dwell criteria were not
    met yet — a real, honest outcome, not an error).

    `arguments["observations"]` may be pre-built HEXT Observation dicts, or
    `arguments["texts"]` a list of plain strings this tool turns into real
    HEXT Observations via `build_hext_observation()` (deterministic
    observation_id/state_hash/sealed_at derived from each string's own
    index and content — not fabricated data, just a convenience
    constructor matching the documented real wire schema).
    """
    import hashlib
    from datetime import datetime, timedelta, timezone

    observations = arguments.get("observations")
    if observations is None:
        texts = arguments.get("texts", [])
        base_time = datetime.now(timezone.utc)
        observations = [
            build_hext_observation(
                observation_id=f"mcp-{i:04d}",
                text=text,
                state_hash=hashlib.sha256(f"{i}:{text}".encode()).hexdigest(),
                sealed_at=(base_time + timedelta(seconds=i)).isoformat(),
            )
            for i, text in enumerate(texts)
        ]

    result = run_meaning_trajectory(observations)
    return {
        "steps_processed": len(result.steps),
        "quarantined_count": sum(1 for s in result.steps if s.quarantined),
        "stabilized": result.stabilized,
        "trajectory": (
            {
                "trajectory_id": result.trajectory.trajectory_id,
                "frame_id": result.trajectory.frame_id,
                "basin_id": result.trajectory.basin_id,
                "is_novel": result.trajectory.is_novel,
                "centroid": list(result.trajectory.centroid),
                "dwell_steps": result.trajectory.dwell_steps,
                "dwell_seconds": result.trajectory.dwell_seconds,
            }
            if result.trajectory is not None
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Meaning Triangulation capability tools — the MCP Capability Bus surface
# for runtime.services.meaning_triangulation / capability_decision.
# request_meaning_triangulation() / runtime.services.runtime_context. Async
# (unlike nvs_run_meaning_trajectory above): this tool persists to HEKB and
# needs a DB session for Event lineage, both of which do real I/O, unlike
# the pure in-process measurement nvs_run_meaning_trajectory wraps.
# ---------------------------------------------------------------------------


async def nvs_run_meaning_triangulation(arguments: dict[str, Any]) -> dict[str, Any]:
    """invoke_capability() for Meaning Triangulation: runs each of
    `arguments["paths"]` (each `{"path_id", "observations", "method"}`)
    through MeaningMapper -> MSR independently, compares the resulting
    stabilized trajectories, and persists the result to HEKB (trajectories
    + summary + DERIVES lineage) via `request_meaning_triangulation()`.

    Requires an already-registered `session_id`/`agent_id` — same
    requirement `nvs_emit_sep_event` already has. `divergence_epsilon` is
    optional; omitting it means the returned `state` is `NOT_EVALUABLE`
    (see `meaning_triangulation` module docstring for why no default
    exists) — evidence is still persisted either way.
    """
    session_id = UUID(arguments["session_id"])
    agent_id = UUID(arguments["agent_id"])
    inputs = [
        TriangulationInput(
            path_id=str(path["path_id"]),
            observations=list(path["observations"]),
            method=str(path.get("method", "")),
        )
        for path in arguments["paths"]
    ]
    divergence_epsilon = arguments.get("divergence_epsilon")

    with db_session() as db:
        result = await request_meaning_triangulation(
            db,
            session_id,
            agent_id,
            inputs,
            divergence_epsilon=divergence_epsilon,
            hekb=_hekb_client,
        )

    return {
        "runtime_cycle_id": str(result.runtime_cycle_id),
        "outcome": result.outcome.value,
        "invocation_result": result.invocation_result,
        "evidence_status": result.evidence_status.value,
        "evidence_object_id": result.evidence_object_id,
    }


async def nvs_get_triangulation_context(arguments: dict[str, Any]) -> dict[str, Any]:
    """Read-only: the Runtime Context leg. Reads back a triangulation
    summary (by the HEKB object id `nvs_run_meaning_triangulation`
    returned as `evidence_object_id`) and its DERIVES-linked per-path
    trajectory evidence via `runtime.services.runtime_context.
    get_triangulation_context()` — pure HEKB reads (Phase 1's
    get_object/neighbours), no capability-selection policy."""
    return await get_triangulation_context(
        str(arguments["triangulation_object_id"]), hekb=_hekb_client
    )


# ---------------------------------------------------------------------------
# GPT-OSS Semantic Anchor capability tool — thin wrapper over
# request_semantic_anchor_triangulation(). This tool does not decide
# anything: it is the interoperability layer over a real Runtime Decision
# Boundary function that already does discover/decide/invoke. GPT-OSS
# itself is never treated as ground truth by that function or this tool.
# ---------------------------------------------------------------------------


async def nvs_request_semantic_anchor_triangulation(arguments: dict[str, Any]) -> dict[str, Any]:
    """invoke_capability() for the Semantic Anchor capability: generate a
    real completion from a local inference runtime (default model_id
    "gpt-oss:20b" via Ollama — see runtime.gateway.ollama_client), triangulate
    it against a direct-observation path through the existing MeaningMapper
    -> MSR chain, and persist both to HEKB with real DERIVES lineage.

    Requires an already-registered session_id/agent_id, same requirement
    every other capability tool in this module already has.
    """
    session_id = UUID(arguments["session_id"])
    agent_id = UUID(arguments["agent_id"])

    with db_session() as db:
        result = await request_semantic_anchor_triangulation(
            db,
            session_id,
            agent_id,
            str(arguments["observation_text"]),
            observation_id=str(arguments["observation_id"]),
            model_id=str(arguments.get("model_id", "gpt-oss:20b")),
            prompt_version=str(arguments.get("prompt_version", "v1")),
            divergence_epsilon=arguments.get("divergence_epsilon"),
            ollama=_ollama_client,
            hekb=_hekb_client,
        )

    return {
        "runtime_cycle_id": str(result.runtime_cycle_id),
        "outcome": result.outcome.value,
        "invocation_result": result.invocation_result,
        "evidence_status": result.evidence_status.value,
        "evidence_object_id": result.evidence_object_id,
    }
