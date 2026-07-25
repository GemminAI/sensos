from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_generate_pipeline(client, mock_annotator):
    with patch(
        "runtime.services.pipeline.generate_narrative",
        new=AsyncMock(return_value=("Test narrative output.", "openai")),
    ):
        resp = client.post(
            "/runtime/generate",
            json={"article": "Sample article about semiconductor policy.", "origin": "us"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["state_hash"]
    assert data["narrative"] == "Test narrative output."
    assert "T10_epistemic_confidence" in data["tags"]
    assert data["subject_origin"] == "us"


def test_list_and_get_states(client, mock_annotator):
    with patch(
        "runtime.services.pipeline.generate_narrative",
        new=AsyncMock(return_value=("Another narrative.", "gemini")),
    ):
        create = client.post(
            "/runtime/generate",
            json={"article": "Japan energy transition report.", "origin": "jp"},
        )
    assert create.status_code == 201
    state_hash = create.json()["state_hash"]

    listing = client.get("/states")
    assert listing.status_code == 200
    items = listing.json()
    assert any(i["state_hash"] == state_hash for i in items)

    detail = client.get(f"/states/{state_hash}")
    assert detail.status_code == 200
    assert detail.json()["narrative"] == "Another narrative."


def test_get_state_not_found(client):
    resp = client.get("/states/nonexistenthash")
    assert resp.status_code == 404
