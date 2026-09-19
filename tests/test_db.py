import datetime

import pytest

from travel_agent.db import create_session, load_session, save_session
from travel_agent.schemas import FlightCandidate, HotelCandidate, ItineraryDay, Message, TripBrief


def test_create_and_load_empty_session(db_ready):
    create_session("sess-1")
    state = load_session("sess-1")
    assert state.id == "sess-1"
    assert state.messages == []
    assert state.trip_brief is None
    assert state.flight_candidates == []


def test_load_missing_session_returns_none(db_ready):
    assert load_session("does-not-exist") is None


def test_save_and_reload_full_session(db_ready):
    create_session("sess-2")
    messages = [Message(role="user", content="Plan a trip to Paris")]
    brief = TripBrief(destination="Paris", origin="ICN", budget_usd=2000.0, interests=["art"], pace="balanced")
    flights = [FlightCandidate(carrier="KE", price_usd=800.0, departure_time="t1", arrival_time="t2", origin="ICN", destination="CDG", stops=0)]
    hotels = [HotelCandidate(name="Hotel Lumiere", price_usd_per_night=150.0, rating=4.2, address="Paris")]
    itinerary = [ItineraryDay(day_number=1, date=datetime.date(2026, 11, 1), locations=["Louvre"], activities=["Louvre"], notes="")]

    save_session(
        "sess-2",
        messages=messages,
        trip_brief=brief,
        flight_candidates=flights,
        hotel_candidates=hotels,
        itinerary=itinerary,
    )

    state = load_session("sess-2")
    assert state.messages == messages
    assert state.trip_brief == brief
    assert state.flight_candidates == flights
    assert state.hotel_candidates == hotels
    assert state.itinerary == itinerary


def test_save_missing_session_raises_keyerror(db_ready):
    with pytest.raises(KeyError):
        save_session(
            "never-created",
            messages=[],
            trip_brief=TripBrief(),
            flight_candidates=[],
            hotel_candidates=[],
            itinerary=[],
        )
