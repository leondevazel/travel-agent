from dataclasses import dataclass, field

from travel_agent.agents.flight_agent import _route_legs, run_flight_agent
from travel_agent.agents.hotel_agent import _cities, run_hotel_agent
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


async def test_flight_candidate_accepts_price_without_schedule_details():
    # Real failure this guards: requiring departure/arrival/stops made the
    # agent refuse to submit anything when search gave a carrier and a fare
    # but no timetable, so the UI showed no flights at all.
    response = FakeResponse(
        content=[
            FakeBlock(type="server_tool_use", name="web_search", input={"query": "Busan to Seoul flight price"}),
            FakeBlock(type="web_search_tool_result"),
            FakeBlock(
                type="tool_use",
                name="submit_flight_candidates",
                input={
                    "candidates": [
                        {
                            "carrier": "Air Busan",
                            "price_usd": 48.0,
                            "origin": "Busan",
                            "destination": "Seoul",
                            "booking_url": "https://www.skyscanner.net/routes/pus/sel",
                        }
                    ]
                },
            ),
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=120, output_tokens=30),
    )
    client = FakeClient([response])

    candidates, _ = await run_flight_agent(client, _brief())

    assert len(candidates) == 1
    assert candidates[0].carrier == "Air Busan"
    assert candidates[0].departure_time is None
    assert candidates[0].booking_url == "https://www.skyscanner.net/routes/pus/sel"


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


def test_route_legs_empty_for_single_city_trip():
    assert _route_legs(_brief()) == []


def test_route_legs_chains_origin_through_cities_and_back():
    brief = _brief().model_copy(update={"additional_destinations": ["Rome", "Barcelona"]})

    assert _route_legs(brief) == [
        ("ICN", "Paris"),
        ("Paris", "Rome"),
        ("Rome", "Barcelona"),
        ("Barcelona", "ICN"),
    ]


def test_cities_lists_destination_then_additional_destinations():
    brief = _brief().model_copy(update={"additional_destinations": ["Rome"]})
    assert _cities(brief) == ["Paris", "Rome"]


async def test_run_flight_agent_multi_city_submits_candidates_per_leg():
    response = FakeResponse(
        content=[
            FakeBlock(type="server_tool_use", name="web_search", input={"query": "ICN to Tokyo flight"}),
            FakeBlock(type="web_search_tool_result"),
            FakeBlock(
                type="tool_use",
                name="submit_flight_candidates",
                input={
                    "candidates": [
                        {
                            "carrier": "ANA",
                            "price_usd": 400.0,
                            "departure_time": "t1",
                            "arrival_time": "t2",
                            "origin": "ICN",
                            "destination": "Tokyo",
                            "stops": 0,
                        },
                        {
                            "carrier": "JAL",
                            "price_usd": 150.0,
                            "departure_time": "t3",
                            "arrival_time": "t4",
                            "origin": "Tokyo",
                            "destination": "Osaka",
                            "stops": 0,
                        },
                        {
                            "carrier": "ANA",
                            "price_usd": 420.0,
                            "departure_time": "t5",
                            "arrival_time": "t6",
                            "origin": "Osaka",
                            "destination": "ICN",
                            "stops": 0,
                        },
                    ]
                },
            ),
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=300, output_tokens=60),
    )
    client = FakeClient([response])
    brief = TripBrief(
        destination="Tokyo",
        origin="ICN",
        additional_destinations=["Osaka"],
        start_date="2026-11-01",
        end_date="2026-11-08",
        budget_usd=2000.0,
    )

    candidates, usage = await run_flight_agent(client, brief)

    assert [(c.origin, c.destination) for c in candidates] == [("ICN", "Tokyo"), ("Tokyo", "Osaka"), ("Osaka", "ICN")]
    sent_message = client.messages.calls[0]["messages"][0]["content"]
    assert "ICN -> Tokyo" in sent_message
    assert "Tokyo -> Osaka" in sent_message
    assert "Osaka -> ICN" in sent_message
    # 2 legs (ICN->Tokyo->Osaka) + return leg = 3 legs total -> more search
    # budget than the single-city case.
    web_search_tool = next(t for t in client.messages.calls[0]["tools"] if t.get("type") == "web_search_20250305")
    assert web_search_tool["max_uses"] > 2


async def test_run_hotel_agent_multi_city_mentions_every_city():
    response = FakeResponse(
        content=[
            FakeBlock(type="server_tool_use", name="web_search", input={"query": "Tokyo hotel"}),
            FakeBlock(type="web_search_tool_result"),
            FakeBlock(
                type="tool_use",
                name="submit_hotel_candidates",
                input={
                    "candidates": [
                        {"name": "Tokyo Inn", "price_usd_per_night": 120.0, "rating": 4.0, "address": "Tokyo"},
                        {"name": "Osaka Stay", "price_usd_per_night": 90.0, "rating": 4.1, "address": "Osaka"},
                    ]
                },
            ),
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=250, output_tokens=50),
    )
    client = FakeClient([response])
    brief = TripBrief(
        destination="Tokyo",
        origin="ICN",
        additional_destinations=["Osaka"],
        start_date="2026-11-01",
        end_date="2026-11-08",
        budget_usd=2000.0,
    )

    candidates, usage = await run_hotel_agent(client, brief)

    assert len(candidates) == 2
    sent_message = client.messages.calls[0]["messages"][0]["content"]
    assert "Tokyo" in sent_message
    assert "Osaka" in sent_message
    web_search_tool = next(t for t in client.messages.calls[0]["tools"] if t.get("type") == "web_search_20250305")
    assert web_search_tool["max_uses"] > 2
