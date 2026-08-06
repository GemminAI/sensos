"""HEKB client — transport-only extension point.

EXP-Ubuntu011 scope is the Runtime Transport Layer only. This client gives
the HEKB leg the same pooled/async/retry/timeout transport as NVS and CLE,
but does **not** implement the Observation -> Knowledge Object mapping (the
"Memory Adapter" business logic) — see runtime/core/config.py's `hekb_url`
docstring for the confirmed port this defaults to
(`integrations/hekb-mcp/client.py`'s DEFAULT_BASE_URL) and adjust per
deployment.

Do not call any store/query method from the Worker in this phase; only
`health_check()` and the generic `call()` transport are exercised today.
"""

from __future__ import annotations

from typing import Any

from runtime.core.config import Settings, get_settings
from runtime.gateway.http_pool import RetryExhaustedError, request_with_retry

_TRANSPORT_ERRORS = (RetryExhaustedError,)


class HekbClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def base_url(self) -> str:
        return self.settings.hekb_url

    async def health_check(self) -> bool:
        try:
            response = await request_with_retry("GET", self.base_url, "/health")
            return response.status_code == 200
        except _TRANSPORT_ERRORS:
            return False

    async def call(self, method: str, path: str, *, json: dict[str, Any] | None = None):
        """Generic pooled/retried call against any HEKB route. Returns the
        parsed JSON body. This is the only way this client talks to HEKB
        today — no route-specific method commits to a payload shape."""
        response = await request_with_retry(method, self.base_url, path, json=json)
        response.raise_for_status()
        return response.json()

    # TODO(EXP-Ubuntu012, Semantic Mapping): implement
    #   async def store(self, knowledge_object: ...) -> HekbObject
    # once "Observation -> Meaning -> Knowledge -> HEKB" (Memory Adapter,
    # see feedback_sensos_v3_implementation_rules) is designed and agreed.
    # Not implemented in EXP-Ubuntu011 — Runtime infra only, no HEKB
    # business logic.
