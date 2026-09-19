from dataclasses import dataclass, field

from travel_agent.agents.itinerary_agent import run_itinerary_agent
from travel_agent.schemas import FlightCandidate, HotelCandidate, ItineraryDay, TripBrief


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
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.messages = FakeMessagesAPI(responses)


def _brief(**overrides):
    base = dict(
        destination="Paris",
        origin="ICN",
        start_date="2026-11-01",
        end_date="2026-11-02",
        budget_usd=2000.0,
        interests=["art"],
        pace="relaxed",
    )
    base.update(overrides)
    return TripBrief(**base)


async def test_itinerary_agent_composes_days_from_context_in_one_turn():
    # A single response can contain server-executed web_search blocks
    # followed directly by the final submit_itinerary tool call.
    response = FakeResponse(
        content=[
            FakeBlock(type="server_tool_use", name="web_search", input={"query": "Paris museums"}),
            FakeBlock(type="web_search_tool_result"),
            FakeBlock(
                type="tool_use",
                name="submit_itinerary",
                input={
                    "days": [
                        {"day_number": 1, "date": "2026-11-01", "location": "Louvre", "activities": ["Louvre"], "notes": "relaxed pace"},
                    ]
                },
            ),
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=300, output_tokens=80),
    )
    client = FakeClient([response])

    days, usage = await run_itinerary_agent(
        client,
        _brief(),
        flights=[FlightCandidate(carrier="KE", price_usd=800, departure_time="t1", arrival_time="t2", origin="ICN", destination="CDG", stops=0)],
        hotels=[HotelCandidate(name="Hotel Lumiere", price_usd_per_night=150, rating=4.2, address="Paris")],
        weather=[{"date": "2026-11-01", "temp_max_c": 14.0, "temp_min_c": 7.0, "condition": "overcast"}],
    )

    assert days == [ItineraryDay(day_number=1, date="2026-11-01", location="Louvre", activities=["Louvre"], notes="relaxed pace")]
    assert usage.input_tokens == 300
    sent_message = client.messages.calls[0]["messages"][0]["content"]
    assert "overcast" in sent_message
    assert "Hotel Lumiere" in sent_message


async def test_itinerary_agent_includes_web_search_tool():
    response = FakeResponse(
        content=[FakeBlock(type="tool_use", name="submit_itinerary", input={"days": []})],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=10, output_tokens=5),
    )
    client = FakeClient([response])

    await run_itinerary_agent(client, _brief(), flights=[], hotels=[], weather=[])

    tool_types = {t.get("type") for t in client.messages.calls[0]["tools"]}
    assert "web_search_20250305" in tool_types


async def test_itinerary_agent_prompt_states_route_order_and_must_visit():
    response = FakeResponse(
        content=[FakeBlock(type="tool_use", name="submit_itinerary", input={"days": []})],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=10, output_tokens=5),
    )
    client = FakeClient([response])
    brief = _brief(additional_destinations=["Rome"], must_visit=["Eiffel Tower"])

    await run_itinerary_agent(client, brief, flights=[], hotels=[], weather=[])

    sent_message = client.messages.calls[0]["messages"][0]["content"]
    assert "Paris -> Rome" in sent_message
    assert "Eiffel Tower" in sent_message
    # Multi-city trips get a wider search/turn/token budget than a single city.
    web_search_tool = next(t for t in client.messages.calls[0]["tools"] if t.get("type") == "web_search_20250305")
    assert web_search_tool["max_uses"] > 3
