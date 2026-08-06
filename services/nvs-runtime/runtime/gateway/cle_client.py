"""CLE (Categorical Lift Engine) client.

EXP-Ubuntu011 gave this client pooled/async HTTP, retry, timeout, batching —
proven against CLE's real API (`categorical-lift-engine/src/cle/api/router.py`:
GET /health, POST /lift, /pullback, /recover, /compress). EXP-Ubuntu012B adds
`lift()`, the Observation -> LiftRequest payload mapping (Semantic Mapping):
it wraps a meaning-space position vector in CLE's own existing wire shape
(`cle.api.models.LiftRequest` / `ConceptInput` / `MeaningStatePoint` — this
client stays a plain HTTP client, so that shape is reproduced as a dict here
rather than imported cross-repo) and posts it to the existing `/lift` route.
No new CLE algorithm, endpoint, or object model — `pullback()`/`recover()`/
`compress()` remain unimplemented; only `lift()` is EXP-Ubuntu012B's scope.
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

    async def lift(self, position: list[float]) -> dict[str, Any]:
        """Lift a meaning-space position vector through CLE's existing /lift.

        `position` is `ObserveResponse.geometry["position"]` (nvs-kernel's
        real coordinate array, EXP-Ubuntu012B). It is wrapped as one point
        in a single-state `ConceptInput` — CLE's existing minimal point-cloud
        shape (`cle.runtime.engine._coordinates_of` reads exactly one
        `.states[i].theta` per point) — with no subject/observer/knowledge
        context, since the Runtime does not have three-view data to offer
        yet; `LiftRequest` already defaults those to `None` for this case.
        Returns CLE's `LiftResponse` body verbatim.
        """
        concept = {"states": [{"theta": list(position)}]}
        return await self.call("POST", "/lift", json={"concept": concept})
