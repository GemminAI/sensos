import json
from typing import Any
from uuid import UUID

import redis
import redis.asyncio as aioredis

from runtime.core.config import Settings, get_settings

#: Redis stream + consumer group backing the Observation -> Queue -> Worker
#: pipeline (EXP-Ubuntu011). One group so every ForwardWorker instance
#: shares the queue instead of each seeing every message.
FORWARD_STREAM = "runtime:forward:queue"
FORWARD_GROUP = "nvs-forward-workers"


class RedisService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._client: redis.Redis | None = None
        self._aclient: aioredis.Redis | None = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self.settings.redis_url, decode_responses=True)
        return self._client

    @property
    def aclient(self) -> aioredis.Redis:
        if self._aclient is None:
            self._aclient = aioredis.from_url(self.settings.redis_url, decode_responses=True)
        return self._aclient

    def ping(self) -> bool:
        return bool(self.client.ping())

    def next_sequence(self, session_id: UUID, agent_id: UUID) -> int:
        key = f"runtime:seq:{session_id}:{agent_id}"
        return int(self.client.incr(key))

    def is_duplicate(self, event_id: UUID) -> bool:
        key = f"runtime:dedup:{event_id}"
        if self.client.exists(key):
            return True
        self.client.setex(key, self.settings.dedup_ttl_seconds, "1")
        return False

    def append_event_stream(self, session_id: UUID, envelope: dict[str, Any]) -> str:
        key = f"runtime:events:{session_id}"
        entry_id = self.client.xadd(
            key,
            {"data": json.dumps(envelope, default=str)},
            maxlen=self.settings.event_stream_maxlen,
            approximate=True,
        )
        return entry_id

    def read_event_stream(
        self,
        session_id: UUID,
        last_id: str = "0-0",
        count: int = 100,
    ) -> list[tuple[str, dict[str, Any]]]:
        key = f"runtime:events:{session_id}"
        entries = self.client.xread({key: last_id}, count=count, block=1000)
        result: list[tuple[str, dict[str, Any]]] = []
        for _stream, messages in entries:
            for msg_id, fields in messages:
                data = json.loads(fields["data"])
                result.append((msg_id, data))
        return result

    def set_session_cache(self, session_id: UUID, data: dict[str, Any]) -> None:
        key = f"runtime:session:{session_id}"
        self.client.hset(key, mapping={k: json.dumps(v, default=str) for k, v in data.items()})

    def get_session_cache(self, session_id: UUID) -> dict[str, Any]:
        key = f"runtime:session:{session_id}"
        raw = self.client.hgetall(key)
        return {k: json.loads(v) for k, v in raw.items()}

    def set_experiment_cache(self, experiment_id: UUID, data: dict[str, Any]) -> None:
        key = f"runtime:experiment:{experiment_id}"
        self.client.hset(key, mapping={k: json.dumps(v, default=str) for k, v in data.items()})

    def enqueue_forward(self, payload: dict[str, Any]) -> str:
        return self.client.xadd(FORWARD_STREAM, {"data": json.dumps(payload, default=str)})

    async def ensure_forward_group(self) -> None:
        """Idempotently create the ForwardWorker consumer group. Safe to call
        on every worker startup — BUSYGROUP means it already exists."""
        try:
            await self.aclient.xgroup_create(FORWARD_STREAM, FORWARD_GROUP, id="0", mkstream=True)
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def dequeue_forward_batch(
        self, consumer: str, batch_size: int, block_ms: int
    ) -> list[tuple[str, dict[str, Any]]]:
        """Read up to `batch_size` entries for `consumer` from the forward
        queue: this consumer's own still-unacknowledged entries first (id
        "0" — retries a previous batch that failed transport and was left
        un-ACKed), then new entries ("id" ">") to fill the rest, blocking up
        to `block_ms` only for the new-entries read.

        Entries are delivered but not acknowledged — call ack_forward() once
        they're durably handled, or the next drain_once() (same consumer)
        will read them again from its own pending list (at-least-once
        delivery, single-consumer redelivery model)."""
        result: list[tuple[str, dict[str, Any]]] = []

        pending = await self.aclient.xreadgroup(
            groupname=FORWARD_GROUP,
            consumername=consumer,
            streams={FORWARD_STREAM: "0"},
            count=batch_size,
        )
        for _stream, messages in pending or []:
            for msg_id, fields in messages:
                result.append((msg_id, json.loads(fields["data"])))

        remaining = batch_size - len(result)
        if remaining > 0:
            fresh = await self.aclient.xreadgroup(
                groupname=FORWARD_GROUP,
                consumername=consumer,
                streams={FORWARD_STREAM: ">"},
                count=remaining,
                block=block_ms,
            )
            for _stream, messages in fresh or []:
                for msg_id, fields in messages:
                    result.append((msg_id, json.loads(fields["data"])))

        return result

    async def ack_forward(self, *msg_ids: str) -> None:
        if msg_ids:
            await self.aclient.xack(FORWARD_STREAM, FORWARD_GROUP, *msg_ids)

    def publish_telemetry(self, session_id: UUID, data: dict[str, Any]) -> None:
        channel = f"kernel:telemetry:{session_id}"
        self.client.publish(channel, json.dumps(data, default=str))
