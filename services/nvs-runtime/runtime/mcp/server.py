"""MCP server entrypoint — stdio transport."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from runtime.mcp.tools import (
    LAYER3_STUBS,
    nvs_create_session,
    nvs_emit_sep_event,
    nvs_get_port_capability,
    nvs_invoke_port,
    nvs_meaning_mapper_capability,
    nvs_persist_port_evidence,
    nvs_query_events,
    nvs_register_agent,
    nvs_run_meaning_trajectory,
    stub_response,
)

server = Server("nvs-runtime")

FULL_TOOLS = {
    "nvs_register_agent": nvs_register_agent,
    "nvs_create_session": nvs_create_session,
    "nvs_emit_sep_event": nvs_emit_sep_event,
    "nvs_query_events": nvs_query_events,
    "nvs_meaning_mapper_capability": nvs_meaning_mapper_capability,
    "nvs_run_meaning_trajectory": nvs_run_meaning_trajectory,
}

#: 38-Port capability tools are async (KernelGateway/HekbClient are
#: httpx-async clients) — dispatched separately from FULL_TOOLS, which are
#: sync (SQLAlchemy). See call_tool() below.
ASYNC_TOOLS = {
    "nvs_get_port_capability": nvs_get_port_capability,
    "nvs_invoke_port": nvs_invoke_port,
    "nvs_persist_port_evidence": nvs_persist_port_evidence,
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    tools = [
        Tool(
            name="nvs_register_agent",
            description="Register an agent in the NVS Runtime registry",
            inputSchema={
                "type": "object",
                "properties": {
                    "provider": {"type": "string"},
                    "model": {"type": "string"},
                    "display_name": {"type": "string"},
                    "capabilities": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["provider", "model"],
            },
        ),
        Tool(
            name="nvs_create_session",
            description="Create a new runtime session",
            inputSchema={
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "participants": {"type": "array", "items": {"type": "string"}},
                },
            },
        ),
        Tool(
            name="nvs_emit_sep_event",
            description="Emit a SEP event (RFC-NVS16) through the runtime envelope",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "agent_id": {"type": "string"},
                    "runtime_event_type": {"type": "string"},
                    "sep_payload": {"type": "object"},
                    "experiment_id": {"type": "string"},
                    "source_provider": {"type": "string"},
                    "source_model": {"type": "string"},
                },
                "required": ["session_id", "agent_id", "sep_payload"],
            },
        ),
        Tool(
            name="nvs_query_events",
            description="Query persisted events for a session",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
                "required": ["session_id"],
            },
        ),
        Tool(
            name="nvs_get_port_capability",
            description=(
                "Get live capability metadata for one of the 38 fixed, "
                "read-only observation Ports (GET /ports/{port_id}_Port)"
            ),
            inputSchema={
                "type": "object",
                "properties": {"port_id": {"type": "string"}},
                "required": ["port_id"],
            },
        ),
        Tool(
            name="nvs_invoke_port",
            description="Invoke one of the 38 fixed, read-only observation Ports",
            inputSchema={
                "type": "object",
                "properties": {
                    "port_id": {"type": "string"},
                    "body": {"type": "object"},
                },
                "required": ["port_id", "body"],
            },
        ),
        Tool(
            name="nvs_persist_port_evidence",
            description="Invoke a Port and persist its raw result to HEKB as Evidence",
            inputSchema={
                "type": "object",
                "properties": {
                    "port_id": {"type": "string"},
                    "body": {"type": "object"},
                    "session_id": {"type": "string"},
                    "cycle": {"type": "integer"},
                },
                "required": ["port_id", "body"],
            },
        ),
        Tool(
            name="nvs_meaning_mapper_capability",
            description="Get capability metadata for the MeaningMapper -> Trajectory capability",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="nvs_run_meaning_trajectory",
            description=(
                "Feed HEXT Observations through MeaningMapper -> meaning-space-runtime, "
                "returning a real StabilizedTrajectory if dwell criteria were met"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "observations": {"type": "array", "items": {"type": "object"}},
                    "texts": {"type": "array", "items": {"type": "string"}},
                },
            },
        ),
    ]
    for name in LAYER3_STUBS:
        tools.append(
            Tool(
                name=name,
                description=f"Layer 3 stub — {LAYER3_STUBS[name]}",
                inputSchema={"type": "object", "properties": {}},
            )
        )
    return tools


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name in LAYER3_STUBS:
        result = stub_response(name)
    elif name in ASYNC_TOOLS:
        result = await ASYNC_TOOLS[name](arguments or {})
    elif name in FULL_TOOLS:
        result = FULL_TOOLS[name](arguments or {})
    else:
        result = {"error": "UNKNOWN_TOOL", "tool": name}
    return [TextContent(type="text", text=json.dumps(result, default=str))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
