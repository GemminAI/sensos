import httpx
import pytest

from runtime.gateway.kernel_gateway import KernelGateway
from runtime.models.enums import ForwardStatus, RuntimeEventType
from runtime.abi.observation import EventKind, ObservationEvent, ObserveRequest


def _mock_observe_response_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "session_id": "demo",
            "cycle": 7,
            "control": {
                "tier": 0,
                "tier_label": "L0",
                "intervention": "MONITOR",
                "actionable": False,
                "requires_approval": False,
                "authorized": True,
                "reason": "steady at L0",
            },
        },
    )


def test_forward_runtime_event_kernel_unavailable():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)
    gateway = KernelGateway()
    gateway._client = lambda: httpx.Client(transport=transport, base_url="http://kernel", timeout=5.0)

    status, ref = gateway.forward_runtime_event(
        {
            "event_type": RuntimeEventType.SEP_EXCITATION.value,
            "session_id": "sess-1",
            "agent_id": "agent-1",
            "payload": {"sep_version": "nvs.sep.event.v1", "event_type": "excitation.step"},
        }
    )
    assert status == ForwardStatus.PENDING
    assert ref is None


def test_sep_control_skipped_no_http_call():
    calls: list[str] = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={})

    gateway = KernelGateway()
    gateway._client = lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url="http://kernel", timeout=5.0)

    status, ref = gateway.forward_runtime_event({"event_type": RuntimeEventType.SEP_CONTROL.value})
    assert status == ForwardStatus.SKIPPED
    assert ref is None
    assert calls == []


def test_narrative_append_skipped_no_http_call():
    calls: list[str] = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={})

    gateway = KernelGateway()
    gateway._client = lambda: httpx.Client(transport=httpx.MockTransport(handler), base_url="http://kernel", timeout=5.0)

    status, ref = gateway.forward_runtime_event({"event_type": RuntimeEventType.NARRATIVE_APPEND.value})
    assert status == ForwardStatus.SKIPPED
    assert ref is None
    assert calls == []


def test_forward_runtime_event_state_raw_uses_observation_kind():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return _mock_observe_response_handler(request)

    transport = httpx.MockTransport(handler)
    gateway = KernelGateway()
    gateway._client = lambda: httpx.Client(transport=transport, base_url="http://kernel", timeout=5.0)

    status, ref = gateway.forward_runtime_event(
        {
            "event_type": RuntimeEventType.STATE_RAW.value,
            "session_id": "550e8400-e29b-41d4-a716-446655440001",
            "agent_id": "550e8400-e29b-41d4-a716-446655440002",
            "sequence_id": 3,
            "payload": {"text": "raw state sample"},
        }
    )
    assert captured["path"] == "/observe"
    assert captured["json"]["events"][0]["kind"] == "OBSERVATION"
    assert status == ForwardStatus.FORWARDED
    assert ref == "7"


def test_forward_runtime_event_sep_excitation_uses_user_kind():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["json"] = json.loads(request.content)
        return _mock_observe_response_handler(request)

    transport = httpx.MockTransport(handler)
    gateway = KernelGateway()
    gateway._client = lambda: httpx.Client(transport=transport, base_url="http://kernel", timeout=5.0)

    status, ref = gateway.forward_runtime_event(
        {
            "event_type": RuntimeEventType.SEP_EXCITATION.value,
            "session_id": "550e8400-e29b-41d4-a716-446655440001",
            "agent_id": "550e8400-e29b-41d4-a716-446655440002",
            "payload": {"event_type": "excitation.step", "text": "injected excitation"},
        }
    )
    assert captured["json"]["events"][0]["kind"] == "USER"
    assert status == ForwardStatus.FORWARDED
    assert ref == "7"


def _sample_observe_request() -> ObserveRequest:
    return ObserveRequest(
        session_id="demo",
        events=[
            ObservationEvent(
                step=0,
                timestamp_ns=0,
                kind=EventKind.THOUGHT,
                text="deploy the service and check the logs",
                source="agent-runtime",
                agent_id="worker-1",
            )
        ],
    )


def test_observe_sends_observation_abi_shape():
    """KernelGateway.observe() must speak nvs-kernel's real /observe contract
    (session_id/events/adapter), not the old /kernel/ingest vocabulary."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "session_id": "demo",
                "cycle": 1,
                "control": {
                    "tier": 0,
                    "tier_label": "L0",
                    "intervention": "MONITOR",
                    "actionable": False,
                    "requires_approval": False,
                    "authorized": True,
                    "reason": "steady at L0; L0 below interlock gate",
                },
            },
        )

    transport = httpx.MockTransport(handler)
    gateway = KernelGateway()
    gateway._client = lambda: httpx.Client(transport=transport, base_url="http://kernel", timeout=5.0)

    response = gateway.observe(_sample_observe_request())

    assert captured["path"] == "/observe"
    assert captured["json"]["session_id"] == "demo"
    assert captured["json"]["events"][0]["kind"] == "THOUGHT"
    assert captured["json"]["adapter"] == "generic"
    assert response.session_id == "demo"
    assert response.cycle == 1
    assert response.control.tier_label == "L0"
    assert response.control.actionable is False


def test_observe_propagates_kernel_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": "DimensionMismatchError", "detail": "bad vector"})

    transport = httpx.MockTransport(handler)
    gateway = KernelGateway()
    gateway._client = lambda: httpx.Client(transport=transport, base_url="http://kernel", timeout=5.0)

    with pytest.raises(httpx.HTTPStatusError):
        gateway.observe(_sample_observe_request())
