import json
from typing import Any
from uuid import UUID

import redis

from runtime.core.config import Settings, get_settings


class RedisService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._client: redis.Redis | None = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self.settings.redis_url, decode_responses=True)
        return self._client

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
        return self.client.xadd("runtime:forward:queue", {"data": json.dumps(payload, default=str)})

    def publish_telemetry(self, session_id: UUID, data: dict[str, Any]) -> None:
        channel = f"kernel:telemetry:{session_id}"
        self.client.publish(channel, json.dumps(data, default=str))
