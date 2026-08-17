"""Real MCP wire-protocol verification: spawns the actual
`runtime.mcp.server` subprocess over stdio and drives it with the official
`mcp` client SDK (JSON-RPC framing, real `initialize` handshake) — not a
Python-level function call. This is what an MCP client (Claude Desktop,
MCP Inspector, ...) actually does; unlike the module-level tests in
test_mcp_tools.py, it proves the protocol layer itself, not just the tool
handlers.

Skips automatically if hekbd is not reachable at HEKB_QUERY_URL_LIVE (the
`nvs_hekb_stats` call needs a live backend to return a real, non-error
result) — mirrors the skip convention used elsewhere in this test suite.
"""

import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

LIVE_HEKBD_URL = os.environ.get("HEKB_QUERY_URL_LIVE", "http://127.0.0.1:8100")


async def _reachable(url: str) -> bool:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{url}/health")
            return response.status_code == 200
    except httpx.TransportError:
        return False


async def test_mcp_server_real_wire_protocol_round_trip():
    if not await _reachable(LIVE_HEKBD_URL):
        pytest.skip(f"no live hekbd reachable at {LIVE_HEKBD_URL}")

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "runtime.mcp.server"],
        env={"HEKB_QUERY_URL": LIVE_HEKBD_URL, "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            # Real negotiated protocol version, not asserted against a
            # fixed string — this SDK (mcp==1.9.0) only knows 2025-03-26,
            # see docs/audit/MCP_COMPLIANCE_AUDIT_20260818.md item 1.
            assert init.protocolVersion
            assert init.capabilities.tools is not None
            assert init.capabilities.resources is None  # honestly not offered
            assert init.capabilities.prompts is None  # honestly not offered

            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            for expected in (
                "nvs_hekb_get",
                "nvs_hekb_nearest",
                "nvs_hekb_neighbours",
                "nvs_hekb_geodesic",
                "nvs_hekb_stats",
                "nvs_hekb_relate",
            ):
                assert expected in names

            stats_result = await session.call_tool("nvs_hekb_stats", {})
            assert stats_result.isError is False
            assert "objects" in stats_result.content[0].text

            absent_result = await session.call_tool("nvs_hekb_get", {"object_id": "f" * 64})
            assert absent_result.isError is False
            assert '"found": false' in absent_result.content[0].text
