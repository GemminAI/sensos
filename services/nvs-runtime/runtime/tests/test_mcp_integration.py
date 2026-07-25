from runtime.mcp.tools import nvs_register_agent, nvs_query_events, nvs_create_session
from runtime.models.enums import AgentProvider
from unittest.mock import patch


def test_mcp_register_agent_integration(db_session, fake_redis):
    with patch("runtime.mcp.tools.db_session") as mock_db:
        mock_db.return_value.__enter__ = lambda s: db_session
        mock_db.return_value.__exit__ = lambda s, *a: None
        result = nvs_register_agent({"provider": "custom", "model": "test-model"})
    assert "agent_id" in result


def test_mcp_query_empty(db_session, fake_redis):
    from runtime.services.session_service import SessionService
    from runtime.models.schemas import SessionCreate
    from uuid import uuid4

    with patch("runtime.mcp.tools.db_session") as mock_db:
        mock_db.return_value.__enter__ = lambda s: db_session
        mock_db.return_value.__exit__ = lambda s, *a: None
        session = SessionService().create(db_session, SessionCreate())
        db_session.flush()
        result = nvs_query_events({"session_id": str(session.session_id)})
    assert result["count"] == 0
