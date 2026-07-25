from unittest.mock import patch

from runtime.models.enums import ForwardStatus, RuntimeEventType


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_agent_session_event_flow(client, sep_payload):
    with patch(
        "runtime.services.event_service.KernelGateway.forward_event",
        return_value=(ForwardStatus.SKIPPED, None),
    ):
        agent_resp = client.post(
            "/api/v1/agents",
            json={"provider": "anthropic", "model": "claude-sonnet-4", "capabilities": ["sep.excitation"]},
        )
        assert agent_resp.status_code == 201
        agent_id = agent_resp.json()["agent_id"]

        session_resp = client.post("/api/v1/sessions", json={"label": "test", "participants": [agent_id]})
        assert session_resp.status_code == 201
        session_id = session_resp.json()["session_id"]

        exp_resp = client.post(f"/api/v1/sessions/{session_id}/experiments", json={"label": "sep-run"})
        assert exp_resp.status_code == 201

        event_resp = client.post(
            f"/api/v1/sessions/{session_id}/events",
            json={
                "event_type": RuntimeEventType.SEP_EXCITATION.value,
                "agent_id": agent_id,
                "source_provider": "anthropic",
                "payload": sep_payload,
            },
        )
        assert event_resp.status_code == 202
        assert event_resp.json()["accepted"] == 1

        query_resp = client.get(f"/api/v1/sessions/{session_id}/events")
        assert query_resp.status_code == 200
        assert len(query_resp.json()) == 1


def test_capabilities(client):
    resp = client.get("/api/v1/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert "nvs_emit_sep_event" in data["mcp_tools"]
    assert "nvs_forecast_transition" in data["layer3_stubs"]


def test_list_agents_and_ready(client):
    client.post("/api/v1/agents", json={"provider": "google", "model": "gemini-pro"})
    resp = client.get("/api/v1/agents")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    ready = client.get("/ready")
    assert ready.status_code == 200
    assert "checks" in ready.json()

