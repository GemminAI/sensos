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
)
from runtime.services.event_service import EventService
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
    def __init__(self, fail: bool = False):
        self.calls: list[dict] = []
        self._fail = fail

    async def store(self, knowledge_object: dict) -> dict:
        if self._fail:
            raise RetryExhaustedError("simulated HEKB failure")
        self.calls.append(knowledge_object)
        return {"object_id": "a" * 64, "hash": "a" * 64, "timestamp": "2026-08-06T00:00:00Z"}


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
