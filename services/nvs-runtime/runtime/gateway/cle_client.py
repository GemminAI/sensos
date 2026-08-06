"""CLE (Categorical Lift Engine) client — transport-only extension point.

EXP-Ubuntu011 scope is the Runtime Transport Layer only: pooled/async HTTP,
retry, timeout, batching. This client proves that transport against CLE's
real API (verified against `categorical-lift-engine/src/cle/api/router.py`:
GET /health, POST /lift, /pullback, /recover, /compress) but does **not**
implement the Observation -> LiftRequest payload mapping — that is Semantic
Mapping, out of scope here and deferred to EXP-Ubuntu012+.

Do not call `lift()`/`pullback()`/`recover()`/`compress()` from the Worker
in this phase; only `health_check()` and the generic `call()` transport are
exercised today.
"""

from __future__ import annotations

from typing import Any

from runtime.core.config import Settings, get_settings
from runtime.gateway.http_pool import RetryExhaustedError, request_with_retry

_TRANSPORT_ERRORS = (RetryExhaustedError,)


class CLEClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def base_url(self) -> str:
        return self.settings.cle_url

    async def health_check(self) -> bool:
        try:
            response = await request_with_retry("GET", self.base_url, "/health")
            return response.status_code == 200
        except _TRANSPORT_ERRORS:
            return False

    async def call(self, method: str, path: str, *, json: dict[str, Any] | None = None):
        """Generic pooled/retried call against any CLE route. Returns the
        parsed JSON body. This is the only way this client talks to CLE
        today — no route-specific method commits to a payload shape."""
        response = await request_with_retry(method, self.base_url, path, json=json)
        response.raise_for_status()
        return response.json()

    # TODO(EXP-Ubuntu012, Semantic Mapping): implement
    #   async def lift(self, observation: ...) -> LiftResult
    # once the Observation -> LiftRequest(concept, subject_context,
    # observer_context, human_knowledge_context) mapping is designed and
    # agreed (see cle.api.models.LiftRequest). Not implemented in
    # EXP-Ubuntu011 — Runtime infra only, no CLE business logic.
