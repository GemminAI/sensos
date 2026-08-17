from contextlib import nullcontext
from uuid import uuid4

import httpx
import pytest

from runtime.models.enums import AgentProvider, ForwardStatus, RuntimeEventType, SEP_VERSION
from runtime.models.schemas import AgentCreate, EventIngestRequest, SessionCreate
from runtime.services.agent_service import AgentService
from runtime.services.event_service import EventService
from runtime.services.forward_worker import ForwardWorker
from runtime.services.session_service import SessionService


def _make_session(db_session):
    agent = AgentService().create(db_session, AgentCreate(provider=AgentProvider.CUSTOM, model="m1"))
    db_session.flush()
    session = SessionService().create(db_session, SessionCreate(participants=[agent.agent_id]))
    db_session.flush()
    return agent, session


def _worker(db_session, gateway, redis, consumer="test-worker", cle=None, hekb=None) -> ForwardWorker:
    return ForwardWorker(
        redis=redis,
        gateway=gateway,
        cle=cle,
        hekb=hekb,
        consumer=consumer,
        db_session_factory=lambda: nullcontext(db_session),
    )


class _FakeGateway:
    """Records every observe_batch() call instead of doing real transport —
    the queue/batch/status-update wiring is what this test file verifies,
    not KernelGateway's own HTTP behavior (see test_kernel_gateway.py).

    `geometry` defaults to None (no `position` key), which is exactly what a
    real ObserveResponse looks like when include_vectors wasn't honoured —
    ForwardWorker._propagate_semantic_mapping() returns immediately in that
    case, so every pre-EXP-Ubuntu012B test below still runs without ever
    touching CLEClient/HekbClient."""

    def __init__(
        self,
        cycle_start: int = 1,
        fail_sessions: frozenset[str] = frozenset(),
        geometry: dict | None = None,
        port_results: dict[str, dict] | None = None,
        fail_port_ids: frozenset[str] = frozenset(),
    ):
        self.calls: list[tuple[str, int]] = []
        self.port_calls: list[tuple[str, dict]] = []
        self._cycle = cycle_start
        self._fail_sessions = fail_sessions
        self._geometry = geometry
        self._port_results = port_results or {}
        self._fail_port_ids = fail_port_ids

    async def observe_batch(self, session_id: str, events: list):
        if session_id in self._fail_sessions:
            from runtime.gateway.http_pool import RetryExhaustedError

            raise RetryExhaustedError(f"simulated failure for {session_id}")
        self.calls.append((session_id, len(events)))
        self._cycle += 1

        class _Resp:
            cycle = self._cycle
            geometry = self._geometry

        return _Resp()

    async def invoke_port(self, port_id: str, body: dict) -> dict:
        self.port_calls.append((port_id, body))
        if port_id in self._fail_port_ids:
            from runtime.gateway.http_pool import RetryExhaustedError

            raise RetryExhaustedError(f"simulated Port failure for {port_id}")
        return self._port_results.get(
            port_id,
            {"port_id": f"{port_id}_Port", "status": "OK", "result": {}},
        )


class _FakeCLE:
    def __init__(self, fail: bool = False):
        self.calls: list[list[float]] = []
        self._fail = fail

    async def lift(self, position: list[float]) -> dict:
        if self._fail:
            from runtime.gateway.http_pool import RetryExhaustedError

            raise RetryExhaustedError("simulated CLE failure")
        self.calls.append(position)
        return {
            "concept_id": "fake-concept",
            "normalized_hash": "fake-hash",
            "invariants": {"betti_0": 1, "betti_1": 0, "betti_2": 0, "euler_characteristic": 1},
            "compression_ratio": 1.0,
            "proof": {"is_valid": True},
        }


class _FakeHekb:
    def __init__(self, fail: bool = False):
        self.calls: list[dict] = []
        self._fail = fail

    async def store(self, knowledge_object: dict) -> dict:
        if self._fail:
            from runtime.gateway.http_pool import RetryExhaustedError

            raise RetryExhaustedError("simulated HEKB failure")
        self.calls.append(knowledge_object)
        return {"object_id": "a" * 64, "hash": "a" * 64, "timestamp": "2026-08-06T00:00:00Z"}


def _redis_service_from(fake_redis):
    from runtime.services.redis_service import RedisService

    return RedisService()


async def test_drain_once_delivers_queued_event_and_acks(db_session, fake_redis):
    agent, session = _make_session(db_session)
    service = EventService()
    result = service.ingest(
        db_session,
        session.session_id,
        EventIngestRequest(
            event_type=RuntimeEventType.STATE_RAW.value,
            agent_id=agent.agent_id,
            source_provider="custom",
            payload={"text": "hello"},
        ),
    )
    assert result.forward_status == ForwardStatus.QUEUED

    gateway = _FakeGateway()
    worker = _worker(db_session, gateway, _redis_service_from(fake_redis))

    processed = await worker.drain_once(block_ms=50)

    assert processed == 1
    assert len(gateway.calls) == 1
    assert gateway.calls[0][0] == str(session.session_id)

    stored = service.list_events(db_session, session.session_id)[0]
    assert stored.forward_status == ForwardStatus.FORWARDED.value
    assert stored.kernel_run_id is not None

    # ACKed -> a second drain sees nothing new for this consumer.
    processed_again = await worker.drain_once(block_ms=50)
    assert processed_again == 0


async def test_drain_once_batches_same_session_events_into_one_call(db_session, fake_redis, monkeypatch):
    # The "local" profile defaults batch_size=1 (no batching needed on
    # localhost) — force a WAN-like profile so this test actually exercises
    # batching regardless of which NetworkProfile is ambient.
    from runtime.core.network_profile import NetworkProfile
    from runtime.services import forward_worker as forward_worker_module

    monkeypatch.setattr(
        forward_worker_module,
        "get_network_profile",
        lambda: NetworkProfile(
            mode="wan", base_rtt_ms=155, request_timeout_ms=1500, connect_timeout_ms=300,
            retry_count=3, retry_backoff_ms=250, batch_size=10,
        ),
    )

    agent, session = _make_session(db_session)
    service = EventService()
    for i in range(3):
        service.ingest(
            db_session,
            session.session_id,
            EventIngestRequest(
                event_type=RuntimeEventType.STATE_RAW.value,
                agent_id=agent.agent_id,
                source_provider="custom",
                payload={"text": f"event-{i}"},
            ),
        )

    gateway = _FakeGateway()
    worker = _worker(db_session, gateway, _redis_service_from(fake_redis))

    processed = await worker.drain_once(block_ms=50)

    assert processed == 3
    assert len(gateway.calls) == 1  # one batched /observe call, not three
    assert gateway.calls[0][1] == 3

    events = service.list_events(db_session, session.session_id)
    assert all(e.forward_status == ForwardStatus.FORWARDED.value for e in events)


async def test_skipped_event_type_acked_without_gateway_call(db_session, fake_redis):
    agent, session = _make_session(db_session)
    service = EventService()
    service.ingest(
        db_session,
        session.session_id,
        EventIngestRequest(
            event_type=RuntimeEventType.HEARTBEAT.value,
            agent_id=agent.agent_id,
            source_provider="custom",
            payload={},
        ),
    )

    gateway = _FakeGateway()
    worker = _worker(db_session, gateway, _redis_service_from(fake_redis))

    processed = await worker.drain_once(block_ms=50)

    assert processed == 1
    assert gateway.calls == []
    stored = service.list_events(db_session, session.session_id)[0]
    assert stored.forward_status == ForwardStatus.SKIPPED.value


async def test_transport_failure_leaves_entry_unacked_for_redelivery(db_session, fake_redis):
    agent, session = _make_session(db_session)
    service = EventService()
    service.ingest(
        db_session,
        session.session_id,
        EventIngestRequest(
            event_type=RuntimeEventType.STATE_RAW.value,
            agent_id=agent.agent_id,
            source_provider="custom",
            payload={"text": "will fail"},
        ),
    )

    failing_gateway = _FakeGateway(fail_sessions=frozenset({str(session.session_id)}))
    redis = _redis_service_from(fake_redis)
    worker = _worker(db_session, failing_gateway, redis)

    processed = await worker.drain_once(block_ms=50)
    assert processed == 1  # entry was read...

    stored = service.list_events(db_session, session.session_id)[0]
    assert stored.forward_status == ForwardStatus.QUEUED.value  # ...but never marked FORWARDED

    # Same consumer's next drain_once() re-reads its own pending entry (id
    # "0") before taking new ones — at-least-once redelivery within one
    # consumer, no XCLAIM/second-consumer handoff in this phase.
    recovering_gateway = _FakeGateway()
    worker.gateway = recovering_gateway
    processed2 = await worker.drain_once(block_ms=50)
    assert processed2 == 1
    assert len(recovering_gateway.calls) == 1

    stored2 = service.list_events(db_session, session.session_id)[0]
    assert stored2.forward_status == ForwardStatus.FORWARDED.value


async def test_successful_forward_propagates_through_cle_to_hekb(db_session, fake_redis):
    """EXP-Ubuntu012B: once NVS returns geometry.position, ForwardWorker
    carries it through CLEClient.lift() and HEKBClient.store() — the
    target NVS -> CLE -> HEKB pipeline, with fakes standing in for the
    real HTTP clients (see test_extension_point_clients.py for those)."""
    agent, session = _make_session(db_session)
    service = EventService()
    service.ingest(
        db_session,
        session.session_id,
        EventIngestRequest(
            event_type=RuntimeEventType.STATE_RAW.value,
            agent_id=agent.agent_id,
            source_provider="custom",
            payload={"text": "semantic mapping happy path"},
        ),
    )

    gateway = _FakeGateway(geometry={"position": [0.1, 0.2, 0.3]})
    cle, hekb = _FakeCLE(), _FakeHekb()
    worker = _worker(db_session, gateway, _redis_service_from(fake_redis), cle=cle, hekb=hekb)

    processed = await worker.drain_once(block_ms=50)

    assert processed == 1
    stored = service.list_events(db_session, session.session_id)[0]
    assert stored.forward_status == ForwardStatus.FORWARDED.value  # NVS leg unaffected

    assert cle.calls == [[0.1, 0.2, 0.3]]
    assert len(hekb.calls) == 1
    assert hekb.calls[0]["kind"] == "OBSERVATION"
    assert hekb.calls[0]["vector"] == [0.1, 0.2, 0.3]
    assert hekb.calls[0]["labels"]["session_id"] == str(session.session_id)


async def test_forward_without_geometry_skips_semantic_mapping(db_session, fake_redis):
    """No include_vectors/position on the response (e.g. an nvs-kernel that
    predates EXP-Ubuntu012B) -> CLE/HEKB are never called, NVS forwarding
    still succeeds."""
    agent, session = _make_session(db_session)
    service = EventService()
    service.ingest(
        db_session,
        session.session_id,
        EventIngestRequest(
            event_type=RuntimeEventType.STATE_RAW.value,
            agent_id=agent.agent_id,
            source_provider="custom",
            payload={"text": "no geometry"},
        ),
    )

    gateway = _FakeGateway()  # geometry=None by default
    cle, hekb = _FakeCLE(), _FakeHekb()
    worker = _worker(db_session, gateway, _redis_service_from(fake_redis), cle=cle, hekb=hekb)

    processed = await worker.drain_once(block_ms=50)

    assert processed == 1
    stored = service.list_events(db_session, session.session_id)[0]
    assert stored.forward_status == ForwardStatus.FORWARDED.value
    assert cle.calls == []
    assert hekb.calls == []


async def test_semantic_mapping_failure_does_not_affect_nvs_forward_status(db_session, fake_redis):
    """CLE/HEKB unreachable -> logged and swallowed; the already-successful
    NVS forward (and its FORWARDED status) must not be undone by it."""
    agent, session = _make_session(db_session)
    service = EventService()
    service.ingest(
        db_session,
        session.session_id,
        EventIngestRequest(
            event_type=RuntimeEventType.STATE_RAW.value,
            agent_id=agent.agent_id,
            source_provider="custom",
            payload={"text": "cle is down"},
        ),
    )

    gateway = _FakeGateway(geometry={"position": [0.5]})
    cle, hekb = _FakeCLE(fail=True), _FakeHekb()
    worker = _worker(db_session, gateway, _redis_service_from(fake_redis), cle=cle, hekb=hekb)

    processed = await worker.drain_once(block_ms=50)

    assert processed == 1
    stored = service.list_events(db_session, session.session_id)[0]
    assert stored.forward_status == ForwardStatus.FORWARDED.value
    assert hekb.calls == []  # never reached — lift() failed first


# ---------------------------------------------------------------------------
# ForwardWorker.persist_port_evidence — 38-Port invoke -> HEKB Evidence
# ---------------------------------------------------------------------------

_REAL_P04_RESULT = {
    "port_id": "P04_Port",
    "capability": "core_c04_hext_closure_verifier",
    "status": "OK",
    "result": {"quantized_once": [1.0, 2.0, 3.0], "residual": 0.0, "closed": True},
}
_REAL_P02_RESULT = {
    "port_id": "P02_Port",
    "capability": "core_c02_homotopic_identity_resolver",
    "status": "OK",
    "result": {"top_eigenvalue": 0.0, "betti": [1, 0, 0], "identity_code": 1.0},
}


async def test_persist_port_evidence_stateless_port(db_session, fake_redis):
    """Stateless Port (no session_id needed) -> real result -> HEKB Evidence."""
    gateway = _FakeGateway(port_results={"P04": _REAL_P04_RESULT})
    hekb = _FakeHekb()
    worker = _worker(db_session, gateway, _redis_service_from(fake_redis), hekb=hekb)

    result = await worker.persist_port_evidence("P04", {"vector": [1.0, 2.0, 3.0]})

    assert gateway.port_calls == [("P04", {"vector": [1.0, 2.0, 3.0]})]
    assert len(hekb.calls) == 1
    assert hekb.calls[0]["kind"] == "EVIDENCE"
    assert hekb.calls[0]["labels"]["port_id"] == "P04"
    assert "session_id" not in hekb.calls[0]["labels"]
    assert result["object_id"] == "a" * 64


async def test_persist_port_evidence_session_scoped_port(db_session, fake_redis):
    gateway = _FakeGateway(port_results={"P02": _REAL_P02_RESULT})
    hekb = _FakeHekb()
    worker = _worker(db_session, gateway, _redis_service_from(fake_redis), hekb=hekb)

    await worker.persist_port_evidence(
        "P02", {"session_id": "sess-live-1", "epsilon": 0.5}, session_id="sess-live-1", cycle=3
    )

    assert gateway.port_calls == [("P02", {"session_id": "sess-live-1", "epsilon": 0.5})]
    assert hekb.calls[0]["labels"]["session_id"] == "sess-live-1"
    assert hekb.calls[0]["labels"]["cycle"] == "3"


async def test_persist_port_evidence_preserves_port_id(db_session, fake_redis):
    gateway = _FakeGateway(port_results={"P17": {"port_id": "P17_Port", "result": {}}})
    hekb = _FakeHekb()
    worker = _worker(db_session, gateway, _redis_service_from(fake_redis), hekb=hekb)

    await worker.persist_port_evidence("P17", {})

    assert hekb.calls[0]["labels"]["port_id"] == "P17"


async def test_persist_port_evidence_preserves_session_id(db_session, fake_redis):
    gateway = _FakeGateway(port_results={"P02": _REAL_P02_RESULT})
    hekb = _FakeHekb()
    worker = _worker(db_session, gateway, _redis_service_from(fake_redis), hekb=hekb)

    await worker.persist_port_evidence("P02", {}, session_id="sess-xyz")

    assert hekb.calls[0]["labels"]["session_id"] == "sess-xyz"


async def test_persist_port_evidence_port_invoke_failure_propagates(db_session, fake_redis):
    """Error propagation: unlike _propagate_semantic_mapping, there is no
    prior success to protect, so a Port-invoke failure must surface."""
    from runtime.gateway.http_pool import RetryExhaustedError

    gateway = _FakeGateway(fail_port_ids=frozenset({"P04"}))
    hekb = _FakeHekb()
    worker = _worker(db_session, gateway, _redis_service_from(fake_redis), hekb=hekb)

    with pytest.raises(RetryExhaustedError):
        await worker.persist_port_evidence("P04", {"vector": [1.0]})

    assert hekb.calls == []  # never reached


async def test_persist_port_evidence_hekb_unavailable_propagates(db_session, fake_redis):
    """Unavailable downstream dependency: HEKB unreachable must surface as
    a real failure, not be silently swallowed."""
    from runtime.gateway.http_pool import RetryExhaustedError

    gateway = _FakeGateway(port_results={"P04": _REAL_P04_RESULT})
    hekb = _FakeHekb(fail=True)
    worker = _worker(db_session, gateway, _redis_service_from(fake_redis), hekb=hekb)

    with pytest.raises(RetryExhaustedError):
        await worker.persist_port_evidence("P04", {"vector": [1.0]})


async def test_persist_port_evidence_does_not_call_cle(db_session, fake_redis):
    """No CLE step: nothing maps a Port result onto CLE's theta shape."""
    gateway = _FakeGateway(port_results={"P04": _REAL_P04_RESULT})
    cle, hekb = _FakeCLE(), _FakeHekb()
    worker = _worker(db_session, gateway, _redis_service_from(fake_redis), cle=cle, hekb=hekb)

    await worker.persist_port_evidence("P04", {"vector": [1.0]})

    assert cle.calls == []


async def test_persist_port_evidence_no_fabricated_evidence_fields(db_session, fake_redis):
    """No Var[S]/H_comp/Triad/state_hash is computed or claimed anywhere in
    the persisted object."""
    import json as _json

    gateway = _FakeGateway(port_results={"P04": _REAL_P04_RESULT})
    hekb = _FakeHekb()
    worker = _worker(db_session, gateway, _redis_service_from(fake_redis), hekb=hekb)

    await worker.persist_port_evidence("P04", {"vector": [1.0]})

    haystack = _json.dumps(hekb.calls[0]).lower()
    for term in ("var_s", "h_comp", "state_hash", "canonical", "triad", "eou"):
        assert term not in haystack
    assert hekb.calls[0]["labels"]["value_kind"] == "measured"
