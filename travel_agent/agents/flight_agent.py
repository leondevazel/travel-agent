from travel_agent.agents.base import AgentUsage, run_agent_loop
from travel_agent.schemas import FlightCandidate, TripBrief
from travel_agent.tools.amadeus_client import AmadeusClient

FLIGHT_SYSTEM_PROMPT = """You are the Flight agent for a travel planning system.
Given a trip brief, call search_flights with the correct IATA airport codes
for the origin and destination cities and the trip's start/end dates, then
call submit_flight_candidates with up to 3 options ranked by best value
(balance of price and directness) within the stated budget when possible.
"""

SEARCH_FLIGHTS_TOOL = {
    "name": "search_flights",
    "description": "Search real flight offers via Amadeus.",
    "input_schema": {
        "type": "object",
        "properties": {
            "origin": {"type": "string", "description": "3-letter IATA airport code"},
            "destination": {"type": "string", "description": "3-letter IATA airport code"},
            "departure_date": {"type": "string", "description": "ISO date"},
            "return_date": {"type": ["string", "null"], "description": "ISO date"},
        },
        "required": ["origin", "destination", "departure_date"],
    },
}

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


async def run_flight_agent(client, brief: TripBrief, amadeus: AmadeusClient) -> tuple[list[FlightCandidate], AgentUsage]:
    async def executor(name: str, tool_input: dict) -> dict:
        offers = await amadeus.search_flights(
            origin=tool_input["origin"],
            destination=tool_input["destination"],
            departure_date=tool_input["departure_date"],
            return_date=tool_input.get("return_date"),
        )
        return {"offers": offers}

    user_message = (
        f"Trip brief: origin city/airport={brief.origin}, destination={brief.destination}, "
        f"depart={brief.start_date}, return={brief.end_date}, budget_usd={brief.budget_usd}. "
        "Search for flights and submit up to 3 ranked candidates."
    )

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt=FLIGHT_SYSTEM_PROMPT,
        user_message=user_message,
        tools=[SEARCH_FLIGHTS_TOOL, SUBMIT_FLIGHT_CANDIDATES_TOOL],
        final_tool_name="submit_flight_candidates",
        tool_executor=executor,
        client_tool_names={"search_flights"},
        max_turns=3,
    )

    candidates = [FlightCandidate(**c) for c in result.output["candidates"]]
    return candidates, result.usage
