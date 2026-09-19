"""End-to-end multi-turn test over the real HTTP endpoints.

Only the four agent functions and the weather lookup are faked; the real
orchestrator (diff -> selective rerun -> persistence) and the real DB layer
run, so this covers "only rerun what changed" across a full round-trip.
"""

import pytest
from fastapi.testclient import TestClient

from travel_agent import db, main, orchestrator
from travel_agent.agents.base import AgentUsage
from travel_agent.schemas import FlightCandidate, HotelCandidate, ItineraryDay, TripBrief

BASE_BRIEF = TripBrief(
    destination="Paris",
    origin="ICN",
    start_date="2026-11-01",
    end_date="2026-11-03",
    budget_usd=2000.0,
    interests=["art"],
    pace="balanced",
)
RELAXED_BRIEF = BASE_BRIEF.model_copy(update={"pace": "relaxed"})

FLIGHTS = [
    FlightCandidate(
        carrier="KE", price_usd=812.5, departure_time="t1", arrival_time="t2",
        origin="ICN", destination="CDG", stops=0,
    )
]
HOTELS = [HotelCandidate(name="Hotel Lumiere", price_usd_per_night=180.0, rating=4.3, address="Paris")]
BALANCED_DAYS = [ItineraryDay(day_number=1, date="2026-11-01", activities=["Louvre", "Musee d'Orsay"], notes="")]
RELAXED_DAYS = [ItineraryDay(day_number=1, date="2026-11-01", activities=["Louvre"], notes="relaxed pace")]


def _usage():
    return AgentUsage(input_tokens=10, output_tokens=5, latency_ms=1.0)


@pytest.fixture
def api_client(db_ready):
    return TestClient(main.app)


@pytest.fixture
def fake_agents(monkeypatch):
    calls = {"flight": 0, "hotel": 0, "itinerary": 0}
    briefs = iter([BASE_BRIEF, RELAXED_BRIEF])

    async def fake_planner(client, messages, previous_brief):
        return next(briefs), _usage()

    async def fake_flight(client, brief):
        calls["flight"] += 1
        return FLIGHTS, _usage()

    async def fake_hotel(client, brief):
        calls["hotel"] += 1
        return HOTELS, _usage()

    async def fake_itinerary(client, brief, flights_, hotels_, weather):
        calls["itinerary"] += 1
        return (RELAXED_DAYS if brief.pace == "relaxed" else BALANCED_DAYS), _usage()

    async def fake_weather(destination, start_date, end_date):
        return []

    monkeypatch.setattr(orchestrator, "run_planner_agent", fake_planner)
    monkeypatch.setattr(orchestrator, "run_flight_agent", fake_flight)
    monkeypatch.setattr(orchestrator, "run_hotel_agent", fake_hotel)
    monkeypatch.setattr(orchestrator, "run_itinerary_agent", fake_itinerary)
    monkeypatch.setattr(orchestrator, "get_daily_summary", fake_weather)
    return calls


def test_pace_only_second_turn_reuses_flight_and_hotel_results(api_client, fake_agents, tmp_path, monkeypatch):
    monkeypatch.setattr("travel_agent.metrics.METRICS_PATH", tmp_path / "metrics.jsonl")

    session_id = api_client.post("/sessions").json()["session_id"]

    first = api_client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "Plan 3 days in Paris from Seoul, Nov 1-3, budget 2000, I like art"},
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["trip_brief"]["pace"] == "balanced"
    assert len(first_body["flight_candidates"]) == 1
    assert fake_agents == {"flight": 1, "hotel": 1, "itinerary": 1}

    second = api_client.post(f"/sessions/{session_id}/messages", json={"content": "make it more relaxed"})
    assert second.status_code == 200
    second_body = second.json()

    # (a) itinerary reflects the new pace; flight/hotel candidates unchanged.
    assert second_body["trip_brief"]["pace"] == "relaxed"
    assert second_body["itinerary"][0]["notes"] == "relaxed pace"
    assert second_body["flight_candidates"] == first_body["flight_candidates"]
    assert second_body["hotel_candidates"] == first_body["hotel_candidates"]

    # (b) flight/hotel agents were not re-invoked on turn 2.
    assert fake_agents == {"flight": 1, "hotel": 1, "itinerary": 2}

    # (c) persisted state reflects both turns.
    state = db.load_session(session_id)
    assert [m.role for m in state.messages] == ["user", "assistant", "user", "assistant"]
    assert state.messages[2].content == "make it more relaxed"
    assert state.trip_brief == RELAXED_BRIEF
    assert state.itinerary == RELAXED_DAYS
    assert state.flight_candidates == FLIGHTS
    assert state.hotel_candidates == HOTELS
