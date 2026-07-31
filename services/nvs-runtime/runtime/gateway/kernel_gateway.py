"""Kernel gateway — all Kernel communication MUST go through this module."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any

import httpx

from runtime.core.config import Settings, get_settings
from runtime.models.enums import ForwardStatus, RuntimeEventType
from runtime.abi.observation import EventKind, ObservationEvent, ObserveRequest, ObserveResponse

logger = logging.getLogger(__name__)

#: Runtime event types that get forwarded to the kernel as an Observation-ABI
#: event, and the EventKind they're recorded as. Every other RuntimeEventType
#: is a lifecycle/control-plane signal, not a Reality fact, and is skipped —
#: this preserves exactly what today's forwarding does, only fixing transport.
_FORWARDED_EVENT_KINDS: dict[RuntimeEventType, EventKind] = {
    RuntimeEventType.STATE_RAW: EventKind.OBSERVATION,
    RuntimeEventType.SEP_EXCITATION: EventKind.USER,
    RuntimeEventType.SEP_DISTURBANCE: EventKind.USER,
    RuntimeEventType.SEP_RAW: EventKind.USER,
}


def _string_attributes(payload: dict[str, Any]) -> dict[str, str]:
    """Coerce an arbitrary runtime payload into the kernel's dict[str, str]
    attributes shape, losslessly (non-string values are JSON-encoded)."""
    result: dict[str, str] = {}
    for key, value in payload.items():
        result[str(key)] = value if isinstance(value, str) else json.dumps(value, default=str)
    return result


def _timestamp_ns(envelope: dict[str, Any]) -> int:
    raw = envelope.get("timestamp")
    if raw:
        try:
            return int(datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp() * 1e9)
        except ValueError:
            pass
    return time.time_ns()


class KernelGateway:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.settings.nvs_kernel_url,
            timeout=self.settings.kernel_forward_timeout,
        )

    def health_check(self) -> bool:
        try:
            with self._client() as client:
                resp = client.get("/health")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def observe(self, request: ObserveRequest) -> ObserveResponse:
        """Forward an Observation ABI request to nvs-kernel's real /observe.

        Pure transport: no vocabulary translation happens here. `request`
        must already be Observation-ABI-conformant before this is called.
        """
        with self._client() as client:
            resp = client.post("/observe", json=request.model_dump(mode="json"))
            resp.raise_for_status()
            return ObserveResponse.model_validate(resp.json())

    def forward_runtime_event(self, envelope: dict[str, Any]) -> tuple[ForwardStatus, str | None]:
        """Forward a runtime envelope to the kernel via the real /observe contract.

        Only the event types in `_FORWARDED_EVENT_KINDS` are Reality facts;
        everything else (session lifecycle, narrative, control, heartbeat,
        error) is skipped, unchanged from prior behavior.
        """
        try:
            event_type = RuntimeEventType(envelope.get("event_type"))
        except ValueError:
            return ForwardStatus.SKIPPED, None

        kind = _FORWARDED_EVENT_KINDS.get(event_type)
        if kind is None:
            return ForwardStatus.SKIPPED, None

        payload = envelope.get("payload", {}) or {}
        request = ObserveRequest(
            session_id=str(envelope.get("session_id")),
            events=[
                ObservationEvent(
                    step=envelope.get("sequence_id", 0),
                    timestamp_ns=_timestamp_ns(envelope),
                    kind=kind,
                    text=str(payload.get("text", "")),
                    source=envelope.get("source_provider"),
                    agent_id=envelope.get("agent_id"),
                    attributes=_string_attributes(payload),
                )
            ],
        )
        try:
            response = self.observe(request)
        except httpx.HTTPError as exc:
            logger.warning("Kernel unavailable: %s", exc)
            return ForwardStatus.PENDING, None
        # TODO(RFC-SensOS21-Follow-up): ObserveResponse.control (tier/intervention)
        # is discarded here. RFC-SensOS21/22/23 define a Governance -> Goal ->
        # Directive -> Instruction chain; this is the likely future bridge from
        # Kernel Executive into that chain. Not wired up in this change.
        return ForwardStatus.FORWARDED, str(response.cycle)
