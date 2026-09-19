from travel_agent.agents.base import AgentUsage, run_agent_loop
from travel_agent.schemas import FlightCandidate, HotelCandidate, ItineraryDay, TripBrief

ITINERARY_SYSTEM_PROMPT = """You are the Itinerary agent for a travel planning system.
Compose a day-by-day plan from the trip brief, the chosen flight/hotel
candidates, and the daily weather forecast. Use web_search for specific
attractions, opening hours, or events worth knowing about at the
destination(s). Respect the requested pace ("relaxed" = 1-2 activities/day,
"balanced" = 2-3, "packed" = 4+).

If the trip brief lists more than one city (destination plus
additional_destinations), visit them in EXACTLY that order — never
reorder the user's stated route. Split the total trip nights across the
cities (roughly evenly unless interests clearly favor one city more), and
say in each day's notes which city that day is in and, on the day the
traveler moves between cities, mention the transition explicitly.

If the trip brief lists must_visit places, make sure every one of them
appears in some day's activities — these are non-negotiable, unlike
interests, which are just a general steer on what kind of activities to
pick.

When finished, call submit_itinerary with one entry per day of the trip.
"""

SUBMIT_ITINERARY_TOOL = {
    "name": "submit_itinerary",
    "description": "Submit the final day-by-day itinerary.",
    "input_schema": {
        "type": "object",
        "properties": {
            "days": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "day_number": {"type": "integer"},
                        "date": {"type": "string"},
                        "activities": {"type": "array", "items": {"type": "string"}},
                        "notes": {"type": "string"},
                    },
                    "required": ["day_number", "date", "activities", "notes"],
                },
            },
        },
        "required": ["days"],
    },
}


async def _no_op_executor(name: str, tool_input: dict) -> dict:
    raise AssertionError(f"itinerary agent has no local client tools, got {name!r}")


def _format_weather(weather: list[dict]) -> str:
    if not weather:
        return "no forecast available"
    return "; ".join(f"{d['date']}: {d['condition']}, {d['temp_min_c']}-{d['temp_max_c']}C" for d in weather)


def _format_flights(flights: list[FlightCandidate]) -> str:
    if not flights:
        return "none selected"
    return "; ".join(f"{f.carrier} {f.origin}->{f.destination} ${f.price_usd}" for f in flights)


def _format_hotels(hotels: list[HotelCandidate]) -> str:
    if not hotels:
        return "none selected"
    return "; ".join(f"{h.name} (${h.price_usd_per_night}/night, {h.address})" for h in hotels)


async def run_itinerary_agent(
    client,
    brief: TripBrief,
    flights: list[FlightCandidate],
    hotels: list[HotelCandidate],
    weather: list[dict],
) -> tuple[list[ItineraryDay], AgentUsage]:
    cities = [c for c in [brief.destination, *brief.additional_destinations] if c]
    route = " -> ".join(cities) if len(cities) > 1 else (brief.destination or "unspecified")

    user_message = (
        f"Route: {route}. Dates: {brief.start_date} to {brief.end_date}. "
        f"Interests: {', '.join(brief.interests) or 'unspecified'}. "
        f"Must visit: {', '.join(brief.must_visit) or 'none specified'}. "
        f"Pace: {brief.pace or 'balanced'}.\n"
        f"Flights: {_format_flights(flights)}\n"
        f"Hotels: {_format_hotels(hotels)}\n"
        f"Weather: {_format_weather(weather)}\n"
        "Compose the day-by-day itinerary and call submit_itinerary."
    )

    max_uses = 3 if len(cities) <= 1 else min(2 * len(cities) + 1, 8)
    max_turns = 6 if len(cities) <= 1 else min(2 * len(cities) + 4, 12)
    max_tokens = 4096 if len(cities) <= 1 else min(4096 + 1024 * (len(cities) - 1), 8192)

    tools = [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses},
        SUBMIT_ITINERARY_TOOL,
    ]

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt=ITINERARY_SYSTEM_PROMPT,
        user_message=user_message,
        tools=tools,
        final_tool_name="submit_itinerary",
        tool_executor=_no_op_executor,
        client_tool_names=set(),
        max_turns=max_turns,
        max_tokens=max_tokens,
    )

    days = [ItineraryDay(**d) for d in result.output["days"]]
    return days, result.usage
