import httpx
import pytest

from runtime.gateway import http_pool
from runtime.gateway.kernel_gateway import KernelGateway
from runtime.models.enums import ForwardStatus, RuntimeEventType
from runtime.abi.observation import EventKind, ObservationEvent, ObserveRequest


def _mock_pooled_client(monkeypatch, handler):
    """EXP-Ubuntu011: KernelGateway now goes through http_pool's cached
    AsyncClient instead of opening a per-call httpx.Client — patch the pool
    factory itself so every gateway call in a test hits the same mock
    transport, regardless of how many times get_pooled_client() is called."""
    transport = httpx.MockTransport(handler)

    async def fake_get_pooled_client(base_url, profile=None):
        return httpx.AsyncClient(transport=transport, base_url=base_url)

    monkeypatch.setattr(http_pool, "get_pooled_client", fake_get_pooled_client)


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


async def test_forward_runtime_event_kernel_unavailable(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    _mock_pooled_client(monkeypatch, handler)
    gateway = KernelGateway()

    status, ref = await gateway.forward_runtime_event(
        {
            "event_type": RuntimeEventType.SEP_EXCITATION.value,
            "session_id": "sess-1",
            "agent_id": "agent-1",
            "payload": {"sep_version": "nvs.sep.event.v1", "event_type": "excitation.step"},
        }
    )
    assert status == ForwardStatus.PENDING
    assert ref is None


async def test_sep_control_skipped_no_http_call(monkeypatch):
    calls: list[str] = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={})

    _mock_pooled_client(monkeypatch, handler)
    gateway = KernelGateway()

    status, ref = await gateway.forward_runtime_event({"event_type": RuntimeEventType.SEP_CONTROL.value})
    assert status == ForwardStatus.SKIPPED
    assert ref is None
    assert calls == []


async def test_narrative_append_skipped_no_http_call(monkeypatch):
    calls: list[str] = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={})

    _mock_pooled_client(monkeypatch, handler)
    gateway = KernelGateway()

    status, ref = await gateway.forward_runtime_event({"event_type": RuntimeEventType.NARRATIVE_APPEND.value})
    assert status == ForwardStatus.SKIPPED
    assert ref is None
    assert calls == []


async def test_forward_runtime_event_state_raw_uses_observation_kind(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return _mock_observe_response_handler(request)

    _mock_pooled_client(monkeypatch, handler)
    gateway = KernelGateway()

    status, ref = await gateway.forward_runtime_event(
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


async def test_forward_runtime_event_sep_excitation_uses_user_kind(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["json"] = json.loads(request.content)
        return _mock_observe_response_handler(request)

    _mock_pooled_client(monkeypatch, handler)
    gateway = KernelGateway()

    status, ref = await gateway.forward_runtime_event(
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


async def test_observe_sends_observation_abi_shape(monkeypatch):
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

    _mock_pooled_client(monkeypatch, handler)
    gateway = KernelGateway()

    response = await gateway.observe(_sample_observe_request())

    assert captured["path"] == "/observe"
    assert captured["json"]["session_id"] == "demo"
    assert captured["json"]["events"][0]["kind"] == "THOUGHT"
    assert captured["json"]["adapter"] == "generic"
    assert response.session_id == "demo"
    assert response.cycle == 1
    assert response.control.tier_label == "L0"
    assert response.control.actionable is False


async def test_observe_propagates_kernel_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": "DimensionMismatchError", "detail": "bad vector"})

    _mock_pooled_client(monkeypatch, handler)
    gateway = KernelGateway()

    with pytest.raises(httpx.HTTPStatusError):
        await gateway.observe(_sample_observe_request())


async def test_observe_batch_sends_multiple_events_in_one_request(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["json"] = json.loads(request.content)
        return _mock_observe_response_handler(request)

    _mock_pooled_client(monkeypatch, handler)
    gateway = KernelGateway()

    events = [
        ObservationEvent(step=0, timestamp_ns=0, kind=EventKind.OBSERVATION, text="a"),
        ObservationEvent(step=1, timestamp_ns=1, kind=EventKind.OBSERVATION, text="b"),
    ]
    response = await gateway.observe_batch("demo", events)

    assert len(captured["json"]["events"]) == 2
    assert response.cycle == 7


async def test_invoke_port_stateless_posts_raw_fields_to_port_url(monkeypatch):
    """Stateless Port shape, verbatim from the real captured evidence
    (EXP-TRJ-38PORT-SEMANTIC-PERTURBATION-001/code/collector.py's
    STATELESS["P04"]): body is the raw feature fields, no session_id."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"port_id": "P04", "result": {"c04": 0.42}})

    _mock_pooled_client(monkeypatch, handler)
    gateway = KernelGateway()

    result = await gateway.invoke_port("P04", {"vector": [1.0, 2.0, 3.0]})

    assert captured["path"] == "/ports/P04_Port/invoke"
    assert captured["json"] == {"vector": [1.0, 2.0, 3.0]}
    assert result == {"port_id": "P04", "result": {"c04": 0.42}}


async def test_invoke_port_session_scoped_includes_session_id(monkeypatch):
    """Session-scoped Port shape, verbatim from the real captured evidence
    (same source, SESSION_SCOPED["P02"]): body is {"session_id", **extra}."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["path"] = request.url.path
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"port_id": "P02", "result": {"c02": 0.1}})

    _mock_pooled_client(monkeypatch, handler)
    gateway = KernelGateway()

    result = await gateway.invoke_port("P02", {"session_id": "demo", "epsilon": 0.5})

    assert captured["path"] == "/ports/P02_Port/invoke"
    assert captured["json"] == {"session_id": "demo", "epsilon": 0.5}
    assert result == {"port_id": "P02", "result": {"c02": 0.1}}


async def test_invoke_port_appends_port_suffix_for_any_port_id(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json={})

    _mock_pooled_client(monkeypatch, handler)
    gateway = KernelGateway()

    await gateway.invoke_port("P38", {})
    assert captured["path"] == "/ports/P38_Port/invoke"


async def test_invoke_port_propagates_kernel_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": "InvalidPortRequest"})

    _mock_pooled_client(monkeypatch, handler)
    gateway = KernelGateway()

    with pytest.raises(httpx.HTTPStatusError):
        await gateway.invoke_port("P04", {"vector": [1.0]})


@pytest.mark.parametrize("port_id", ["P01", "P09", "P10", "P17", "P38"])
async def test_invoke_port_accepts_valid_ssot_boundaries(monkeypatch, port_id):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    _mock_pooled_client(monkeypatch, handler)
    gateway = KernelGateway()

    await gateway.invoke_port(port_id, {})  # must not raise


@pytest.mark.parametrize(
    "port_id",
    ["P00", "P39", "P99", "P1", "p17", "P17X", "", "P017", "17", "Q17"],
)
async def test_invoke_port_rejects_invalid_port_id_before_any_http_call(monkeypatch, port_id):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={})

    _mock_pooled_client(monkeypatch, handler)
    gateway = KernelGateway()

    with pytest.raises(ValueError, match="port_id"):
        await gateway.invoke_port(port_id, {})
    assert calls == []  # rejected client-side, before any HTTP request


# ---------------------------------------------------------------------------
# get_port_capability — capability_available? boundary (GET /ports/{id}_Port)
# ---------------------------------------------------------------------------

_REAL_P04_CAPABILITY = {
    "type": "port",
    "id": "P04_Port",
    "layer": "CORE",
    "name": "HEXT Closure Verifier",
    "version": "1.0.0",
    "status": "IMPLEMENTED",
    "input": {"type": "CoreInvokeRequest", "schema_uri": None},
    "output": {"type": "Core.C04.ClosureResult", "schema_uri": None},
    "capabilities": ["core_c04_hext_closure_verifier"],
    "provider": {"implementation": "nvs-kernel-v5", "abi_version": "5.0.0"},
    "invoke_endpoints": ["POST /ports/{port_id}/invoke"],
}


async def test_get_port_capability_uses_get_method_on_port_url(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        return httpx.Response(200, json=_REAL_P04_CAPABILITY)

    _mock_pooled_client(monkeypatch, handler)
    gateway = KernelGateway()

    result = await gateway.get_port_capability("P04")

    assert captured["method"] == "GET"
    assert captured["path"] == "/ports/P04_Port"
    assert result == _REAL_P04_CAPABILITY


async def test_get_port_capability_rejects_invalid_port_id_before_any_http_call(monkeypatch):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={})

    _mock_pooled_client(monkeypatch, handler)
    gateway = KernelGateway()

    with pytest.raises(ValueError, match="port_id"):
        await gateway.get_port_capability("P99")
    assert calls == []


async def test_get_port_capability_propagates_kernel_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "unknown port"})

    _mock_pooled_client(monkeypatch, handler)
    gateway = KernelGateway()

    with pytest.raises(httpx.HTTPStatusError):
        await gateway.get_port_capability("P04")
