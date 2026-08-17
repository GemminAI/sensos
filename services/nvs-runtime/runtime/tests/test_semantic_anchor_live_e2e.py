"""End-to-end verification of the GPT-OSS Semantic Anchor capability
against a real, live Ollama instance running the real `gpt-oss:20b` model
(pulled locally for this cycle — Reality Audit found no GPT-OSS
integration or model anywhere in this system beforehand; see
docs/adr/ADR-0014-gpt-oss-semantic-anchor.md), and a real, live `hekbd`
(no mocks anywhere in this file).

Skips automatically if Ollama is unreachable or `MODEL_ID` is not present
locally, mirroring this suite's other live-test conventions.
"""

import os

import pytest
from runtime.core.config import Settings
from runtime.gateway.hekb_client import HekbClient
from runtime.gateway.ollama_client import OllamaClient
from runtime.models.enums import AgentProvider
from runtime.models.schemas import AgentCreate, SessionCreate
from runtime.services.agent_service import AgentService
from runtime.services.capability_decision import EvidenceStatus, RuntimeOutcome, request_semantic_anchor_triangulation
from runtime.services.runtime_context import get_triangulation_context
from runtime.services.semantic_anchor import request_semantic_anchor
from runtime.services.session_service import SessionService

MODEL_ID = os.environ.get("SEMANTIC_ANCHOR_MODEL_ID_LIVE", "gpt-oss:20b")
LIVE_HEKBD_URL = os.environ.get("HEKB_URL_LIVE", "http://127.0.0.1:8100")


async def _live_ollama() -> OllamaClient | None:
    client = OllamaClient()
    if not await client.health_check():
        return None
    if await client.digest_of(MODEL_ID) is None:
        return None
    return client


async def _live_hekb() -> HekbClient | None:
    client = HekbClient(Settings(hekb_url=LIVE_HEKBD_URL))
    if not await client.health_check():
        return None
    return client


async def test_gpt_oss_determinism_live():
    """DETERMINISM (cycle instructions §3): same input, same model_id,
    same prompt_version, fixed temperature/seed -> A1 == A2 on a REAL
    GPT-OSS generation. Only temperature/seed are claimed fixed (this
    module's own empirically-verified controllable knobs) -- nothing about
    reasoning effort or other gpt-oss-specific parameters is asserted."""
    ollama = await _live_ollama()
    if ollama is None:
        pytest.skip(f"no live Ollama with {MODEL_ID} pulled")

    text = "the runtime is observing a stable meaning across independent paths"
    a1 = await request_semantic_anchor(
        text, observation_id="det-1", model_id=MODEL_ID, prompt_version="v1", client=ollama
    )
    a2 = await request_semantic_anchor(
        text, observation_id="det-2", model_id=MODEL_ID, prompt_version="v1", client=ollama
    )

    assert a1.structured_result == a2.structured_result  # A1 == A2, the real model's real output
    assert a1.anchor_id == a2.anchor_id  # content-addressed identity agrees
    assert a1.model_revision is not None  # a real digest, not None/placeholder
    assert a1.model_revision == a2.model_revision


async def test_semantic_anchor_full_chain_live_e2e(db_session, fake_redis):
    """Observation -> GPT-OSS Semantic Anchor -> Triangulation (vs a direct
    MeaningMapper path) -> HEKB Evidence -> HEKB Read MCP -> Runtime
    Context, against real Ollama/gpt-oss:20b and real hekbd throughout."""
    ollama = await _live_ollama()
    hekb = await _live_hekb()
    if ollama is None or hekb is None:
        pytest.skip(f"no live Ollama+{MODEL_ID} and/or hekbd reachable")

    agent = AgentService().create(db_session, AgentCreate(provider=AgentProvider.CUSTOM, model="e2e-anchor"))
    db_session.flush()
    session = SessionService().create(db_session, SessionCreate())
    db_session.flush()

    result = await request_semantic_anchor_triangulation(
        db_session,
        session.session_id,
        agent.agent_id,
        "the runtime is observing a stable meaning across independent paths",
        observation_id="live-anchor-1",
        model_id=MODEL_ID,
        divergence_epsilon=1000.0,  # generous: this test proves the chain wires up, not a specific verdict
        ollama=ollama,
        hekb=hekb,
    )

    assert result.outcome == RuntimeOutcome.SUCCESS
    assert result.invocation_result["model_id"] == MODEL_ID
    assert len(result.invocation_result["structured_result"]["summary"]) > 0  # a real, non-empty completion
    assert result.evidence_status == EvidenceStatus.PERSISTED
    assert result.evidence_object_id is not None
    assert len(result.evidence_object_id) == 64  # a real hekbd content address

    # Runtime Context: read the same evidence back out of the same live HEKB
    context = await get_triangulation_context(result.evidence_object_id, hekb=hekb)
    assert context["found"] is True
    # both the direct trajectory and the anchor trajectory come back linked,
    # each a real, measured StabilizedTrajectory. Distinctness is checked by
    # HEKB object_id (content-addressed over the real centroid), not MSR's
    # own `trajectory_id` -- that field is `f"traj-{frame_id}-{step_index}"`
    # (msr/stability.py), scoped to one MeaningSpaceRuntime instance, so two
    # independent runtimes that each stabilize at their own first step
    # legitimately produce the SAME trajectory_id even though they are
    # different objects with different centroids -- confirmed live, not
    # assumed, while writing this test.
    assert len(context["related_evidence"]) == 2
    object_ids = set()
    for related in context["related_evidence"]:
        labels = related["object"]["labels"]
        assert labels["value_kind"] == "measured"
        assert labels["session_id"] == str(session.session_id)
        object_ids.add(related["object_id"])
    assert len(object_ids) == 2  # two genuinely distinct HEKB objects, not the same one twice

    # the anchor object itself is independently fetchable and DERIVES-linked
    anchor_object_id = result.invocation_result["anchor_object_id"]
    anchor_context = await get_triangulation_context(anchor_object_id, hekb=hekb)
    # get_triangulation_context works on any object id, not only summaries --
    # the anchor object itself has one outgoing neighbour: its own trajectory
    assert anchor_context["found"] is True
    assert anchor_context["triangulation"]["labels"]["model_id"] == MODEL_ID
    assert len(anchor_context["related_evidence"]) == 1
