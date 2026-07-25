import httpx
import pytest

from runtime.gateway.kernel_gateway import KernelGateway
from runtime.models.enums import ForwardStatus, RuntimeEventType


def test_forward_event_kernel_unavailable():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)
    gateway = KernelGateway()
    with httpx.Client(transport=transport, base_url="http://kernel") as _:
        gateway.settings.nvs_kernel_url = "http://kernel"
        original = gateway._client

        def mock_client():
            return httpx.Client(transport=transport, base_url="http://kernel", timeout=5.0)

        gateway._client = mock_client
        status, ref = gateway.forward_event(
            {
                "event_type": RuntimeEventType.SEP_EXCITATION.value,
                "session_id": "sess-1",
                "agent_id": "agent-1",
                "payload": {"sep_version": "nvs.sep.event.v1", "event_type": "excitation.step"},
            }
        )
        gateway._client = original
    assert status == ForwardStatus.PENDING
    assert ref is None


def test_sep_control_skipped():
    gateway = KernelGateway()
    status, ref = gateway.forward_event({"event_type": RuntimeEventType.SEP_CONTROL.value})
    assert status == ForwardStatus.SKIPPED
    assert ref is None


def test_forward_observation_success():
    def handler(request):
        return httpx.Response(200, json={"observation_id": "obs-123", "run_id": "run-abc"})

    transport = httpx.MockTransport(handler)
    gateway = KernelGateway()

    def mock_client():
        return httpx.Client(transport=transport, base_url="http://kernel", timeout=5.0)

    gateway._client = mock_client
    status, ref = gateway.forward_observation(
        {
            "event_type": RuntimeEventType.SEP_EXCITATION.value,
            "session_id": "550e8400-e29b-41d4-a716-446655440001",
            "agent_id": "550e8400-e29b-41d4-a716-446655440002",
            "payload": {"event_type": "excitation.step"},
        }
    )
    assert status == ForwardStatus.FORWARDED
    assert ref == "obs-123"
