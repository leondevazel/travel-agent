from travel_agent.agents.base import AgentUsage, run_agent_loop
from travel_agent.schemas import HotelCandidate, TripBrief

HOTEL_SYSTEM_PROMPT = """You are the Hotel agent for a travel planning system.
Given a trip brief, use web_search to find current hotel prices and options
in the destination city (or, for a multi-city trip, in EACH city on the
route) for the given dates (e.g. search Booking.com, Google Hotels, or hotel
sites). Then call submit_hotel_candidates with up to 3 options per city,
ranked by best value within the stated budget when possible.
Only submit candidates backed by an actual web_search result for a current
price: never recall, estimate, or invent a hotel or a price from your own
knowledge. If web search doesn't turn up a clear, current price for a city,
return fewer candidates for that city rather than a fabricated one.
"""

_CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "price_usd_per_night": {"type": "number"},
        "rating": {"type": ["number", "null"]},
        "address": {"type": "string"},
    },
    "required": ["name", "price_usd_per_night", "address"],
}

SUBMIT_HOTEL_CANDIDATES_TOOL = {
    "name": "submit_hotel_candidates",
    "description": "Submit the final ranked list of hotel candidates.",
    "input_schema": {
        "type": "object",
        "properties": {"candidates": {"type": "array", "items": _CANDIDATE_SCHEMA}},
        "required": ["candidates"],
    },
}


async def _no_op_executor(name: str, tool_input: dict) -> dict:
    raise AssertionError(f"hotel agent has no local client tools, got {name!r}")


def _cities(brief: TripBrief) -> list[str]:
    return [c for c in [brief.destination, *brief.additional_destinations] if c]


async def run_hotel_agent(client, brief: TripBrief) -> tuple[list[HotelCandidate], AgentUsage]:
    cities = _cities(brief)

    if len(cities) <= 1:
        user_message = (
            f"Trip brief: destination={brief.destination}, check_in={brief.start_date}, "
            f"check_out={brief.end_date}, budget_usd={brief.budget_usd}. "
            "Search the web for current hotel prices and submit up to 3 ranked candidates."
        )
        max_uses = 2
        max_turns = 4
        max_tokens = 3072
    else:
        city_lines = "\n".join(f"- {c}" for c in cities)
        user_message = (
            f"Multi-city trip brief: overall trip dates {brief.start_date} to "
            f"{brief.end_date}, budget_usd={brief.budget_usd} (covers the whole "
            f"trip, all cities combined). Find a hotel in EACH of these "
            f"{len(cities)} cities (exact nights per city aren't decided yet, so "
            "search for current typical rates around these dates):\n"
            f"{city_lines}\n"
            "Search the web for current hotel prices in each city, then submit "
            f"up to 3 ranked candidates per city (up to {len(cities) * 3} "
            "candidates total) via submit_hotel_candidates, each with an address "
            "that makes clear which city it's in."
        )
        max_uses = min(2 * len(cities), 8)
        max_turns = min(2 * len(cities) + 2, 12)
        max_tokens = min(3072 + 1024 * (len(cities) - 1), 8192)

    tools = [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses},
        SUBMIT_HOTEL_CANDIDATES_TOOL,
    ]

    result = await run_agent_loop(
        client=client,
        model="claude-haiku-4-5-20251001",
        system_prompt=HOTEL_SYSTEM_PROMPT,
        user_message=user_message,
        tools=tools,
        final_tool_name="submit_hotel_candidates",
        tool_executor=_no_op_executor,
        client_tool_names=set(),
        max_turns=max_turns,
        max_tokens=max_tokens,
    )

    candidates = [HotelCandidate(**c) for c in result.output["candidates"]]
    return candidates, result.usage
