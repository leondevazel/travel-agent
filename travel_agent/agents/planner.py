from travel_agent.agents.base import AgentUsage, run_agent_loop
from travel_agent.schemas import Message, TripBrief

PLANNER_SYSTEM_PROMPT = """You are the Planner agent for a travel planning system.
Read the full conversation and the previous structured trip brief (if any),
then produce the updated trip brief by calling submit_trip_brief.

Rules:
- Keep every field from the previous brief unless the conversation clearly
  changes it. Never null out a field the user hasn't mentioned again.
- interests is a cumulative list of the user's stated interests/activities.
- pace is one of "relaxed", "balanced", "packed" — infer it from phrasing
  like "느슨하게"/relaxed, "빡빡하게"/packed, etc.
- Dates must be ISO format (YYYY-MM-DD). origin/destination are city or
  airport names as the user said them; do not invent an IATA code here.
"""

SUBMIT_TRIP_BRIEF_TOOL = {
    "name": "submit_trip_brief",
    "description": "Submit the updated structured trip brief extracted from the conversation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "destination": {"type": ["string", "null"]},
            "origin": {"type": ["string", "null"]},
            "start_date": {"type": ["string", "null"], "description": "ISO date"},
            "end_date": {"type": ["string", "null"], "description": "ISO date"},
            "budget_usd": {"type": ["number", "null"]},
            "interests": {"type": "array", "items": {"type": "string"}},
            "pace": {"type": ["string", "null"], "enum": ["relaxed", "balanced", "packed", None]},
        },
        "required": ["interests"],
    },
}


async def _no_op_executor(name: str, tool_input: dict) -> dict:
    raise AssertionError(f"planner agent has no client tools, got {name!r}")


async def run_planner_agent(
    client, messages: list[Message], previous_brief: TripBrief | None
) -> tuple[TripBrief, AgentUsage]:
    conversation_text = "\n".join(f"{m.role}: {m.content}" for m in messages)
    previous_json = previous_brief.model_dump_json() if previous_brief else "null"
    user_message = (
        f"Conversation so far:\n{conversation_text}\n\n"
        f"Previous trip brief (JSON):\n{previous_json}\n\n"
        "Extract/update the trip brief and call submit_trip_brief."
    )

    result = await run_agent_loop(
        client=client,
        model="claude-sonnet-5",
        system_prompt=PLANNER_SYSTEM_PROMPT,
        user_message=user_message,
        tools=[SUBMIT_TRIP_BRIEF_TOOL],
        final_tool_name="submit_trip_brief",
        tool_executor=_no_op_executor,
        client_tool_names=set(),
        tool_choice={"type": "tool", "name": "submit_trip_brief"},
        max_turns=1,
    )

    return TripBrief(**result.output), result.usage
