from dataclasses import dataclass, field

from travel_agent.agents.planner import run_planner_agent
from travel_agent.schemas import Message, TripBrief


@dataclass
class FakeBlock:
    type: str
    name: str = ""
    input: dict = field(default_factory=dict)
    id: str = "block-1"


@dataclass
class FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class FakeResponse:
    content: list
    stop_reason: str
    usage: FakeUsage


class FakeMessagesAPI:
    def __init__(self, response):
        self._response = response
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class FakeClient:
    def __init__(self, response):
        self.messages = FakeMessagesAPI(response)


async def test_planner_extracts_brief_from_conversation():
    response = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                name="submit_trip_brief",
                input={
                    "destination": "Paris",
                    "origin": "ICN",
                    "start_date": "2026-11-01",
                    "end_date": "2026-11-05",
                    "budget_usd": 2000.0,
                    "interests": ["art", "food"],
                    "pace": "balanced",
                },
            )
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=200, output_tokens=40),
    )
    client = FakeClient(response)
    messages = [Message(role="user", content="Plan a 5 day trip to Paris from Seoul, budget $2000, into art and food")]

    brief, usage = await run_planner_agent(client, messages, previous_brief=None)

    assert brief == TripBrief(
        destination="Paris",
        origin="ICN",
        start_date="2026-11-01",
        end_date="2026-11-05",
        budget_usd=2000.0,
        interests=["art", "food"],
        pace="balanced",
    )
    assert usage.input_tokens == 200
    assert client.messages.calls[0]["tool_choice"] == {"type": "tool", "name": "submit_trip_brief"}


async def test_planner_passes_previous_brief_in_prompt():
    response = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                name="submit_trip_brief",
                input={
                    "destination": "Paris",
                    "origin": "ICN",
                    "start_date": "2026-11-01",
                    "end_date": "2026-11-05",
                    "budget_usd": 2000.0,
                    "interests": ["art"],
                    "pace": "relaxed",
                },
            )
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=210, output_tokens=42),
    )
    client = FakeClient(response)
    previous_brief = TripBrief(
        destination="Paris",
        origin="ICN",
        start_date="2026-11-01",
        end_date="2026-11-05",
        budget_usd=2000.0,
        interests=["art"],
        pace="balanced",
    )
    messages = [
        Message(role="user", content="Plan a trip to Paris"),
        Message(role="assistant", content="Sure, here's a plan..."),
        Message(role="user", content="2일차 느슨하게 바꿔줘"),
    ]

    brief, _ = await run_planner_agent(client, messages, previous_brief)

    sent_user_message = client.messages.calls[0]["messages"][0]["content"]
    assert "느슨하게" in sent_user_message
    assert '"pace":"balanced"' in sent_user_message.replace(" ", "") or "balanced" in sent_user_message
    assert brief.pace == "relaxed"


async def test_planner_extracts_multi_city_route_and_must_visit():
    response = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                name="submit_trip_brief",
                input={
                    "destination": "Tokyo",
                    "origin": "ICN",
                    "additional_destinations": ["Osaka"],
                    "must_visit": ["Fushimi Inari Shrine"],
                    "start_date": "2026-11-01",
                    "end_date": "2026-11-08",
                    "budget_usd": 3000.0,
                    "interests": ["food"],
                    "pace": "balanced",
                },
            )
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=220, output_tokens=45),
    )
    client = FakeClient(response)
    messages = [
        Message(
            role="user",
            content="Plan a trip to Tokyo then Osaka from Seoul, I really want to see Fushimi Inari Shrine",
        )
    ]

    brief, _ = await run_planner_agent(client, messages, previous_brief=None)

    assert brief.destination == "Tokyo"
    assert brief.additional_destinations == ["Osaka"]
    assert brief.must_visit == ["Fushimi Inari Shrine"]
