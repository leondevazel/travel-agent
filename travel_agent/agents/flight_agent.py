from travel_agent.agents.base import AgentUsage, run_agent_loop
from travel_agent.schemas import FlightCandidate, TripBrief

FLIGHT_SYSTEM_PROMPT = """You are the Flight agent for a travel planning system.
Given a trip brief, use web_search to find current flight prices between the
stated origin/destination (or, for a multi-city trip, for each leg of the
route) on the given dates (e.g. search Google Flights, Skyscanner, or
airline sites). Then call submit_flight_candidates with up to 3 options per
leg, ranked by best value (balance of price and directness) within the
stated budget when possible.
Only submit candidates backed by an actual web_search result for a current
price: never recall, estimate, or invent a carrier, route, or price from
your own knowledge.

Submit what you actually found. carrier, price_usd, origin and destination
are required; departure_time, arrival_time and stops are optional -- search
results often give a carrier and a fare without exact schedule details. In
that case submit the candidate WITHOUT those fields rather than inventing
times or omitting a real fare you found. Never return an empty candidate
list just because schedule details were missing: a real carrier and a real
price is a useful result on its own.

Also set booking_url on each candidate: the page a traveler can actually
book or price-check that route on (the specific search result you took the
fare from, or that airline's or an aggregator's search URL for the route
and dates). It must be a real URL you saw in a search result, not invented.
"""

_CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "carrier": {"type": "string"},
        "price_usd": {"type": "number"},
        "origin": {"type": "string"},
        "destination": {"type": "string"},
        "departure_time": {"type": ["string", "null"], "description": "Only if the search result gave it"},
        "arrival_time": {"type": ["string", "null"], "description": "Only if the search result gave it"},
        "stops": {"type": ["integer", "null"], "description": "Only if the search result gave it"},
        "booking_url": {
            "type": ["string", "null"],
            "description": "Real URL from a search result where this fare can be booked or checked",
        },
    },
    "required": ["carrier", "price_usd", "origin", "destination"],
}

SUBMIT_FLIGHT_CANDIDATES_TOOL = {
    "name": "submit_flight_candidates",
    "description": "Submit the final ranked list of flight candidates.",
    "input_schema": {
        "type": "object",
        "properties": {"candidates": {"type": "array", "items": _CANDIDATE_SCHEMA}},
        "required": ["candidates"],
    },
}


async def _no_op_executor(name: str, tool_input: dict) -> dict:
    raise AssertionError(f"flight agent has no local client tools, got {name!r}")


def _route_legs(brief: TripBrief) -> list[tuple[str, str]]:
    """Ordered one-way legs for a multi-city trip.

    origin -> destination -> additional_destinations[0] -> ... -> back to
    origin. Empty for a single-city trip, which is instead searched as one
    round trip (see run_flight_agent) since that's a more natural search
    query and matches how most fares are actually sold.
    """
    if not brief.additional_destinations:
        return []
    stops = [brief.destination, *brief.additional_destinations]
    legs: list[tuple[str, str]] = []
    prev = brief.origin
    for stop in stops:
        legs.append((prev, stop))
        prev = stop
    legs.append((prev, brief.origin))
    return legs


async def run_flight_agent(client, brief: TripBrief) -> tuple[list[FlightCandidate], AgentUsage]:
    legs = _route_legs(brief)

    if not legs:
        user_message = (
            f"Trip brief: origin={brief.origin}, destination={brief.destination}, "
            f"depart={brief.start_date}, return={brief.end_date}, budget_usd={brief.budget_usd}. "
            "Search the web for current round-trip flight prices and submit up to 3 ranked candidates."
        )
        max_uses = 2
        max_turns = 4
        max_tokens = 3072
    else:
        leg_lines = "\n".join(f"- {o} -> {d}" for o, d in legs)
        user_message = (
            f"Multi-city trip brief: dates {brief.start_date} to {brief.end_date}, "
            f"budget_usd={brief.budget_usd} (covers the whole trip, all legs combined). "
            f"This trip has {len(legs)} one-way flight legs, in order:\n{leg_lines}\n"
            "Search the web for current one-way flight prices for EACH leg "
            f"separately, then submit up to 3 ranked candidates per leg (up to "
            f"{len(legs) * 3} candidates total) via submit_flight_candidates, each "
            "tagged with the origin/destination of the leg it belongs to."
        )
        max_uses = min(2 * len(legs), 8)
        max_turns = min(2 * len(legs) + 2, 12)
        max_tokens = min(3072 + 1024 * (len(legs) - 1), 8192)

    tools = [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses},
        SUBMIT_FLIGHT_CANDIDATES_TOOL,
    ]

    result = await run_agent_loop(
        client=client,
        model="claude-haiku-4-5-20251001",
        system_prompt=FLIGHT_SYSTEM_PROMPT,
        user_message=user_message,
        tools=tools,
        final_tool_name="submit_flight_candidates",
        tool_executor=_no_op_executor,
        client_tool_names=set(),
        max_turns=max_turns,
        max_tokens=max_tokens,
    )

    candidates = [FlightCandidate(**c) for c in result.output["candidates"]]
    return candidates, result.usage
