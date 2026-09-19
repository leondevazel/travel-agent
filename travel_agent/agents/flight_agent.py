from travel_agent.agents.base import AgentUsage, run_agent_loop
from travel_agent.schemas import FlightCandidate, TripBrief

FLIGHT_SYSTEM_PROMPT = """You are the Flight agent for a travel planning system.
Given a trip brief, use web_search to find current flight prices and options
between the origin and destination on the given dates (e.g. search Google
Flights, Skyscanner, or airline sites). Then call submit_flight_candidates
with up to 3 options ranked by best value (balance of price and directness)
within the stated budget when possible.
Only submit candidates backed by an actual web_search result for a current
price: never recall, estimate, or invent a carrier, route, or price from
your own knowledge. If web search doesn't turn up a clear, current price for
a route, return fewer candidates rather than a fabricated one.
"""

WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 4}

_CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "carrier": {"type": "string"},
        "price_usd": {"type": "number"},
        "departure_time": {"type": "string"},
        "arrival_time": {"type": "string"},
        "origin": {"type": "string"},
        "destination": {"type": "string"},
        "stops": {"type": "integer"},
    },
    "required": ["carrier", "price_usd", "departure_time", "arrival_time", "origin", "destination", "stops"],
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


async def run_flight_agent(client, brief: TripBrief) -> tuple[list[FlightCandidate], AgentUsage]:
    user_message = (
        f"Trip brief: origin={brief.origin}, destination={brief.destination}, "
        f"depart={brief.start_date}, return={brief.end_date}, budget_usd={brief.budget_usd}. "
        "Search the web for current flight prices and submit up to 3 ranked candidates."
    )

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt=FLIGHT_SYSTEM_PROMPT,
        user_message=user_message,
        tools=[WEB_SEARCH_TOOL, SUBMIT_FLIGHT_CANDIDATES_TOOL],
        final_tool_name="submit_flight_candidates",
        tool_executor=_no_op_executor,
        client_tool_names=set(),
        max_turns=4,
    )

    candidates = [FlightCandidate(**c) for c in result.output["candidates"]]
    return candidates, result.usage
