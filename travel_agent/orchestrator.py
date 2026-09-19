import asyncio
import time
import uuid
from dataclasses import dataclass

import anthropic
from pydantic import ValidationError

from travel_agent import metrics
from travel_agent.agents.base import AgentError
from travel_agent.agents.flight_agent import run_flight_agent
from travel_agent.agents.hotel_agent import run_hotel_agent
from travel_agent.agents.itinerary_agent import run_itinerary_agent
from travel_agent.agents.planner import run_planner_agent
from travel_agent.db import TripSessionState
from travel_agent.diff import diff_trip_brief
from travel_agent.schemas import FlightCandidate, HotelCandidate, ItineraryDay, Message, TripBrief
from travel_agent.tools.route_optimizer import optimize_route
from travel_agent.tools.weather_client import WeatherAPIError, get_daily_summary

AGENT_TIMEOUT_SECONDS = 60

# Everything an agent can plausibly fail with for reasons outside our control:
# upstream APIs (Open-Meteo/Anthropic, including its web_search tool), a
# timeout, or an LLM returning data that doesn't fit the schema
# (ValidationError) or omits an expected key (KeyError). Deliberately NOT
# bare Exception, so genuine bugs in our own code (e.g. a TypeError) still
# surface loudly instead of looking like a graceful degradation.
_FALLIBLE_ERRORS = (
    WeatherAPIError,
    AgentError,
    asyncio.TimeoutError,
    anthropic.APIError,
    ValidationError,
    KeyError,
)


@dataclass
class TurnResult:
    reply: str
    trip_brief: TripBrief
    flight_candidates: list[FlightCandidate]
    hotel_candidates: list[HotelCandidate]
    itinerary: list[ItineraryDay]
    warnings: list[str]


async def _run_with_fallback(agent_name: str, coro, cached, session_id: str | None = None, turn_id: str | None = None):
    start = time.monotonic()
    try:
        result, usage = await asyncio.wait_for(coro, timeout=AGENT_TIMEOUT_SECONDS)
        metrics.record_agent_call(
            agent_name=agent_name,
            session_id=session_id,
            turn_id=turn_id,
            latency_ms=usage.latency_ms,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            success=True,
        )
        return result, None
    except _FALLIBLE_ERRORS as exc:
        latency_ms = (time.monotonic() - start) * 1000
        metrics.record_agent_call(
            agent_name=agent_name,
            session_id=session_id,
            turn_id=turn_id,
            latency_ms=latency_ms,
            input_tokens=0,
            output_tokens=0,
            success=False,
            error_type=type(exc).__name__,
        )
        warning = (
            f"couldn't fetch live {agent_name} data right now, showing previous results"
            if cached
            else f"couldn't fetch live {agent_name} data right now"
        )
        return cached, warning


async def _optimize_route_order(
    brief: TripBrief, session_id: str, turn_id: str
) -> tuple[TripBrief, str | None]:
    """Reorder a multi-city brief's destination + additional_destinations to
    (approximately) minimize real-world travel distance, using geocoded
    coordinates. A no-op for a single-city brief. Never fails the turn: on a
    geocoding failure, the brief's original order is kept and a warning is
    returned instead."""
    if not brief.additional_destinations or not brief.origin or not brief.destination:
        return brief, None

    cities = [brief.destination, *brief.additional_destinations]
    start = time.monotonic()
    try:
        optimized = await asyncio.wait_for(optimize_route(brief.origin, cities), timeout=AGENT_TIMEOUT_SECONDS)
        metrics.record_agent_call(
            agent_name="route_optimizer",
            session_id=session_id,
            turn_id=turn_id,
            latency_ms=(time.monotonic() - start) * 1000,
            input_tokens=0,
            output_tokens=0,
            success=True,
        )
    except (WeatherAPIError, asyncio.TimeoutError) as exc:
        metrics.record_agent_call(
            agent_name="route_optimizer",
            session_id=session_id,
            turn_id=turn_id,
            latency_ms=(time.monotonic() - start) * 1000,
            input_tokens=0,
            output_tokens=0,
            success=False,
            error_type=type(exc).__name__,
        )
        return brief, "couldn't compute an optimized route order, using the order you gave"

    if optimized == cities:
        return brief, None
    return brief.model_copy(update={"destination": optimized[0], "additional_destinations": optimized[1:]}), None


def _retryable_agents(brief: TripBrief, session: TripSessionState) -> set[str]:
    """Agents whose cached result is empty but which the brief can now feed.

    Without this, an agent that failed on an earlier turn would never retry:
    the brief stops changing, so diff_trip_brief returns nothing to run and the
    empty result persists forever.
    """
    if not (brief.origin and brief.destination and brief.start_date and brief.end_date):
        return set()
    agents: set[str] = set()
    if not session.flight_candidates:
        agents.add("flight")
    if not session.hotel_candidates:
        agents.add("hotel")
    return agents


async def handle_turn(client, session: TripSessionState, user_message: str) -> TurnResult:
    turn_start = time.monotonic()
    turn_id = str(uuid.uuid4())
    messages = session.messages + [Message(role="user", content=user_message)]
    warnings: list[str] = []
    planner_failed = False

    planner_start = time.monotonic()
    try:
        new_brief, planner_usage = await asyncio.wait_for(
            run_planner_agent(client, messages, session.trip_brief), timeout=AGENT_TIMEOUT_SECONDS
        )
        metrics.record_agent_call(
            agent_name="planner",
            session_id=session.id,
            turn_id=turn_id,
            latency_ms=planner_usage.latency_ms,
            input_tokens=planner_usage.input_tokens,
            output_tokens=planner_usage.output_tokens,
            success=True,
        )
        new_brief, route_warning = await _optimize_route_order(new_brief, session.id, turn_id)
        if route_warning:
            warnings.append(route_warning)

        agents_to_run = diff_trip_brief(session.trip_brief, new_brief)
        agents_to_run |= _retryable_agents(new_brief, session)
    except _FALLIBLE_ERRORS as exc:
        latency_ms = (time.monotonic() - planner_start) * 1000
        metrics.record_agent_call(
            agent_name="planner",
            session_id=session.id,
            turn_id=turn_id,
            latency_ms=latency_ms,
            input_tokens=0,
            output_tokens=0,
            success=False,
            error_type=type(exc).__name__,
        )
        # No new brief data to act on, so skip specialist agents entirely rather than
        # feeding them an empty/unchanged brief that would likely just fail again.
        new_brief = session.trip_brief if session.trip_brief is not None else TripBrief()
        agents_to_run = set()
        planner_failed = True
        warnings.append("couldn't update your trip details right now")

    flight_candidates = session.flight_candidates
    hotel_candidates = session.hotel_candidates
    itinerary = session.itinerary

    if "flight" in agents_to_run or "hotel" in agents_to_run:
        (flight_candidates, flight_warning), (hotel_candidates, hotel_warning) = await asyncio.gather(
            _run_with_fallback(
                "flight",
                run_flight_agent(client, new_brief),
                session.flight_candidates,
                session_id=session.id,
                turn_id=turn_id,
            ),
            _run_with_fallback(
                "hotel",
                run_hotel_agent(client, new_brief),
                session.hotel_candidates,
                session_id=session.id,
                turn_id=turn_id,
            ),
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
            session_id=session.id,
            turn_id=turn_id,
        )
        if itin_warning:
            warnings.append(itin_warning)

    reply = _build_reply(new_brief, itinerary, warnings, planner_failed=planner_failed)

    metrics.record_agent_call(
        agent_name="turn",
        session_id=session.id,
        turn_id=turn_id,
        latency_ms=(time.monotonic() - turn_start) * 1000,
        input_tokens=0,
        output_tokens=0,
        success=True,
    )

    return TurnResult(
        reply=reply,
        trip_brief=new_brief,
        flight_candidates=flight_candidates,
        hotel_candidates=hotel_candidates,
        itinerary=itinerary,
        warnings=warnings,
    )


def _build_reply(
    brief: TripBrief, itinerary: list[ItineraryDay], warnings: list[str], planner_failed: bool = False
) -> str:
    # When the planner itself failed, nothing was updated, so don't claim it was.
    if planner_failed:
        lines = ["I couldn't update your trip details just now, so here's what I had before."]
    else:
        lines = [f"Updated your trip to {brief.destination or 'your destination'}."]
    for day in itinerary:
        lines.append(f"Day {day.day_number} ({day.date}): {', '.join(day.activities)}")
    for warning in warnings:
        lines.append(f"Note: {warning}.")
    return "\n".join(lines)
