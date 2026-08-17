"""End-to-end verification of the HEKB Read MCP tools against a real, live
`hekbd` process (GemminAI/hekb's C++ server) — no mocks. Skips automatically
if no live hekbd is reachable at HEKB_QUERY_URL_LIVE, so it never blocks the
regular unit test run.

Discovered live against a real hekbd while writing this test (not assumed):
hekbd's `POST /v1/objects` returns `{"id": "..."}`, NOT the
`{"object_id","hash","timestamp"}` shape `HekbClient.store()` expects —
that shape belongs to the *Python* hekb-api (`hekb_url`), a different
server with an overlapping but non-identical contract (see
runtime/core/config.py's `hekb_query_url` docstring). So this test writes
seed objects via `call_query()` directly, reading hekbd's real `id` key,
rather than through `store()`.
"""

import os
from uuid import uuid4

import pytest
from runtime.core.config import Settings
from runtime.gateway.hekb_client import HekbClient

LIVE_HEKBD_URL = os.environ.get("HEKB_QUERY_URL_LIVE", "http://127.0.0.1:8100")


async def _live_client() -> HekbClient | None:
    client = HekbClient(Settings(hekb_url=LIVE_HEKBD_URL, hekb_query_url=LIVE_HEKBD_URL))
    if not await client.health_check():
        return None
    return client


async def test_hekb_read_mcp_tools_against_live_hekbd():
    client = await _live_client()
    if client is None:
        pytest.skip(f"no live hekbd reachable at {LIVE_HEKBD_URL}")

    stats_before = await client.stats()

    # HEKB is content-addressed (put is idempotent — identical content always
    # yields the same id and does not grow the store), so a unique label per
    # test run is required for the count-delta assertions below to mean
    # anything; a fixed label across repeated runs would legitimately produce
    # zero growth, which is correct HEKB behavior, not something to defeat.
    run_id = uuid4().hex
    obj_a = await client.call_query(
        "POST",
        "/v1/objects",
        json={"kind": "OBSERVATION", "vector": [1.0, 0.0, 0.0], "attributes": {}, "labels": {"run": run_id, "test": "live-e2e-a"}},
    )
    obj_b = await client.call_query(
        "POST",
        "/v1/objects",
        json={"kind": "OBSERVATION", "vector": [0.0, 1.0, 0.0], "attributes": {}, "labels": {"run": run_id, "test": "live-e2e-b"}},
    )
    id_a, id_b = obj_a["id"], obj_b["id"]
    assert len(id_a) == 64 and len(id_b) == 64  # real content addresses, not fabricated ids

    # get_object — real read of what was just written
    fetched = await client.get_object(id_a)
    assert fetched is not None
    assert fetched["labels"]["test"] == "live-e2e-a"

    # get_object — a genuinely absent id returns None, not an exception
    absent = await client.get_object("f" * 64)
    assert absent is None

    # nearest — real cosine search over the real store
    matches = await client.nearest([1.0, 0.0, 0.0], limit=5)
    assert any(m["id"] == id_a for m in matches)

    # relate — real morphism write (the one write tool in this tranche)
    morphism_id = await client.relate(id_a, id_b, "SUPPORTS", weight=0.25)
    assert len(morphism_id) == 64

    # neighbours — real BFS over the real morphism just created
    neighbours = await client.neighbours(id_a, depth=1)
    assert any(n["id"] == id_b for n in neighbours)

    # geodesic — real Dijkstra over the real morphism just created
    path = await client.geodesic(id_a, id_b)
    assert path["found"] is True
    assert id_b in path["objects"]

    # stats — real counts, strictly increased by the two objects + one morphism above
    stats_after = await client.stats()
    assert stats_after["objects"] >= stats_before.get("objects", 0) + 2
    assert stats_after["morphisms"] >= stats_before.get("morphisms", 0) + 1
