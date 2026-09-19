import asyncio
import time
from dataclasses import dataclass

from travel_agent import metrics
from travel_agent.agents.base import AgentError
from travel_agent.agents.flight_agent import run_flight_agent
from travel_agent.agents.hotel_agent import run_hotel_agent
from travel_agent.agents.itinerary_agent import run_itinerary_agent
from travel_agent.agents.planner import run_planner_agent
from travel_agent.db import TripSessionState
from travel_agent.diff import diff_trip_brief
from travel_agent.schemas import FlightCandidate, HotelCandidate, ItineraryDay, Message, TripBrief
from travel_agent.tools.amadeus_client import AmadeusAPIError
from travel_agent.tools.weather_client import WeatherAPIError, get_daily_summary

AGENT_TIMEOUT_SECONDS = 30
_FALLIBLE_ERRORS = (AmadeusAPIError, WeatherAPIError, AgentError, asyncio.TimeoutError)


@dataclass
class TurnResult:
    reply: str
    trip_brief: TripBrief
    flight_candidates: list[FlightCandidate]
    hotel_candidates: list[HotelCandidate]
    itinerary: list[ItineraryDay]
    warnings: list[str]


async def _run_with_fallback(agent_name: str, coro, cached):
    start = time.monotonic()
    try:
        result, usage = await asyncio.wait_for(coro, timeout=AGENT_TIMEOUT_SECONDS)
        metrics.record_agent_call(
            agent_name=agent_name,
            latency_ms=usage.latency_ms,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            success=True,
        )
        return result, None
    except _FALLIBLE_ERRORS:
        latency_ms = (time.monotonic() - start) * 1000
        metrics.record_agent_call(
            agent_name=agent_name, latency_ms=latency_ms, input_tokens=0, output_tokens=0, success=False
        )
        warning = (
            f"couldn't fetch live {agent_name} data right now, showing previous results"
            if cached
            else f"couldn't fetch live {agent_name} data right now"
        )
        return cached, warning


async def handle_turn(client, amadeus, session: TripSessionState, user_message: str) -> TurnResult:
    messages = session.messages + [Message(role="user", content=user_message)]
    warnings: list[str] = []

    planner_start = time.monotonic()
    try:
        new_brief, planner_usage = await asyncio.wait_for(
            run_planner_agent(client, messages, session.trip_brief), timeout=AGENT_TIMEOUT_SECONDS
        )
        metrics.record_agent_call(
            agent_name="planner",
            latency_ms=planner_usage.latency_ms,
            input_tokens=planner_usage.input_tokens,
            output_tokens=planner_usage.output_tokens,
            success=True,
        )
        agents_to_run = diff_trip_brief(session.trip_brief, new_brief)
    except _FALLIBLE_ERRORS:
        latency_ms = (time.monotonic() - planner_start) * 1000
        metrics.record_agent_call(
            agent_name="planner", latency_ms=latency_ms, input_tokens=0, output_tokens=0, success=False
        )
        # No new brief data to act on, so skip specialist agents entirely rather than
        # feeding them an empty/unchanged brief that would likely just fail again.
        new_brief = session.trip_brief if session.trip_brief is not None else TripBrief()
        agents_to_run = set()
        warnings.append("couldn't update your trip details right now")

    flight_candidates = session.flight_candidates
    hotel_candidates = session.hotel_candidates
    itinerary = session.itinerary

    if "flight" in agents_to_run or "hotel" in agents_to_run:
        (flight_candidates, flight_warning), (hotel_candidates, hotel_warning) = await asyncio.gather(
            _run_with_fallback("flight", run_flight_agent(client, new_brief, amadeus), session.flight_candidates),
            _run_with_fallback("hotel", run_hotel_agent(client, new_brief, amadeus), session.hotel_candidates),
        )
        for w in (flight_warning, hotel_warning):
            if w:
                warnings.append(w)

    if agents_to_run:
        if new_brief.destination and new_brief.start_date and new_brief.end_date:
            try:
                weather = await get_daily_summary(new_brief.destination, new_brief.start_date, new_brief.end_date)
            except WeatherAPIError:
                weather = []
        else:
            weather = []
        itinerary, itin_warning = await _run_with_fallback(
            "itinerary",
            run_itinerary_agent(client, new_brief, flight_candidates, hotel_candidates, weather),
            session.itinerary,
        )
        if itin_warning:
            warnings.append(itin_warning)

    reply = _build_reply(new_brief, itinerary, warnings)
    return TurnResult(
        reply=reply,
        trip_brief=new_brief,
        flight_candidates=flight_candidates,
        hotel_candidates=hotel_candidates,
        itinerary=itinerary,
        warnings=warnings,
    )


def _build_reply(brief: TripBrief, itinerary: list[ItineraryDay], warnings: list[str]) -> str:
    lines = [f"Updated your trip to {brief.destination or 'your destination'}."]
    for day in itinerary:
        lines.append(f"Day {day.day_number} ({day.date}): {', '.join(day.activities)}")
    for warning in warnings:
        lines.append(f"Note: {warning}.")
    return "\n".join(lines)
