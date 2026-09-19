from travel_agent.agents.base import AgentUsage, run_agent_loop
from travel_agent.schemas import HotelCandidate, TripBrief

HOTEL_SYSTEM_PROMPT = """You are the Hotel agent for a travel planning system.
Given a trip brief, use web_search to find current hotel prices and options
in the destination city for the given check-in/check-out dates (e.g. search
Booking.com, Google Hotels, or hotel sites). Then call submit_hotel_candidates
with up to 3 options ranked by best value within the stated budget when
possible.
Only submit candidates backed by an actual web_search result for a current
price: never recall, estimate, or invent a hotel or a price from your own
knowledge. If web search doesn't turn up a clear, current price, return
fewer candidates rather than a fabricated one.
"""

WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 2}

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


async def run_hotel_agent(client, brief: TripBrief) -> tuple[list[HotelCandidate], AgentUsage]:
    user_message = (
        f"Trip brief: destination={brief.destination}, check_in={brief.start_date}, "
        f"check_out={brief.end_date}, budget_usd={brief.budget_usd}. "
        "Search the web for current hotel prices and submit up to 3 ranked candidates."
    )

    result = await run_agent_loop(
        client=client,
        model="claude-haiku-4-5-20251001",
        system_prompt=HOTEL_SYSTEM_PROMPT,
        user_message=user_message,
        tools=[WEB_SEARCH_TOOL, SUBMIT_HOTEL_CANDIDATES_TOOL],
        final_tool_name="submit_hotel_candidates",
        tool_executor=_no_op_executor,
        client_tool_names=set(),
        max_turns=4,
    )

    candidates = [HotelCandidate(**c) for c in result.output["candidates"]]
    return candidates, result.usage
