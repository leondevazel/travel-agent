import asyncio

import pytest

from travel_agent import orchestrator
from travel_agent.agents.base import AgentError, AgentUsage
from travel_agent.db import TripSessionState
from travel_agent.schemas import FlightCandidate, HotelCandidate, ItineraryDay, Message, TripBrief
from travel_agent.tools.amadeus_client import AmadeusAPIError


def _usage():
    return AgentUsage(input_tokens=10, output_tokens=5, latency_ms=12.0)


def _empty_session():
    return TripSessionState(
        id="s1", messages=[], trip_brief=None, flight_candidates=[], hotel_candidates=[], itinerary=[]
    )


async def test_first_turn_runs_all_agents(monkeypatch):
    new_brief = TripBrief(destination="Paris", origin="ICN", start_date="2026-11-01", end_date="2026-11-02", budget_usd=2000.0, interests=["art"], pace="balanced")
    flights = [FlightCandidate(carrier="KE", price_usd=800, departure_time="t1", arrival_time="t2", origin="ICN", destination="CDG", stops=0)]
    hotels = [HotelCandidate(name="H", price_usd_per_night=100, rating=4.0, address="Paris")]
    days = [ItineraryDay(day_number=1, date="2026-11-01", activities=["Louvre"], notes="")]

    async def fake_planner(client, messages, previous_brief):
        return new_brief, _usage()

    async def fake_flight(client, brief, amadeus):
        return flights, _usage()

    async def fake_hotel(client, brief, amadeus):
        return hotels, _usage()

    async def fake_itinerary(client, brief, flights_, hotels_, weather):
        assert flights_ == flights and hotels_ == hotels
        return days, _usage()

    async def fake_weather(destination, start_date, end_date):
        return [{"date": "2026-11-01", "temp_max_c": 10.0, "temp_min_c": 2.0, "condition": "clear"}]

    monkeypatch.setattr(orchestrator, "run_planner_agent", fake_planner)
    monkeypatch.setattr(orchestrator, "run_flight_agent", fake_flight)
    monkeypatch.setattr(orchestrator, "run_hotel_agent", fake_hotel)
    monkeypatch.setattr(orchestrator, "run_itinerary_agent", fake_itinerary)
    monkeypatch.setattr(orchestrator, "get_daily_summary", fake_weather)
    monkeypatch.setattr(orchestrator.metrics, "record_agent_call", lambda **kw: kw)

    result = await orchestrator.handle_turn(client=object(), amadeus=object(), session=_empty_session(), user_message="Plan a trip to Paris")

    assert result.trip_brief == new_brief
    assert result.flight_candidates == flights
    assert result.hotel_candidates == hotels
    assert result.itinerary == days
    assert result.warnings == []


async def test_pace_only_change_skips_flight_and_hotel(monkeypatch):
    previous_brief = TripBrief(destination="Paris", origin="ICN", start_date="2026-11-01", end_date="2026-11-02", budget_usd=2000.0, interests=["art"], pace="balanced")
    new_brief = previous_brief.model_copy(update={"pace": "relaxed"})
    cached_flights = [FlightCandidate(carrier="KE", price_usd=800, departure_time="t1", arrival_time="t2", origin="ICN", destination="CDG", stops=0)]
    cached_hotels = [HotelCandidate(name="H", price_usd_per_night=100, rating=4.0, address="Paris")]
    new_days = [ItineraryDay(day_number=1, date="2026-11-01", activities=["Louvre, slower pace"], notes="")]

    session = TripSessionState(
        id="s1", messages=[], trip_brief=previous_brief,
        flight_candidates=cached_flights, hotel_candidates=cached_hotels, itinerary=[],
    )

    async def fake_planner(client, messages, previous_brief_):
        return new_brief, _usage()

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("flight/hotel agent must not run when only pace changed")

    async def fake_itinerary(client, brief, flights_, hotels_, weather):
        assert flights_ == cached_flights
        assert hotels_ == cached_hotels
        return new_days, _usage()

    async def fake_weather(destination, start_date, end_date):
        return []

    monkeypatch.setattr(orchestrator, "run_planner_agent", fake_planner)
    monkeypatch.setattr(orchestrator, "run_flight_agent", fail_if_called)
    monkeypatch.setattr(orchestrator, "run_hotel_agent", fail_if_called)
    monkeypatch.setattr(orchestrator, "run_itinerary_agent", fake_itinerary)
    monkeypatch.setattr(orchestrator, "get_daily_summary", fake_weather)
    monkeypatch.setattr(orchestrator.metrics, "record_agent_call", lambda **kw: kw)

    result = await orchestrator.handle_turn(client=object(), amadeus=object(), session=session, user_message="2일차 느슨하게 바꿔줘")

    assert result.flight_candidates == cached_flights
    assert result.hotel_candidates == cached_hotels
    assert result.itinerary == new_days


async def test_flight_agent_failure_falls_back_to_cached_and_warns(monkeypatch):
    previous_brief = TripBrief(destination="Paris", origin="ICN", start_date="2026-11-01", end_date="2026-11-02", budget_usd=2000.0, interests=["art"], pace="balanced")
    new_brief = previous_brief.model_copy(update={"budget_usd": 1500.0})
    cached_flights = [FlightCandidate(carrier="KE", price_usd=800, departure_time="t1", arrival_time="t2", origin="ICN", destination="CDG", stops=0)]
    new_hotels = [HotelCandidate(name="H2", price_usd_per_night=90, rating=4.1, address="Paris")]

    session = TripSessionState(
        id="s1", messages=[], trip_brief=previous_brief,
        flight_candidates=cached_flights, hotel_candidates=[], itinerary=[],
    )

    async def fake_planner(client, messages, previous_brief_):
        return new_brief, _usage()

    async def failing_flight(client, brief, amadeus):
        raise AmadeusAPIError("rate limited")

    async def fake_hotel(client, brief, amadeus):
        return new_hotels, _usage()

    async def fake_itinerary(client, brief, flights_, hotels_, weather):
        return [], _usage()

    async def fake_weather(destination, start_date, end_date):
        return []

    monkeypatch.setattr(orchestrator, "run_planner_agent", fake_planner)
    monkeypatch.setattr(orchestrator, "run_flight_agent", failing_flight)
    monkeypatch.setattr(orchestrator, "run_hotel_agent", fake_hotel)
    monkeypatch.setattr(orchestrator, "run_itinerary_agent", fake_itinerary)
    monkeypatch.setattr(orchestrator, "get_daily_summary", fake_weather)
    monkeypatch.setattr(orchestrator.metrics, "record_agent_call", lambda **kw: kw)

    result = await orchestrator.handle_turn(client=object(), amadeus=object(), session=session, user_message="lower budget to 1500")

    assert result.flight_candidates == cached_flights
    assert result.hotel_candidates == new_hotels
    assert any("flight" in w for w in result.warnings)


async def test_agent_timeout_falls_back_without_failing_whole_turn(monkeypatch):
    previous_brief = None
    new_brief = TripBrief(destination="Tokyo", origin="ICN", start_date="2026-12-01", end_date="2026-12-03", budget_usd=1000.0, interests=[], pace="balanced")

    async def fake_planner(client, messages, previous_brief_):
        return new_brief, _usage()

    async def slow_flight(client, brief, amadeus):
        await asyncio.sleep(10)
        return [], _usage()

    async def fake_hotel(client, brief, amadeus):
        return [], _usage()

    async def fake_itinerary(client, brief, flights_, hotels_, weather):
        return [], _usage()

    async def fake_weather(destination, start_date, end_date):
        return []

    monkeypatch.setattr(orchestrator, "run_planner_agent", fake_planner)
    monkeypatch.setattr(orchestrator, "run_flight_agent", slow_flight)
    monkeypatch.setattr(orchestrator, "run_hotel_agent", fake_hotel)
    monkeypatch.setattr(orchestrator, "run_itinerary_agent", fake_itinerary)
    monkeypatch.setattr(orchestrator, "get_daily_summary", fake_weather)
    monkeypatch.setattr(orchestrator, "AGENT_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(orchestrator.metrics, "record_agent_call", lambda **kw: kw)

    result = await orchestrator.handle_turn(client=object(), amadeus=object(), session=_empty_session(), user_message="Plan a trip to Tokyo")

    assert result.flight_candidates == []
    assert any("flight" in w for w in result.warnings)


async def test_unrelated_message_does_not_rerun_specialists(monkeypatch):
    previous_brief = TripBrief(destination="Paris", origin="ICN", start_date="2026-11-01", end_date="2026-11-02", budget_usd=2000.0, interests=["art"], pace="balanced")
    session = TripSessionState(
        id="s1", messages=[], trip_brief=previous_brief,
        flight_candidates=[], hotel_candidates=[], itinerary=[ItineraryDay(day_number=1, date="2026-11-01", activities=["Louvre"], notes="")],
    )

    async def fake_planner(client, messages, previous_brief_):
        return previous_brief, _usage()

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("no specialist agent should run when the brief is unchanged")

    monkeypatch.setattr(orchestrator, "run_planner_agent", fake_planner)
    monkeypatch.setattr(orchestrator, "run_flight_agent", fail_if_called)
    monkeypatch.setattr(orchestrator, "run_hotel_agent", fail_if_called)
    monkeypatch.setattr(orchestrator, "run_itinerary_agent", fail_if_called)
    monkeypatch.setattr(orchestrator.metrics, "record_agent_call", lambda **kw: kw)

    result = await orchestrator.handle_turn(client=object(), amadeus=object(), session=session, user_message="thanks!")

    assert result.itinerary == session.itinerary
