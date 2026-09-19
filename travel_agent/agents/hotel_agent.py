from travel_agent.agents.base import AgentUsage, run_agent_loop
from travel_agent.schemas import HotelCandidate, TripBrief
from travel_agent.tools.amadeus_client import AmadeusClient

HOTEL_SYSTEM_PROMPT = """You are the Hotel agent for a travel planning system.
Given a trip brief, call search_hotels with the 3-letter IATA city code for
the destination and the trip's check-in/check-out dates, then call
submit_hotel_candidates with up to 3 options ranked by best value within
the stated budget when possible.
"""

SEARCH_HOTELS_TOOL = {
    "name": "search_hotels",
    "description": "Search real hotel offers via Amadeus.",
    "input_schema": {
        "type": "object",
        "properties": {
            "city_code": {"type": "string", "description": "3-letter IATA city code"},
            "check_in": {"type": "string", "description": "ISO date"},
            "check_out": {"type": "string", "description": "ISO date"},
        },
        "required": ["city_code", "check_in", "check_out"],
    },
}

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


async def run_hotel_agent(client, brief: TripBrief, amadeus: AmadeusClient) -> tuple[list[HotelCandidate], AgentUsage]:
    async def executor(name: str, tool_input: dict) -> dict:
        offers = await amadeus.search_hotels(
            city_code=tool_input["city_code"],
            check_in=tool_input["check_in"],
            check_out=tool_input["check_out"],
        )
        return {"offers": offers}

    user_message = (
        f"Trip brief: destination={brief.destination}, check_in={brief.start_date}, "
        f"check_out={brief.end_date}, budget_usd={brief.budget_usd}. "
        "Search for hotels and submit up to 3 ranked candidates."
    )

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt=HOTEL_SYSTEM_PROMPT,
        user_message=user_message,
        tools=[SEARCH_HOTELS_TOOL, SUBMIT_HOTEL_CANDIDATES_TOOL],
        final_tool_name="submit_hotel_candidates",
        tool_executor=executor,
        client_tool_names={"search_hotels"},
        max_turns=3,
    )

    candidates = [HotelCandidate(**c) for c in result.output["candidates"]]
    return candidates, result.usage
