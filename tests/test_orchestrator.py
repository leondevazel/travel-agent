import asyncio

import pytest

from travel_agent import orchestrator
from travel_agent.agents.base import AgentError, AgentUsage
from travel_agent.db import TripSessionState
from travel_agent.schemas import FlightCandidate, HotelCandidate, ItineraryDay, Message, TripBrief


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

    async def fake_flight(client, brief):
        return flights, _usage()

    async def fake_hotel(client, brief):
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

    result = await orchestrator.handle_turn(client=object(), session=_empty_session(), user_message="Plan a trip to Paris")

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

    result = await orchestrator.handle_turn(client=object(), session=session, user_message="2일차 느슨하게 바꿔줘")

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

    async def failing_flight(client, brief):
        raise AgentError("web search rate limited")

    async def fake_hotel(client, brief):
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

    result = await orchestrator.handle_turn(client=object(), session=session, user_message="lower budget to 1500")

    assert result.flight_candidates == cached_flights
    assert result.hotel_candidates == new_hotels
    assert any("flight" in w for w in result.warnings)


async def test_agent_timeout_falls_back_without_failing_whole_turn(monkeypatch):
    previous_brief = None
    new_brief = TripBrief(destination="Tokyo", origin="ICN", start_date="2026-12-01", end_date="2026-12-03", budget_usd=1000.0, interests=[], pace="balanced")

    async def fake_planner(client, messages, previous_brief_):
        return new_brief, _usage()

    async def slow_flight(client, brief):
        await asyncio.sleep(10)
        return [], _usage()

    async def fake_hotel(client, brief):
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

    result = await orchestrator.handle_turn(client=object(), session=_empty_session(), user_message="Plan a trip to Tokyo")

    assert result.flight_candidates == []
    assert any("flight" in w for w in result.warnings)


async def test_planner_failure_falls_back_to_previous_brief_and_warns(monkeypatch):
    previous_brief = TripBrief(destination="Paris", origin="ICN", start_date="2026-11-01", end_date="2026-11-02", budget_usd=2000.0, interests=["art"], pace="balanced")
    cached_flights = [FlightCandidate(carrier="KE", price_usd=800, departure_time="t1", arrival_time="t2", origin="ICN", destination="CDG", stops=0)]
    cached_hotels = [HotelCandidate(name="H", price_usd_per_night=100, rating=4.0, address="Paris")]
    cached_itinerary = [ItineraryDay(day_number=1, date="2026-11-01", activities=["Louvre"], notes="")]

    session = TripSessionState(
        id="s1", messages=[], trip_brief=previous_brief,
        flight_candidates=cached_flights, hotel_candidates=cached_hotels, itinerary=cached_itinerary,
    )

    async def failing_planner(client, messages, previous_brief_):
        raise AgentError("planner never produced a final tool call")

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("specialist agents must not run when planner fails")

    monkeypatch.setattr(orchestrator, "run_planner_agent", failing_planner)
    monkeypatch.setattr(orchestrator, "run_flight_agent", fail_if_called)
    monkeypatch.setattr(orchestrator, "run_hotel_agent", fail_if_called)
    monkeypatch.setattr(orchestrator, "run_itinerary_agent", fail_if_called)
    recorded = []
    monkeypatch.setattr(orchestrator.metrics, "record_agent_call", lambda **kw: recorded.append(kw))

    result = await orchestrator.handle_turn(client=object(), session=session, user_message="add more museums")

    assert result.trip_brief == previous_brief
    assert result.flight_candidates == cached_flights
    assert result.hotel_candidates == cached_hotels
    assert result.itinerary == cached_itinerary
    assert any("trip details" in w for w in result.warnings)
    planner_calls = [kw for kw in recorded if kw["agent_name"] == "planner"]
    assert len(planner_calls) == 1
    assert planner_calls[0]["success"] is False


async def test_planner_failure_on_new_session_falls_back_to_empty_brief(monkeypatch):
    async def failing_planner(client, messages, previous_brief_):
        raise AgentError("planner never produced a final tool call")

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("specialist agents must not run when planner fails on first turn")

    monkeypatch.setattr(orchestrator, "run_planner_agent", failing_planner)
    monkeypatch.setattr(orchestrator, "run_flight_agent", fail_if_called)
    monkeypatch.setattr(orchestrator, "run_hotel_agent", fail_if_called)
    monkeypatch.setattr(orchestrator, "run_itinerary_agent", fail_if_called)
    monkeypatch.setattr(orchestrator.metrics, "record_agent_call", lambda **kw: kw)

    result = await orchestrator.handle_turn(client=object(), session=_empty_session(), user_message="Plan a trip to Tokyo")

    assert result.trip_brief == TripBrief()
    assert result.flight_candidates == []
    assert result.hotel_candidates == []
    assert result.itinerary == []
    assert any("trip details" in w for w in result.warnings)


async def test_unrelated_message_does_not_rerun_specialists(monkeypatch):
    previous_brief = TripBrief(destination="Paris", origin="ICN", start_date="2026-11-01", end_date="2026-11-02", budget_usd=2000.0, interests=["art"], pace="balanced")
    session = TripSessionState(
        id="s1", messages=[], trip_brief=previous_brief,
        flight_candidates=[FlightCandidate(carrier="KE", price_usd=800, departure_time="t1", arrival_time="t2", origin="ICN", destination="CDG", stops=0)],
        hotel_candidates=[HotelCandidate(name="H", price_usd_per_night=100, rating=4.0, address="Paris")],
        itinerary=[ItineraryDay(day_number=1, date="2026-11-01", activities=["Louvre"], notes="")],
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

    result = await orchestrator.handle_turn(client=object(), session=session, user_message="thanks!")

    assert result.itinerary == session.itinerary


async def test_validation_error_from_agent_triggers_fallback_and_warning(monkeypatch):
    previous_brief = TripBrief(destination="Paris", origin="ICN", start_date="2026-11-01", end_date="2026-11-02", budget_usd=2000.0, interests=["art"], pace="balanced")
    new_brief = previous_brief.model_copy(update={"budget_usd": 1500.0})
    cached_flights = [FlightCandidate(carrier="KE", price_usd=800, departure_time="t1", arrival_time="t2", origin="ICN", destination="CDG", stops=0)]
    cached_hotels = [HotelCandidate(name="H", price_usd_per_night=100, rating=4.0, address="Paris")]

    session = TripSessionState(
        id="s1", messages=[], trip_brief=previous_brief,
        flight_candidates=cached_flights, hotel_candidates=cached_hotels, itinerary=[],
    )

    async def fake_planner(client, messages, previous_brief_):
        return new_brief, _usage()

    async def malformed_flight(client, brief):
        # What FlightCandidate(**c) raises when the LLM submits junk.
        FlightCandidate(carrier="KE")
        raise AssertionError("unreachable")

    async def fake_hotel(client, brief):
        return cached_hotels, _usage()

    async def fake_itinerary(client, brief, flights_, hotels_, weather):
        return [], _usage()

    async def fake_weather(destination, start_date, end_date):
        return []

    monkeypatch.setattr(orchestrator, "run_planner_agent", fake_planner)
    monkeypatch.setattr(orchestrator, "run_flight_agent", malformed_flight)
    monkeypatch.setattr(orchestrator, "run_hotel_agent", fake_hotel)
    monkeypatch.setattr(orchestrator, "run_itinerary_agent", fake_itinerary)
    monkeypatch.setattr(orchestrator, "get_daily_summary", fake_weather)
    recorded = []
    monkeypatch.setattr(orchestrator.metrics, "record_agent_call", lambda **kw: recorded.append(kw))

    result = await orchestrator.handle_turn(client=object(), session=session, user_message="lower budget")

    assert result.flight_candidates == cached_flights
    assert any("flight" in w for w in result.warnings)
    flight_calls = [kw for kw in recorded if kw["agent_name"] == "flight"]
    assert flight_calls[0]["success"] is False
    assert flight_calls[0]["error_type"] == "ValidationError"


async def test_key_error_from_agent_triggers_fallback_and_warning(monkeypatch):
    new_brief = TripBrief(destination="Tokyo", origin="ICN", start_date="2026-12-01", end_date="2026-12-03", budget_usd=1000.0, interests=[], pace="balanced")

    async def fake_planner(client, messages, previous_brief_):
        return new_brief, _usage()

    async def missing_key_flight(client, brief):
        return {"nope": 1}["candidates"], _usage()

    async def fake_hotel(client, brief):
        return [], _usage()

    async def fake_itinerary(client, brief, flights_, hotels_, weather):
        return [], _usage()

    async def fake_weather(destination, start_date, end_date):
        return []

    monkeypatch.setattr(orchestrator, "run_planner_agent", fake_planner)
    monkeypatch.setattr(orchestrator, "run_flight_agent", missing_key_flight)
    monkeypatch.setattr(orchestrator, "run_hotel_agent", fake_hotel)
    monkeypatch.setattr(orchestrator, "run_itinerary_agent", fake_itinerary)
    monkeypatch.setattr(orchestrator, "get_daily_summary", fake_weather)
    monkeypatch.setattr(orchestrator.metrics, "record_agent_call", lambda **kw: kw)

    result = await orchestrator.handle_turn(client=object(), session=_empty_session(), user_message="Plan Tokyo")

    assert result.flight_candidates == []
    assert any("flight" in w for w in result.warnings)


async def test_previously_failed_flight_agent_retries_on_unchanged_brief(monkeypatch):
    previous_brief = TripBrief(destination="Paris", origin="ICN", start_date="2026-11-01", end_date="2026-11-02", budget_usd=2000.0, interests=["art"], pace="balanced")
    cached_hotels = [HotelCandidate(name="H", price_usd_per_night=100, rating=4.0, address="Paris")]
    recovered_flights = [FlightCandidate(carrier="AF", price_usd=700, departure_time="t1", arrival_time="t2", origin="ICN", destination="CDG", stops=0)]

    # flight_candidates is empty because the flight agent failed on a prior turn.
    session = TripSessionState(
        id="s1", messages=[], trip_brief=previous_brief,
        flight_candidates=[], hotel_candidates=cached_hotels, itinerary=[],
    )

    called = []

    async def fake_planner(client, messages, previous_brief_):
        return previous_brief, _usage()  # brief unchanged this turn

    async def fake_flight(client, brief):
        called.append("flight")
        return recovered_flights, _usage()

    async def fake_hotel(client, brief):
        called.append("hotel")
        return cached_hotels, _usage()

    async def fake_itinerary(client, brief, flights_, hotels_, weather):
        return [], _usage()

    async def fake_weather(destination, start_date, end_date):
        return []

    monkeypatch.setattr(orchestrator, "run_planner_agent", fake_planner)
    monkeypatch.setattr(orchestrator, "run_flight_agent", fake_flight)
    monkeypatch.setattr(orchestrator, "run_hotel_agent", fake_hotel)
    monkeypatch.setattr(orchestrator, "run_itinerary_agent", fake_itinerary)
    monkeypatch.setattr(orchestrator, "get_daily_summary", fake_weather)
    monkeypatch.setattr(orchestrator.metrics, "record_agent_call", lambda **kw: kw)

    result = await orchestrator.handle_turn(client=object(), session=session, user_message="any cheaper flights?")

    assert "flight" in called, "a previously-failed flight agent must retry even when the brief is unchanged"
    assert result.flight_candidates == recovered_flights


async def test_turn_level_metric_is_recorded_with_session_and_turn_ids(monkeypatch):
    new_brief = TripBrief(destination="Paris", origin="ICN", start_date="2026-11-01", end_date="2026-11-02", budget_usd=2000.0, interests=[], pace="balanced")

    async def fake_planner(client, messages, previous_brief_):
        return new_brief, _usage()

    async def fake_flight(client, brief):
        return [], _usage()

    async def fake_hotel(client, brief):
        return [], _usage()

    async def fake_itinerary(client, brief, flights_, hotels_, weather):
        return [], _usage()

    async def fake_weather(destination, start_date, end_date):
        return []

    monkeypatch.setattr(orchestrator, "run_planner_agent", fake_planner)
    monkeypatch.setattr(orchestrator, "run_flight_agent", fake_flight)
    monkeypatch.setattr(orchestrator, "run_hotel_agent", fake_hotel)
    monkeypatch.setattr(orchestrator, "run_itinerary_agent", fake_itinerary)
    monkeypatch.setattr(orchestrator, "get_daily_summary", fake_weather)
    recorded = []
    monkeypatch.setattr(orchestrator.metrics, "record_agent_call", lambda **kw: recorded.append(kw))

    await orchestrator.handle_turn(client=object(), session=_empty_session(), user_message="Plan Paris")

    turn_records = [kw for kw in recorded if kw["agent_name"] == "turn"]
    assert len(turn_records) == 1
    assert turn_records[0]["session_id"] == "s1"
    assert turn_records[0]["latency_ms"] >= 0
    turn_ids = {kw["turn_id"] for kw in recorded}
    assert len(turn_ids) == 1
    assert all(kw["session_id"] == "s1" for kw in recorded)


async def test_planner_failure_reply_does_not_claim_an_update(monkeypatch):
    previous_brief = TripBrief(destination="Paris", origin="ICN", start_date="2026-11-01", end_date="2026-11-02", budget_usd=2000.0, interests=["art"], pace="balanced")
    session = TripSessionState(
        id="s1", messages=[], trip_brief=previous_brief,
        flight_candidates=[], hotel_candidates=[], itinerary=[],
    )

    async def failing_planner(client, messages, previous_brief_):
        raise AgentError("planner never produced a final tool call")

    monkeypatch.setattr(orchestrator, "run_planner_agent", failing_planner)
    monkeypatch.setattr(orchestrator.metrics, "record_agent_call", lambda **kw: kw)

    result = await orchestrator.handle_turn(client=object(), session=session, user_message="add museums")

    assert "Updated your trip" not in result.reply
    assert "couldn't update your trip details" in result.reply

