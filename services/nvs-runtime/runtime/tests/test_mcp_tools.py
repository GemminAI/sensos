import pytest
from runtime.mcp import tools as mcp_tools
from runtime.mcp.tools import stub_response


def test_forecast_stub():
    result = stub_response("nvs_forecast_transition")
    assert result == {"status": "NOT_IMPLEMENTED", "rfc": "RFC-NVS30"}


def test_integrity_stub():
    result = stub_response("nvs_check_integrity")
    assert result["status"] == "NOT_IMPLEMENTED"
    assert result["rfc"] == "RFC-NVS31"


def test_alignment_stub():
    result = stub_response("nvs_get_alignment_profile")
    assert result["rfc"] == "RFC-NVS32"


def test_boundary_stub():
    result = stub_response("nvs_check_boundary_status")
    assert result["rfc"] == "RFC-NVS33"


# ---------------------------------------------------------------------------
# 38-Port capability tools — mocked at the gateway/hekb-client boundary,
# same fake-object convention as test_forward_worker.py's _FakeGateway/
# _FakeHekb (not mocked HTTP transport here, since these tool functions
# don't own transport directly — KernelGateway/HekbClient do, and that
# transport is already covered by test_kernel_gateway.py /
# test_extension_point_clients.py).
# ---------------------------------------------------------------------------


class _FakeGateway:
    def __init__(self, capability=None, invoke_result=None, fail=False):
        self.capability_calls: list[str] = []
        self.invoke_calls: list[tuple[str, dict]] = []
        self._capability = capability
        self._invoke_result = invoke_result
        self._fail = fail

    async def get_port_capability(self, port_id: str) -> dict:
        self.capability_calls.append(port_id)
        if self._fail:
            raise ValueError(f"invalid port_id {port_id!r}")
        return self._capability

    async def invoke_port(self, port_id: str, body: dict) -> dict:
        self.invoke_calls.append((port_id, body))
        if self._fail:
            from runtime.gateway.http_pool import RetryExhaustedError

            raise RetryExhaustedError(f"simulated failure for {port_id}")
        return self._invoke_result


class _FakeHekb:
    def __init__(self, fail=False):
        self.calls: list[dict] = []
        self._fail = fail

    async def store(self, knowledge_object: dict) -> dict:
        if self._fail:
            from runtime.gateway.http_pool import RetryExhaustedError

            raise RetryExhaustedError("simulated HEKB failure")
        self.calls.append(knowledge_object)
        return {"object_id": "a" * 64, "hash": "a" * 64, "timestamp": "2026-08-06T00:00:00Z"}


_REAL_P04_RESULT = {
    "port_id": "P04_Port",
    "capability": "core_c04_hext_closure_verifier",
    "status": "OK",
    "result": {"quantized_once": [1.0, 2.0, 3.0], "residual": 0.0, "closed": True},
}
_REAL_P04_CAPABILITY = {
    "type": "port",
    "id": "P04_Port",
    "status": "IMPLEMENTED",
    "capabilities": ["core_c04_hext_closure_verifier"],
}


async def test_get_port_capability_tool_delegates_to_gateway(monkeypatch):
    fake = _FakeGateway(capability=_REAL_P04_CAPABILITY)
    monkeypatch.setattr(mcp_tools, "_kernel_gateway", fake)

    result = await mcp_tools.nvs_get_port_capability({"port_id": "P04"})

    assert fake.capability_calls == ["P04"]
    assert result == _REAL_P04_CAPABILITY


async def test_invoke_port_tool_delegates_to_gateway(monkeypatch):
    fake = _FakeGateway(invoke_result=_REAL_P04_RESULT)
    monkeypatch.setattr(mcp_tools, "_kernel_gateway", fake)

    result = await mcp_tools.nvs_invoke_port({"port_id": "P04", "body": {"vector": [1.0, 2.0, 3.0]}})

    assert fake.invoke_calls == [("P04", {"vector": [1.0, 2.0, 3.0]})]
    assert result == _REAL_P04_RESULT


async def test_invoke_port_tool_defaults_body_to_empty_dict(monkeypatch):
    fake = _FakeGateway(invoke_result=_REAL_P04_RESULT)
    monkeypatch.setattr(mcp_tools, "_kernel_gateway", fake)

    await mcp_tools.nvs_invoke_port({"port_id": "P04"})

    assert fake.invoke_calls == [("P04", {})]


async def test_persist_port_evidence_tool_invokes_and_stores(monkeypatch):
    fake_gateway = _FakeGateway(invoke_result=_REAL_P04_RESULT)
    fake_hekb = _FakeHekb()
    monkeypatch.setattr(mcp_tools, "_kernel_gateway", fake_gateway)
    monkeypatch.setattr(mcp_tools, "_hekb_client", fake_hekb)

    result = await mcp_tools.nvs_persist_port_evidence(
        {"port_id": "P04", "body": {"vector": [1.0]}, "session_id": "sess-1", "cycle": 3}
    )

    assert fake_gateway.invoke_calls == [("P04", {"vector": [1.0]})]
    assert len(fake_hekb.calls) == 1
    assert fake_hekb.calls[0]["kind"] == "EVIDENCE"
    assert fake_hekb.calls[0]["labels"]["port_id"] == "P04"
    assert fake_hekb.calls[0]["labels"]["session_id"] == "sess-1"
    assert fake_hekb.calls[0]["labels"]["cycle"] == "3"
    assert result["object_id"] == "a" * 64


async def test_persist_port_evidence_tool_omits_session_and_cycle_when_absent(monkeypatch):
    fake_gateway = _FakeGateway(invoke_result=_REAL_P04_RESULT)
    fake_hekb = _FakeHekb()
    monkeypatch.setattr(mcp_tools, "_kernel_gateway", fake_gateway)
    monkeypatch.setattr(mcp_tools, "_hekb_client", fake_hekb)

    await mcp_tools.nvs_persist_port_evidence({"port_id": "P04", "body": {}})

    assert "session_id" not in fake_hekb.calls[0]["labels"]
    assert "cycle" not in fake_hekb.calls[0]["labels"]


async def test_persist_port_evidence_tool_invoke_failure_propagates(monkeypatch):
    from runtime.gateway.http_pool import RetryExhaustedError

    fake_gateway = _FakeGateway(fail=True)
    fake_hekb = _FakeHekb()
    monkeypatch.setattr(mcp_tools, "_kernel_gateway", fake_gateway)
    monkeypatch.setattr(mcp_tools, "_hekb_client", fake_hekb)

    with pytest.raises(RetryExhaustedError):
        await mcp_tools.nvs_persist_port_evidence({"port_id": "P04", "body": {}})
    assert fake_hekb.calls == []


async def test_persist_port_evidence_tool_hekb_unavailable_propagates(monkeypatch):
    from runtime.gateway.http_pool import RetryExhaustedError

    fake_gateway = _FakeGateway(invoke_result=_REAL_P04_RESULT)
    fake_hekb = _FakeHekb(fail=True)
    monkeypatch.setattr(mcp_tools, "_kernel_gateway", fake_gateway)
    monkeypatch.setattr(mcp_tools, "_hekb_client", fake_hekb)

    with pytest.raises(RetryExhaustedError):
        await mcp_tools.nvs_persist_port_evidence({"port_id": "P04", "body": {}})
