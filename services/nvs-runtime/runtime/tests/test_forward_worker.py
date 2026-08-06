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


def _worker(db_session, gateway, redis, consumer="test-worker") -> ForwardWorker:
    return ForwardWorker(
        redis=redis,
        gateway=gateway,
        consumer=consumer,
        db_session_factory=lambda: nullcontext(db_session),
    )


class _FakeGateway:
    """Records every observe_batch() call instead of doing real transport —
    the queue/batch/status-update wiring is what this test file verifies,
    not KernelGateway's own HTTP behavior (see test_kernel_gateway.py)."""

    def __init__(self, cycle_start: int = 1, fail_sessions: frozenset[str] = frozenset()):
        self.calls: list[tuple[str, int]] = []
        self._cycle = cycle_start
        self._fail_sessions = fail_sessions

    async def observe_batch(self, session_id: str, events: list):
        if session_id in self._fail_sessions:
            from runtime.gateway.http_pool import RetryExhaustedError

            raise RetryExhaustedError(f"simulated failure for {session_id}")
        self.calls.append((session_id, len(events)))
        self._cycle += 1

        class _Resp:
            cycle = self._cycle

        return _Resp()


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
