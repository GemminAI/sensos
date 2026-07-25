"""hekb_mcp server entrypoint — stdio transport.

Run with:  PYTHONPATH=. python -m hekb_mcp.server
(matches the existing invocation convention documented in
runtime/DEPLOYMENT.md for runtime/mcp/server.py)

Configuration via environment variables:
  HEKB_RUNTIME_URL          — base URL of hekb-runtime REST API (default http://localhost:8080)
  HEKB_MCP_RESTRICTED_IDS   — comma-separated object ids the Meaning Firewall blocks (default empty)
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from hekb_mcp.client import DEFAULT_BASE_URL, HekbRuntimeClient
from hekb_mcp.observation_engine import ObservationEngine
from hekb_mcp.security import ObservationTokenIssuer, TrustManifestIssuer
from hekb_mcp.tools import NOT_IMPLEMENTED_TOOLS, ToolContext, call_tool

server = Server("hekb-mcp")


def _build_context() -> ToolContext:
    base_url = os.environ.get("HEKB_RUNTIME_URL", DEFAULT_BASE_URL)
    restricted_raw = os.environ.get("HEKB_MCP_RESTRICTED_IDS", "")
    restricted_ids = frozenset(int(x) for x in restricted_raw.split(",") if x.strip())
    client = HekbRuntimeClient(base_url=base_url)
    # ObservationEngine construction is cheap — the sentence-transformers
    # model is loaded lazily on first observe() call, not here.
    return ToolContext(
        client=client,
        token_issuer=ObservationTokenIssuer(),
        trust_issuer=TrustManifestIssuer(),
        restricted_object_ids=restricted_ids,
        observation_engine=ObservationEngine(client=client),
    )


_ctx = _build_context()

_TOOL_SCHEMAS = [
    Tool(
        name="observe",
        description=(
            "RFC-NVS-0100 NVS.SysObserve: project natural-language text into a semantic "
            "coordinate theta (384-dim, paraphrase-multilingual-MiniLM-L12-v2), resolve the "
            "nearest Chart/Attractor, and create a HEXT Observation Object. See "
            "hekb_mcp/docs/EXPERIMENT_REPORT_RFC0100.md for validated accuracy numbers."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "token": {"type": "string", "description": "ObservationToken (requires sys_observe capability)"},
            },
            "required": ["text", "token"],
        },
    ),
    Tool(
        name="get_object",
        description="Fetch a known HEKB object by id (label, potential, energy, curvature, flux_magnitude).",
        inputSchema={
            "type": "object",
            "properties": {
                "object_id": {"type": "integer"},
                "token": {"type": "string", "description": "ObservationToken (requires sys_observe capability)"},
            },
            "required": ["object_id", "token"],
        },
    ),
    Tool(
        name="follow_geodesic",
        description="Compute the shortest topological path between two HEKB objects, subject to Meaning Firewall enforcement.",
        inputSchema={
            "type": "object",
            "properties": {
                "from_object_id": {"type": "integer"},
                "to_object_id": {"type": "integer"},
                "token": {"type": "string", "description": "ObservationToken (requires sys_navigate capability)"},
            },
            "required": ["from_object_id", "to_object_id", "token"],
        },
    ),
    Tool(
        name="estimate_curvature",
        description="Read the stored curvature field of a HEKB object. Not a computed estimate — see tool output note.",
        inputSchema={
            "type": "object",
            "properties": {
                "object_id": {"type": "integer"},
                "token": {"type": "string", "description": "ObservationToken (requires sys_observe capability)"},
            },
            "required": ["object_id", "token"],
        },
    ),
    Tool(
        name="resolve_attractor",
        description=f"NOT IMPLEMENTED — {NOT_IMPLEMENTED_TOOLS['resolve_attractor']}",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="find_pullback",
        description=f"NOT IMPLEMENTED — {NOT_IMPLEMENTED_TOOLS['find_pullback']}",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="get_trust_manifest",
        description="Issue a software-simulated TrustManifest (no TPM/PCR — see hekb_mcp/security.py docstring).",
        inputSchema={
            "type": "object",
            "properties": {"nonce": {"type": "string"}},
            "required": ["nonce"],
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return _TOOL_SCHEMAS


@server.call_tool()
async def call_tool_handler(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    result = call_tool(name, arguments or {}, _ctx)
    return [TextContent(type="text", text=json.dumps(result, default=str))]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
