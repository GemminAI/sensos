"""Observation -> Queue -> Worker -> NVS -> CLE -> HEKB (EXP-Ubuntu011 + 012B).

Background task that drains the Redis forward queue populated by
EventService.ingest() and delivers events to NVS-Kernel through
KernelGateway, batching same-session envelopes into a single /observe call
per NetworkProfile.batch_size (fewer WAN round trips under the ~155ms RTT
measured in EXP-Ubuntu010B).

EXP-Ubuntu012B: after a successful /observe, `_propagate_semantic_mapping()`
carries the resulting geometry through CLEClient.lift() and HEKBClient.store()
— see runtime/gateway/cle_client.py and hekb_client.py. This is wiring only
(minimal field mapping in build_hekb_object()); no new CLE/HEKB business
logic lives here. It is deliberately best-effort: a CLE/HEKB failure is
logged and does not affect the Observation -> NVS forward, which has already
succeeded by the time this runs, nor does it change ForwardStatus.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from contextlib import AbstractContextManager
from typing import Any, Callable
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from runtime.abi.observation import ObservationEvent, ObserveResponse
from runtime.core.network_profile import get_network_profile
from runtime.db.session import get_db_session
from runtime.gateway.cle_client import CLEClient
from runtime.gateway.hekb_client import HekbClient, build_hekb_object, build_hekb_object_from_port_result
from runtime.gateway.http_pool import RetryExhaustedError
from runtime.gateway.kernel_gateway import KernelGateway, build_observation_event
from runtime.models.enums import ForwardStatus
from runtime.services.event_service import EventService
from runtime.services.redis_service import RedisService

logger = logging.getLogger(__name__)

_TRANSPORT_ERRORS = (httpx.HTTPError, RetryExhaustedError)


class ForwardWorker:
    """Drains `runtime:forward:queue` and delivers queued envelopes to
    NVS-Kernel, batched per session_id (an ObserveRequest is scoped to one
    session_id, so a queue batch spanning sessions is split accordingly)."""

    def __init__(
        self,
        redis: RedisService | None = None,
        gateway: KernelGateway | None = None,
        cle: CLEClient | None = None,
        hekb: HekbClient | None = None,
        consumer: str = "forward-worker-1",
        db_session_factory: Callable[[], AbstractContextManager[Session]] | None = None,
    ):
        self.redis = redis or RedisService()
        self.gateway = gateway or KernelGateway()
        self.cle = cle or CLEClient()
        self.hekb = hekb or HekbClient()
        self.consumer = consumer
        # Injectable so tests can point the worker at the same session/engine
        # a test's fixtures use instead of the process-global DB (which
        # get_db_session() would otherwise reach for).
        self.db_session_factory = db_session_factory or get_db_session
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        await self.redis.ensure_forward_group()
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_forever())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _run_forever(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.drain_once()
            except Exception:
                logger.exception("ForwardWorker iteration failed; backing off")
                await asyncio.sleep(1.0)

    async def drain_once(self, block_ms: int = 2000) -> int:
        """Pull one batch off the queue, deliver it, ACK what succeeded.

        Returns the number of queue entries processed (delivered, skipped,
        or left un-ACKed for redelivery after a transport failure).
        DB/Redis calls here are synchronous (SQLAlchemy is not async in this
        service) — acceptable in a dedicated background task, unlike in the
        request path this replaces.
        """
        # Idempotent — cheap, and lets drain_once() be called directly (e.g.
        # in tests) without requiring start() to have run first.
        await self.redis.ensure_forward_group()

        profile = get_network_profile()
        entries = await self.redis.dequeue_forward_batch(self.consumer, profile.batch_size, block_ms)
        if not entries:
            return 0

        by_session: dict[str, list[tuple[str, UUID, ObservationEvent]]] = defaultdict(list)
        skipped: list[tuple[str, UUID]] = []

        for msg_id, item in entries:
            observation_event = build_observation_event(item["envelope"])
            event_id = UUID(item["event_id"])
            if observation_event is None:
                skipped.append((msg_id, event_id))
                continue
            session_id = str(item["envelope"].get("session_id"))
            by_session[session_id].append((msg_id, event_id, observation_event))

        ack_ids: list[str] = []
        with self.db_session_factory() as db:
            service = EventService(redis=self.redis)

            for msg_id, event_id in skipped:
                service.update_forward_status(db, event_id, ForwardStatus.SKIPPED)
                ack_ids.append(msg_id)

            for session_id, batch in by_session.items():
                batch_msg_ids = [msg_id for msg_id, _, _ in batch]
                batch_event_ids = [event_id for _, event_id, _ in batch]
                observation_events = [event for _, _, event in batch]
                try:
                    response = await self.gateway.observe_batch(session_id, observation_events)
                except _TRANSPORT_ERRORS as exc:
                    logger.warning(
                        "ForwardWorker: NVS unavailable for session %s (%d queued events): %s",
                        session_id, len(batch), exc,
                    )
                    continue  # left un-ACKed -> this consumer retries it on its next drain_once()
                for event_id in batch_event_ids:
                    service.update_forward_status(
                        db, event_id, ForwardStatus.FORWARDED, str(response.cycle)
                    )
                ack_ids.extend(batch_msg_ids)
                await self._propagate_semantic_mapping(session_id, response)

        await self.redis.ack_forward(*ack_ids)
        return len(entries)

    async def _propagate_semantic_mapping(
        self, session_id: str, response: ObserveResponse
    ) -> None:
        """NVS -> CLEClient.lift() -> HEKBClient.store() (EXP-Ubuntu012B).

        Best-effort: the Observation -> NVS forward this follows has already
        succeeded and is already ACKed/FORWARDED by the time this runs, so a
        CLE/HEKB failure here is logged, not raised — it must not undo or
        block delivery that already happened.
        """
        geometry = response.geometry or {}
        position = geometry.get("position")
        if not position:
            logger.debug(
                "ForwardWorker: no geometry.position on cycle %s for session %s "
                "(include_vectors not honoured?) — skipping Semantic Mapping",
                response.cycle, session_id,
            )
            return

        try:
            lift_result = await self.cle.lift(position)
            hekb_object = build_hekb_object(
                lift_result, position=position, session_id=session_id, cycle=response.cycle
            )
            await self.hekb.store(hekb_object)
        except _TRANSPORT_ERRORS as exc:
            logger.warning(
                "ForwardWorker: Semantic Mapping failed for session %s (cycle %s): %s",
                session_id, response.cycle, exc,
            )

    async def persist_port_evidence(
        self,
        port_id: str,
        body: dict[str, Any],
        *,
        session_id: str | None = None,
        cycle: int | None = None,
    ) -> dict[str, Any]:
        """Invoke one real 38-Port and persist its raw result to HEKB as
        Evidence: NVS Port invoke -> HEKB, the Port-result analog of
        `_propagate_semantic_mapping`'s NVS -> CLE -> HEKB chain.

        No CLE step: nothing in this repo maps a Port result onto CLE's
        theta/ConceptInput shape, and inventing one would fabricate a
        protocol this integration must avoid (see
        `build_hekb_object_from_port_result`'s docstring).

        Unlike `_propagate_semantic_mapping`, this does NOT swallow
        transport errors. That method is a best-effort side effect chained
        after an observation delivery that has already succeeded and been
        ACKed; this method has no such prior success to protect -- a
        Port-invoke or HEKB-store failure here is the caller's only signal
        that persistence did not happen, so it propagates.

        `session_id`/`cycle` are optional and independent of each other:
        many of the 38 Ports are stateless (v1.4 Section 5.1's own
        taxonomy; confirmed in this repo's prior audit -- 11 real stateless
        Ports require no session_id at all) and this method is not itself
        wired into the automatic queue-drain loop -- WHICH port(s) should
        be invoked routinely, on what trigger, and with what body
        constructed from which real observation field, is not specified
        anywhere in v1.4 or in NVS-Kernel's own documented contract, and is
        not decided here (see Reality Audit: BLOCKED_BY_SPEC_DECISION).
        This method makes the resulting capability real and callable; it
        does not auto-invoke itself.
        """
        port_result = await self.gateway.invoke_port(port_id, body)
        hekb_object = build_hekb_object_from_port_result(
            port_id, port_result, session_id=session_id, cycle=cycle
        )
        return await self.hekb.store(hekb_object)
