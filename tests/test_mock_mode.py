import pytest
from fastapi.testclient import TestClient

from travel_agent import main
from travel_agent.config import settings


@pytest.fixture
def api_client(db_ready):
    return TestClient(main.app)


def test_mock_mode_returns_a_trip_without_calling_any_agent(api_client, monkeypatch):
    monkeypatch.setattr(settings, "mock_mode", True)

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("mock mode must not reach the orchestrator (that costs money)")

    monkeypatch.setattr(main, "handle_turn", fail_if_called)

    session_id = api_client.post("/sessions").json()["session_id"]
    resp = api_client.post(f"/sessions/{session_id}/messages", json={"content": "Plan Seoul"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["itinerary"]) == 3
    # Multi-location days are what the photo journey needs.
    assert all(len(day["locations"]) >= 2 for day in body["itinerary"])
    assert any("MOCK" in w for w in body["warnings"])


def test_mock_mode_off_by_default():
    assert settings.mock_mode is False
