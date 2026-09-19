from dataclasses import dataclass, field

from travel_agent.agents.flight_agent import run_flight_agent
from travel_agent.agents.hotel_agent import run_hotel_agent
from travel_agent.schemas import FlightCandidate, HotelCandidate, TripBrief


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


def _brief():
    return TripBrief(
        destination="Paris",
        origin="ICN",
        start_date="2026-11-01",
        end_date="2026-11-05",
        budget_usd=2000.0,
        interests=["art"],
        pace="balanced",
    )


async def test_run_flight_agent_searches_web_then_submits():
    response = FakeResponse(
        content=[
            FakeBlock(type="server_tool_use", name="web_search", input={"query": "ICN to CDG flight price Nov 1 2026"}),
            FakeBlock(type="web_search_tool_result"),
            FakeBlock(
                type="tool_use",
                name="submit_flight_candidates",
                input={
                    "candidates": [
                        {
                            "carrier": "KE",
                            "price_usd": 812.5,
                            "departure_time": "t1",
                            "arrival_time": "t2",
                            "origin": "ICN",
                            "destination": "CDG",
                            "stops": 0,
                        }
                    ]
                },
            ),
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=200, output_tokens=40),
    )
    client = FakeClient([response])

    candidates, usage = await run_flight_agent(client, _brief())

    assert candidates == [
        FlightCandidate(carrier="KE", price_usd=812.5, departure_time="t1", arrival_time="t2", origin="ICN", destination="CDG", stops=0)
    ]
    assert usage.input_tokens == 200
    tool_types = {t.get("type") for t in client.messages.calls[0]["tools"]}
    assert "web_search_20250305" in tool_types


async def test_run_hotel_agent_searches_web_then_submits():
    response = FakeResponse(
        content=[
            FakeBlock(type="server_tool_use", name="web_search", input={"query": "Paris hotel Nov 1-5 2026 price"}),
            FakeBlock(type="web_search_tool_result"),
            FakeBlock(
                type="tool_use",
                name="submit_hotel_candidates",
                input={
                    "candidates": [
                        {"name": "Hotel Lumiere", "price_usd_per_night": 180.0, "rating": 4.3, "address": "Paris"}
                    ]
                },
            ),
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=190, output_tokens=38),
    )
    client = FakeClient([response])

    candidates, usage = await run_hotel_agent(client, _brief())

    assert candidates == [HotelCandidate(name="Hotel Lumiere", price_usd_per_night=180.0, rating=4.3, address="Paris")]
    assert usage.input_tokens == 190
    tool_types = {t.get("type") for t in client.messages.calls[0]["tools"]}
    assert "web_search_20250305" in tool_types
