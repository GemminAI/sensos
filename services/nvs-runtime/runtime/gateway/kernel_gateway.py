"""Kernel gateway — all Kernel communication MUST go through this module."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx

from runtime.core.config import Settings, get_settings
from runtime.models.enums import ForwardStatus, RuntimeEventType

logger = logging.getLogger(__name__)


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

    def forward_event(self, envelope: dict[str, Any]) -> tuple[ForwardStatus, str | None]:
        event_type = envelope.get("event_type")
        if event_type == RuntimeEventType.SEP_CONTROL.value:
            return ForwardStatus.SKIPPED, None

        try:
            with self._client() as client:
                if event_type == RuntimeEventType.STATE_RAW.value:
                    return self._forward_ingest(client, envelope)
                if event_type in {
                    RuntimeEventType.SEP_EXCITATION.value,
                    RuntimeEventType.SEP_DISTURBANCE.value,
                    RuntimeEventType.SEP_RAW.value,
                }:
                    return self._forward_observation(client, envelope)
                if event_type == RuntimeEventType.NARRATIVE_APPEND.value:
                    return ForwardStatus.SKIPPED, None
            return ForwardStatus.SKIPPED, None
        except httpx.HTTPError as exc:
            logger.warning("Kernel unavailable: %s", exc)
            return ForwardStatus.PENDING, None

    def forward_observation(self, envelope: dict[str, Any]) -> tuple[ForwardStatus, str | None]:
        if envelope.get("event_type") == RuntimeEventType.SEP_CONTROL.value:
            return ForwardStatus.SKIPPED, None
        try:
            with self._client() as client:
                return self._forward_observation(client, envelope)
        except httpx.HTTPError as exc:
            logger.warning("Kernel observation forward failed: %s", exc)
            return ForwardStatus.PENDING, None

    def _forward_ingest(self, client: httpx.Client, envelope: dict[str, Any]) -> tuple[ForwardStatus, str | None]:
        payload = envelope.get("payload", {})
        vector = payload.get("vector", [])
        run_id = str(envelope.get("session_id", ""))[:8]
        body = {
            "run_id": run_id,
            "states": [{"vector": vector, "confidence": payload.get("confidence", 1.0)}],
            "context": {"session_id": str(envelope.get("session_id")), "agent_id": str(envelope.get("agent_id"))},
        }
        resp = client.post("/kernel/ingest", json=body)
        if resp.status_code >= 500:
            return ForwardStatus.PENDING, run_id
        resp.raise_for_status()
        data = resp.json()
        return ForwardStatus.FORWARDED, data.get("run_id", run_id)

    def _forward_observation(
        self, client: httpx.Client, envelope: dict[str, Any]
    ) -> tuple[ForwardStatus, str | None]:
        body = {
            "session_id": str(envelope.get("session_id")),
            "agent_id": str(envelope.get("agent_id")),
            "experiment_id": str(envelope.get("experiment_id")) if envelope.get("experiment_id") else None,
            "runtime_event": envelope,
            "sep_payload": envelope.get("payload"),
        }
        resp = client.post("/kernel/v2/observations", json=body)
        if resp.status_code >= 500:
            return ForwardStatus.PENDING, None
        if resp.status_code == 404:
            return ForwardStatus.PENDING, None
        resp.raise_for_status()
        data = resp.json()
        return ForwardStatus.FORWARDED, data.get("observation_id") or data.get("run_id")
