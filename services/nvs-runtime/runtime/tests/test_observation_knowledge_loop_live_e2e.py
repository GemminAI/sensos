"""End-to-end verification of the full Observation-Centered Knowledge Loop
against a real, live `hekbd` (no mocks for HEKB) and the real
MeaningMapper/MSR libraries (no mocks possible or needed — neither does
I/O):

    Observation -> MeaningMapper -> Trajectory -> Triangulation
    -> HEKB Evidence -> HEKB Read MCP -> Runtime Context

Skips automatically if no live hekbd is reachable at HEKB_URL_LIVE,
mirroring test_hekb_read_mcp_live_e2e.py's convention. Per ADR-0013,
`store()` (used internally by `request_meaning_triangulation()`) and the
read/relate methods now target the same single `hekb_url` by default, so
writes and reads in this test hit the same real server and the same real
data.
"""

import os

import pytest
from runtime.core.config import Settings
from runtime.gateway.hekb_client import HekbClient
from runtime.models.enums import AgentProvider
from runtime.models.schemas import AgentCreate, SessionCreate
from runtime.services.agent_service import AgentService
from runtime.services.capability_decision import EvidenceStatus, RuntimeOutcome, request_meaning_triangulation
from runtime.services.meaning_trajectory import build_hext_observation
from runtime.services.meaning_triangulation import TriangulationInput
from runtime.services.runtime_context import get_triangulation_context
from runtime.services.session_service import SessionService

LIVE_HEKBD_URL = os.environ.get("HEKB_URL_LIVE", "http://127.0.0.1:8100")


def _observations(text: str, prefix: str) -> list[dict]:
    return [
        build_hext_observation(
            observation_id=f"{prefix}-{i:04d}",
            text=text,
            state_hash="a" * 64,
            sealed_at=f"2026-08-18T05:00:{i:02d}Z",
        )
        for i in range(8)
    ]


async def _live_hekb() -> HekbClient | None:
    client = HekbClient(Settings(hekb_url=LIVE_HEKBD_URL))
    if not await client.health_check():
        return None
    return client


async def test_full_observation_knowledge_loop_against_live_hekbd(db_session, fake_redis):
    hekb = await _live_hekb()
    if hekb is None:
        pytest.skip(f"no live hekbd reachable at {LIVE_HEKBD_URL}")

    agent = AgentService().create(db_session, AgentCreate(provider=AgentProvider.CUSTOM, model="e2e-loop"))
    db_session.flush()
    session = SessionService().create(db_session, SessionCreate())
    db_session.flush()

    # Two real observation paths for the same claimed meaning: a repeated
    # stable text and its replay under a different path label — the same
    # "identical input replay" leg used in the unit tests, now run against
    # a real HEKB, not a fake.
    text = "the runtime is observing a stable meaning across independent paths"
    inputs = [
        TriangulationInput(path_id="loop-a", observations=_observations(text, "loop-a"), method="repeated_stable"),
        TriangulationInput(path_id="loop-b", observations=_observations(text, "loop-b"), method="replay"),
    ]

    # Triangulation -> HEKB Evidence (real writes: 2 trajectories + 1
    # summary + 2 DERIVES morphisms, all against the live hekbd).
    result = await request_meaning_triangulation(
        db_session, session.session_id, agent.agent_id, inputs, divergence_epsilon=1e-6, hekb=hekb
    )

    assert result.outcome == RuntimeOutcome.SUCCESS
    assert result.invocation_result["state"] == "STABLE"
    assert result.evidence_status == EvidenceStatus.PERSISTED
    assert result.evidence_object_id is not None
    assert len(result.evidence_object_id) == 64  # a real hekbd content address, not fabricated

    # HEKB Read MCP -> Runtime Context: read the same evidence back out of
    # the same live HEKB the write just went into.
    context = await get_triangulation_context(result.evidence_object_id, hekb=hekb)

    assert context["found"] is True
    assert context["triangulation"]["labels"]["state"] == "STABLE"
    assert context["provenance"]["session_id"] == str(session.session_id)
    # both per-path trajectories come back as DERIVES-linked related evidence
    assert len(context["related_evidence"]) == 2
    for related in context["related_evidence"]:
        assert related["object"]["labels"]["value_kind"] == "measured"

    # Confirm via a genuinely independent read (nvs_hekb_stats-equivalent
    # client call) that the writes are real and durable on the server, not
    # an artifact of the same in-process call.
    fresh_read = await hekb.get_object(result.evidence_object_id)
    assert fresh_read is not None
    assert fresh_read["labels"]["triangulation_id"] == result.invocation_result["triangulation_id"]
