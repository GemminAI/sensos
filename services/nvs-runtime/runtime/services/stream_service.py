import asyncio
import json
from typing import AsyncGenerator
from uuid import UUID

from runtime.services.redis_service import RedisService


class StreamService:
    def __init__(self, redis: RedisService | None = None):
        self.redis = redis or RedisService()

    async def sse_stream(
        self,
        session_id: UUID,
        replay_from: str = "0-0",
    ) -> AsyncGenerator[str, None]:
        last_id = replay_from
        replay_done = replay_from != "$"

        while True:
            if replay_done:
                entries = self.redis.read_event_stream(session_id, last_id=last_id, count=50)
            else:
                entries = self.redis.read_event_stream(session_id, last_id=last_id, count=1000)
                if not entries:
                    replay_done = True
                    last_id = "$"
                    continue

            for msg_id, data in entries:
                last_id = msg_id
                event_name = data.get("schema_version", "nvs.runtime.event.v1")
                yield f"event: {event_name}\n"
                yield f"id: {msg_id}\n"
                yield f"data: {json.dumps(data, default=str)}\n\n"

            if not replay_done:
                replay_done = True
                last_id = entries[-1][0] if entries else "$"
                continue

            await asyncio.sleep(0.5)
