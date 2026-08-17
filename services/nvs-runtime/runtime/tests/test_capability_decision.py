"""Tests for the Runtime Decision Boundary (runtime/services/capability_decision.py).

Mocked at the KernelGateway/HekbClient boundary — same convention as
test_mcp_tools.py's Port-capability tests and test_forward_worker.py's
_FakeGateway/_FakeHekb. Real capability descriptors/results used as fixture
data are the exact ones captured live in prior cycles (P04:
core_c04_hext_closure_verifier), not invented.
"""

from __future__ import annotations

import inspect

from runtime.gateway.http_pool import RetryExhaustedError
from runtime.models.enums import AgentProvider, RuntimeEventType
from runtime.models.schemas import AgentCreate, SessionCreate
from runtime.services.agent_service import AgentService
from runtime.services.capability_decision import (
    CapabilityRequest,
    EvidenceStatus,
    RuntimeOutcome,
    request_capability,
    request_meaning_trajectory,
    request_meaning_triangulation,
)
from runtime.services.event_service import EventService
from runtime.services.meaning_trajectory import build_hext_observation
from runtime.services.meaning_triangulation import TriangulationInput
from runtime.services.session_service import SessionService

_REAL_P04_CAPABILITY = {
    "type": "port",
    "id": "P04_Port",
    "status": "IMPLEMENTED",
    "capabilities": ["core_c04_hext_closure_verifier"],
}
_REAL_P04_UNAVAILABLE_CAPABILITY = {**_REAL_P04_CAPABILITY, "status": "NOT_IMPLEMENTED"}
_REAL_P04_RESULT = {
    "port_id": "P04_Port",
    "capability": "core_c04_hext_closure_verifier",
    "status": "OK",
    "result": {"quantized_once": [1.0, 2.0, 3.0], "residual": 0.0, "closed": True},
}


def _make_session(db_session):
    agent = AgentService().create(db_session, AgentCreate(provider=AgentProvider.CUSTOM, model="m1"))
    db_session.flush()
    session = SessionService().create(db_session, SessionCreate())
    db_session.flush()
    return agent, session


class _FakeGateway:
    def __init__(self, capability=None, invoke_result=None, capability_fail=None, invoke_fail=None):
        self.capability_calls: list[str] = []
        self.invoke_calls: list[tuple[str, dict]] = []
        self._capability = capability
        self._invoke_result = invoke_result
        self._capability_fail = capability_fail
        self._invoke_fail = invoke_fail

    async def get_port_capability(self, port_id: str) -> dict:
        self.capability_calls.append(port_id)
        if self._capability_fail:
            raise self._capability_fail
        return self._capability

    async def invoke_port(self, port_id: str, body: dict) -> dict:
        self.invoke_calls.append((port_id, body))
        if self._invoke_fail:
            raise self._invoke_fail
        return self._invoke_result


class _FakeHekb:
    def __init__(self, fail: bool = False, fail_after: int | None = None):
        self.calls: list[dict] = []
        self.relate_calls: list[tuple] = []
        self._fail = fail
        # fail_after: succeed the first N store()/relate() calls combined,
        # then start failing -- for proving a *partial* write is reported
        # BLOCKED, not PERSISTED.
        self._fail_after = fail_after
        self._call_count = 0

    def _maybe_fail(self):
        self._call_count += 1
        if self._fail or (self._fail_after is not None and self._call_count > self._fail_after):
            raise RetryExhaustedError("simulated HEKB failure")

    async def store(self, knowledge_object: dict) -> dict:
        # First call always returns "a"*64 (every pre-existing single-call
        # test asserts this exact value); later calls in the same test get
        # distinct letters ("b"*64, "c"*64, ...) -- ADR-0013's triangulation
        # tests make multiple store() calls per run and want distinct
        # trajectory/summary ids to prove real relate() linkage, not a
        # trivially-equal coincidence.
        self._maybe_fail()
        self.calls.append(knowledge_object)
        letter = chr(ord("a") + len(self.calls) - 1)
        return {"object_id": letter * 64, "hash": letter * 64, "timestamp": "2026-08-06T00:00:00Z"}

    async def relate(self, source: str, target: str, kind: str, weight: float = 0.0) -> str:
        self._maybe_fail()
        self.relate_calls.append((source, target, kind))
        return "e" * 64


# ---------------------------------------------------------------------------
# 1/4. Valid capability request -> SUCCESS
# ---------------------------------------------------------------------------


async def test_success_path_invokes_and_persists_evidence(db_session, fake_redis):
    agent, session = _make_session(db_session)
    gateway = _FakeGateway(capability=_REAL_P04_CAPABILITY, invoke_result=_REAL_P04_RESULT)
    hekb = _FakeHekb()

    result = await request_capability(
        db_session,
        session.session_id,
        agent.agent_id,
        CapabilityRequest(capability_id="P04", input={"vector": [1.0, 2.0, 3.0]}),
        gateway=gateway,
        hekb=hekb,
        event_service=EventService(),
    )

    assert result.outcome == RuntimeOutcome.SUCCESS
    assert result.evidence_status == EvidenceStatus.PERSISTED
    assert result.evidence_object_id == "a" * 64
    assert gateway.capability_calls == ["P04"]
    assert gateway.invoke_calls == [("P04", {"vector": [1.0, 2.0, 3.0]})]
    assert len(hekb.calls) == 1
    assert hekb.calls[0]["labels"]["runtime_cycle_id"] == str(result.runtime_cycle_id)


# ---------------------------------------------------------------------------
# 2. Invalid capability
# ---------------------------------------------------------------------------


async def test_invalid_capability_id_rejected_before_invoke(db_session, fake_redis):
    agent, session = _make_session(db_session)
    gateway = _FakeGateway(capability_fail=ValueError("port_id 'P99' is not valid"))
    hekb = _FakeHekb()

    result = await request_capability(
        db_session,
        session.session_id,
        agent.agent_id,
        CapabilityRequest(capability_id="P99", input={}),
        gateway=gateway,
        hekb=hekb,
        event_service=EventService(),
    )

    assert result.outcome == RuntimeOutcome.INVALID
    assert gateway.invoke_calls == []
    assert hekb.calls == []


# ---------------------------------------------------------------------------
# 3. Unavailable capability
# ---------------------------------------------------------------------------


async def test_unavailable_capability_not_invoked(db_session, fake_redis):
    agent, session = _make_session(db_session)
    gateway = _FakeGateway(capability=_REAL_P04_UNAVAILABLE_CAPABILITY)
    hekb = _FakeHekb()

    result = await request_capability(
        db_session,
        session.session_id,
        agent.agent_id,
        CapabilityRequest(capability_id="P04", input={}),
        gateway=gateway,
        hekb=hekb,
        event_service=EventService(),
    )

    assert result.outcome == RuntimeOutcome.UNAVAILABLE
    assert gateway.invoke_calls == []  # never attempted
    assert hekb.calls == []


# ---------------------------------------------------------------------------
# BLOCKED — capability discovery itself unreachable
# ---------------------------------------------------------------------------


async def test_blocked_when_capability_discovery_unreachable(db_session, fake_redis):
    agent, session = _make_session(db_session)
    gateway = _FakeGateway(capability_fail=RetryExhaustedError("NVS unreachable"))
    hekb = _FakeHekb()

    result = await request_capability(
        db_session,
        session.session_id,
        agent.agent_id,
        CapabilityRequest(capability_id="P04", input={}),
        gateway=gateway,
        hekb=hekb,
        event_service=EventService(),
    )

    assert result.outcome == RuntimeOutcome.BLOCKED
    assert gateway.invoke_calls == []


# ---------------------------------------------------------------------------
# 5. Invocation failure
# ---------------------------------------------------------------------------


async def test_invocation_failure(db_session, fake_redis):
    agent, session = _make_session(db_session)
    gateway = _FakeGateway(
        capability=_REAL_P04_CAPABILITY, invoke_fail=RetryExhaustedError("NVS Port call failed")
    )
    hekb = _FakeHekb()

    result = await request_capability(
        db_session,
        session.session_id,
        agent.agent_id,
        CapabilityRequest(capability_id="P04", input={"vector": [1.0]}),
        gateway=gateway,
        hekb=hekb,
        event_service=EventService(),
    )

    assert result.outcome == RuntimeOutcome.INVOCATION_FAILED
    assert hekb.calls == []  # never reached


# ---------------------------------------------------------------------------
# 6. Evidence failure — SUCCESS outcome, but evidence BLOCKED (HEKB unreachable)
# ---------------------------------------------------------------------------


async def test_evidence_blocked_does_not_downgrade_success_outcome(db_session, fake_redis):
    agent, session = _make_session(db_session)
    gateway = _FakeGateway(capability=_REAL_P04_CAPABILITY, invoke_result=_REAL_P04_RESULT)
    hekb = _FakeHekb(fail=True)

    result = await request_capability(
        db_session,
        session.session_id,
        agent.agent_id,
        CapabilityRequest(capability_id="P04", input={"vector": [1.0]}),
        gateway=gateway,
        hekb=hekb,
        event_service=EventService(),
    )

    assert result.outcome == RuntimeOutcome.SUCCESS  # the Port call itself succeeded
    assert result.evidence_status == EvidenceStatus.BLOCKED
    assert result.evidence_object_id is None


# ---------------------------------------------------------------------------
# 7. Lineage preservation
# ---------------------------------------------------------------------------


async def test_lineage_request_and_result_events_are_linked(db_session, fake_redis):
    agent, session = _make_session(db_session)
    gateway = _FakeGateway(capability=_REAL_P04_CAPABILITY, invoke_result=_REAL_P04_RESULT)
    hekb = _FakeHekb()

    result = await request_capability(
        db_session,
        session.session_id,
        agent.agent_id,
        CapabilityRequest(capability_id="P04", input={"vector": [1.0]}, reason="test"),
        gateway=gateway,
        hekb=hekb,
        event_service=EventService(),
    )

    events = EventService().list_events(db_session, session.session_id)
    assert len(events) == 2

    request_event = next(e for e in events if e.event_type == RuntimeEventType.CAPABILITY_REQUESTED.value)
    result_event = next(e for e in events if e.event_type == RuntimeEventType.CAPABILITY_RESULT.value)

    assert request_event.event_id == result.runtime_cycle_id
    assert result_event.event_id == result.result_event_id
    assert result_event.parent_event_id == request_event.event_id  # real lineage link
    assert request_event.payload["capability_id"] == "P04"
    assert result_event.payload["outcome"] == "SUCCESS"


async def test_lineage_preserved_even_when_request_is_invalid(db_session, fake_redis):
    """A rejected request is still real, replayable lineage — not silently
    dropped."""
    agent, session = _make_session(db_session)
    gateway = _FakeGateway(capability_fail=ValueError("invalid"))
    hekb = _FakeHekb()

    await request_capability(
        db_session,
        session.session_id,
        agent.agent_id,
        CapabilityRequest(capability_id="P99", input={}),
        gateway=gateway,
        hekb=hekb,
        event_service=EventService(),
    )

    events = EventService().list_events(db_session, session.session_id)
    assert len(events) == 2  # request + result recorded even on rejection


async def test_capability_events_are_not_forwarded_to_nvs():
    """Regression: CAPABILITY_REQUESTED/CAPABILITY_RESULT must never be
    forwarded a second time to NVS /observe — they are lineage records of
    calls already made directly to NVS's Port routes."""
    from runtime.gateway.kernel_gateway import _FORWARDED_EVENT_KINDS

    assert RuntimeEventType.CAPABILITY_REQUESTED not in _FORWARDED_EVENT_KINDS
    assert RuntimeEventType.CAPABILITY_RESULT not in _FORWARDED_EVENT_KINDS


# ---------------------------------------------------------------------------
# 8. Deterministic decision
# ---------------------------------------------------------------------------


async def test_deterministic_given_same_inputs(db_session, fake_redis):
    agent, session = _make_session(db_session)

    async def run_once():
        gateway = _FakeGateway(capability=_REAL_P04_CAPABILITY, invoke_result=_REAL_P04_RESULT)
        hekb = _FakeHekb()
        return await request_capability(
            db_session,
            session.session_id,
            agent.agent_id,
            CapabilityRequest(capability_id="P04", input={"vector": [1.0]}),
            gateway=gateway,
            hekb=hekb,
            event_service=EventService(),
        )

    r1 = await run_once()
    r2 = await run_once()
    assert r1.outcome == r2.outcome == RuntimeOutcome.SUCCESS
    assert r1.evidence_status == r2.evidence_status == EvidenceStatus.PERSISTED


# ---------------------------------------------------------------------------
# 9. No semantic hard-coded Port selection
# ---------------------------------------------------------------------------


def test_module_contains_no_hard_coded_port_branching():
    # Checked against the actual decision function's source, not the module
    # docstring (which legitimately cites "P04" as a worked example in
    # prose) — the real question is whether the DECISION LOGIC branches on
    # a specific Port identity, which it must not.
    source = inspect.getsource(request_capability)
    for port_id in ["P01", "P04", "P17", "P38"]:
        assert f'"{port_id}"' not in source
        assert f"'{port_id}'" not in source


def test_capability_id_is_opaque_caller_supplied_value():
    req = CapabilityRequest(capability_id="anything-the-caller-passes", input={})
    assert req.capability_id == "anything-the-caller-passes"


# ---------------------------------------------------------------------------
# request_meaning_trajectory — the second, structurally-parallel Decision
# Boundary function, for the MeaningMapper -> Trajectory capability.
# Uses the REAL meaning_mapper/msr libraries (no mocking possible or
# needed — neither does I/O); only HekbClient is faked, same convention
# as request_capability()'s own tests.
# ---------------------------------------------------------------------------


def _stable_observations(n: int, start: int = 0):
    return [
        build_hext_observation(
            observation_id=f"rmt-{i:04d}",
            text="the system is stable and observing correctly",
            state_hash="c" * 64,
            sealed_at=f"2026-08-17T02:00:{i:02d}Z",
        )
        for i in range(start, start + n)
    ]


async def test_request_meaning_trajectory_success_and_evidence_persisted(db_session, fake_redis):
    agent, session = _make_session(db_session)
    hekb = _FakeHekb()

    result = await request_meaning_trajectory(
        db_session,
        session.session_id,
        agent.agent_id,
        _stable_observations(8),
        hekb=hekb,
        event_service=EventService(),
    )

    assert result.outcome == RuntimeOutcome.SUCCESS
    assert result.invocation_result["stabilized"] is True
    assert result.evidence_status == EvidenceStatus.PERSISTED
    assert result.evidence_object_id == "a" * 64
    assert len(hekb.calls) == 1
    assert hekb.calls[0]["kind"] == "EVIDENCE"
    assert hekb.calls[0]["labels"]["runtime_cycle_id"] == str(result.runtime_cycle_id)


async def test_request_meaning_trajectory_success_without_stabilization(db_session, fake_redis):
    """Fewer observations than dwell_steps -> real SUCCESS (the capability
    ran correctly), but no trajectory yet -> evidence NOT_ATTEMPTED, not a
    fabricated persistence."""
    agent, session = _make_session(db_session)
    hekb = _FakeHekb()

    result = await request_meaning_trajectory(
        db_session,
        session.session_id,
        agent.agent_id,
        _stable_observations(2),
        hekb=hekb,
        event_service=EventService(),
    )

    assert result.outcome == RuntimeOutcome.SUCCESS
    assert result.invocation_result["stabilized"] is False
    assert result.evidence_status == EvidenceStatus.NOT_ATTEMPTED
    assert result.evidence_object_id is None
    assert hekb.calls == []


async def test_request_meaning_trajectory_empty_observations_is_invalid(db_session, fake_redis):
    agent, session = _make_session(db_session)
    hekb = _FakeHekb()

    result = await request_meaning_trajectory(
        db_session, session.session_id, agent.agent_id, [], hekb=hekb, event_service=EventService()
    )

    assert result.outcome == RuntimeOutcome.INVALID
    assert hekb.calls == []


async def test_request_meaning_trajectory_evidence_blocked_does_not_downgrade_success(
    db_session, fake_redis
):
    agent, session = _make_session(db_session)
    hekb = _FakeHekb(fail=True)

    result = await request_meaning_trajectory(
        db_session,
        session.session_id,
        agent.agent_id,
        _stable_observations(8),
        hekb=hekb,
        event_service=EventService(),
    )

    assert result.outcome == RuntimeOutcome.SUCCESS
    assert result.evidence_status == EvidenceStatus.BLOCKED
    assert result.evidence_object_id is None


async def test_request_meaning_trajectory_lineage_linked(db_session, fake_redis):
    agent, session = _make_session(db_session)
    hekb = _FakeHekb()

    result = await request_meaning_trajectory(
        db_session,
        session.session_id,
        agent.agent_id,
        _stable_observations(8),
        hekb=hekb,
        event_service=EventService(),
    )

    events = EventService().list_events(db_session, session.session_id)
    assert len(events) == 2
    request_event = next(e for e in events if e.event_type == RuntimeEventType.CAPABILITY_REQUESTED.value)
    result_event = next(e for e in events if e.event_type == RuntimeEventType.CAPABILITY_RESULT.value)
    assert request_event.event_id == result.runtime_cycle_id
    assert result_event.parent_event_id == request_event.event_id
    assert request_event.payload["capability_id"] == "meaning_mapper.trajectory"


async def test_request_meaning_trajectory_capability_descriptor_is_static_not_live(
    db_session, fake_redis
):
    """Honest distinction from Port capability discovery: no live network
    call happens for this capability's availability check."""
    agent, session = _make_session(db_session)
    hekb = _FakeHekb()

    result = await request_meaning_trajectory(
        db_session,
        session.session_id,
        agent.agent_id,
        _stable_observations(2),
        hekb=hekb,
        event_service=EventService(),
    )
    assert result.capability_descriptor == {
        "capability_id": "meaning_mapper.trajectory",
        "status": "IMPLEMENTED",
        "transport": "in-process",
    }


def test_request_meaning_trajectory_no_hard_coded_capability_selection():
    source = inspect.getsource(request_meaning_trajectory)
    # The default capability_id string itself is allowed (it names THIS
    # capability); what must never appear is a Port SSOT id, which would
    # indicate this function is secretly routing to a specific Port.
    for port_id in ["P01", "P04", "P17", "P38"]:
        assert f'"{port_id}"' not in source
        assert f"'{port_id}'" not in source


# ---------------------------------------------------------------------------
# request_meaning_triangulation() — real MeaningMapper/MSR (via
# run_meaning_triangulation), faked HekbClient (store + relate), same
# convention as request_meaning_trajectory()'s own tests above.
# ---------------------------------------------------------------------------


def _triangulation_inputs(text_a: str, text_b: str) -> list[TriangulationInput]:
    return [
        TriangulationInput(
            path_id="path-a",
            observations=[
                build_hext_observation(
                    observation_id=f"rmt-a-{i:04d}",
                    text=text_a,
                    state_hash="c" * 64,
                    sealed_at=f"2026-08-17T02:00:{i:02d}Z",
                )
                for i in range(8)
            ],
            method="repeated_stable",
        ),
        TriangulationInput(
            path_id="path-b",
            observations=[
                build_hext_observation(
                    observation_id=f"rmt-b-{i:04d}",
                    text=text_b,
                    state_hash="c" * 64,
                    sealed_at=f"2026-08-18T02:00:{i:02d}Z",
                )
                for i in range(8)
            ],
            method="paraphrase",
        ),
    ]


async def test_request_meaning_triangulation_persists_trajectories_and_summary_and_relates_them(
    db_session, fake_redis
):
    agent, session = _make_session(db_session)
    hekb = _FakeHekb()

    result = await request_meaning_triangulation(
        db_session,
        session.session_id,
        agent.agent_id,
        _triangulation_inputs("x", "x"),  # identical text on both paths -> both stabilize identically
        divergence_epsilon=1e-6,
        hekb=hekb,
        event_service=EventService(),
    )

    assert result.outcome == RuntimeOutcome.SUCCESS
    assert result.invocation_result["state"] == "STABLE"
    assert result.evidence_status == EvidenceStatus.PERSISTED
    assert result.evidence_object_id is not None
    # 2 stabilized paths -> 2 trajectory objects + 1 summary object = 3 store() calls
    assert len(hekb.calls) == 3
    assert hekb.calls[0]["kind"] == "EVIDENCE"
    assert hekb.calls[1]["kind"] == "EVIDENCE"
    assert hekb.calls[2]["labels"]["value_kind"] == "derived"  # the summary object
    # both trajectory objects DERIVES-related to the summary
    assert len(hekb.relate_calls) == 2
    for source, target, kind in hekb.relate_calls:
        assert kind == "DERIVES"
        assert target == result.evidence_object_id


async def test_request_meaning_triangulation_persists_evidence_even_when_divergent(db_session, fake_redis):
    """Divergent results are still real evidence worth keeping -- must not
    be silently dropped just because the paths disagreed."""
    agent, session = _make_session(db_session)
    hekb = _FakeHekb()

    result = await request_meaning_triangulation(
        db_session,
        session.session_id,
        agent.agent_id,
        _triangulation_inputs(
            "the system is stable and observing correctly",
            "a completely different sentence about something else",
        ),
        divergence_epsilon=1e-12,
        hekb=hekb,
        event_service=EventService(),
    )

    assert result.invocation_result["state"] == "DIVERGENT"
    assert result.evidence_status == EvidenceStatus.PERSISTED
    assert len(hekb.calls) == 3  # both trajectories + the (divergent) summary, all persisted


async def test_request_meaning_triangulation_partial_write_is_blocked_not_persisted(db_session, fake_redis):
    """A failure partway through the write sequence (after some
    trajectories are stored, before all DERIVES edges exist) must report
    BLOCKED, never a fabricated PERSISTED for an incomplete graph."""
    agent, session = _make_session(db_session)
    hekb = _FakeHekb(fail_after=2)  # 2 trajectory stores succeed, summary store fails

    result = await request_meaning_triangulation(
        db_session,
        session.session_id,
        agent.agent_id,
        _triangulation_inputs("x", "x"),
        divergence_epsilon=1e-6,
        hekb=hekb,
        event_service=EventService(),
    )

    assert result.outcome == RuntimeOutcome.SUCCESS  # the measurement itself ran fine
    assert result.evidence_status == EvidenceStatus.BLOCKED  # but persistence did not complete
    assert result.evidence_object_id is None


async def test_request_meaning_triangulation_empty_inputs_is_invalid(db_session, fake_redis):
    agent, session = _make_session(db_session)
    hekb = _FakeHekb()

    result = await request_meaning_triangulation(
        db_session, session.session_id, agent.agent_id, [], hekb=hekb, event_service=EventService()
    )

    assert result.outcome == RuntimeOutcome.INVALID
    assert hekb.calls == []


async def test_request_meaning_triangulation_lineage_linked(db_session, fake_redis):
    agent, session = _make_session(db_session)
    hekb = _FakeHekb()

    result = await request_meaning_triangulation(
        db_session,
        session.session_id,
        agent.agent_id,
        _triangulation_inputs("x", "x"),
        divergence_epsilon=1e-6,
        hekb=hekb,
        event_service=EventService(),
    )

    events = EventService().list_events(db_session, session.session_id)
    assert len(events) == 2
    request_event = next(e for e in events if e.event_type == RuntimeEventType.CAPABILITY_REQUESTED.value)
    result_event = next(e for e in events if e.event_type == RuntimeEventType.CAPABILITY_RESULT.value)
    assert request_event.event_id == result.runtime_cycle_id
    assert result_event.parent_event_id == request_event.event_id
    assert request_event.payload["capability_id"] == "meaning_mapper.triangulation"
