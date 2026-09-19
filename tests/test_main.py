import pytest
from fastapi.testclient import TestClient

from travel_agent import main
from travel_agent.orchestrator import TurnResult
from travel_agent.schemas import TripBrief


@pytest.fixture
def api_client(db_ready):
    return TestClient(main.app)


def test_create_session_returns_id(api_client):
    resp = api_client.post("/sessions")
    assert resp.status_code == 201
    assert "session_id" in resp.json()


def test_post_message_to_missing_session_returns_404(api_client):
    resp = api_client.post("/sessions/does-not-exist/messages", json={"content": "hi"})
    assert resp.status_code == 404


async def test_post_message_returns_turn_result(api_client, monkeypatch):
    create_resp = api_client.post("/sessions")
    session_id = create_resp.json()["session_id"]

    fake_result = TurnResult(
        reply="Here's your plan.",
        trip_brief=TripBrief(destination="Paris", interests=[]),
        flight_candidates=[],
        hotel_candidates=[],
        itinerary=[],
        warnings=["couldn't fetch live flight data right now"],
    )

    async def fake_handle_turn(client, amadeus, session, user_message):
        assert user_message == "Plan a trip to Paris"
        return fake_result

    monkeypatch.setattr(main, "handle_turn", fake_handle_turn)

    resp = api_client.post(f"/sessions/{session_id}/messages", json={"content": "Plan a trip to Paris"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "Here's your plan."
    assert body["trip_brief"]["destination"] == "Paris"
    assert body["warnings"] == ["couldn't fetch live flight data right now"]
