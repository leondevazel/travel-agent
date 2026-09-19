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


class FakeAmadeus:
    def __init__(self, flight_results=None, hotel_results=None):
        self.flight_results = flight_results or []
        self.hotel_results = hotel_results or []
        self.flight_calls = []
        self.hotel_calls = []

    async def search_flights(self, origin, destination, departure_date, return_date=None, adults=1):
        self.flight_calls.append((origin, destination, departure_date, return_date))
        return self.flight_results

    async def search_hotels(self, city_code, check_in, check_out):
        self.hotel_calls.append((city_code, check_in, check_out))
        return self.hotel_results


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


async def test_run_flight_agent_searches_then_submits():
    search_call = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                name="search_flights",
                input={"origin": "ICN", "destination": "CDG", "departure_date": "2026-11-01", "return_date": "2026-11-05"},
                id="call-1",
            )
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=100, output_tokens=20),
    )
    submit_call = FakeResponse(
        content=[
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
            )
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=60, output_tokens=15),
    )
    client = FakeClient([search_call, submit_call])
    amadeus = FakeAmadeus(
        flight_results=[
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
    )

    candidates, usage = await run_flight_agent(client, _brief(), amadeus)

    assert candidates == [
        FlightCandidate(carrier="KE", price_usd=812.5, departure_time="t1", arrival_time="t2", origin="ICN", destination="CDG", stops=0)
    ]
    assert amadeus.flight_calls == [("ICN", "CDG", "2026-11-01", "2026-11-05")]
    assert usage.input_tokens == 160


async def test_run_hotel_agent_searches_then_submits():
    search_call = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                name="search_hotels",
                input={"city_code": "PAR", "check_in": "2026-11-01", "check_out": "2026-11-05"},
                id="call-1",
            )
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=90, output_tokens=18),
    )
    submit_call = FakeResponse(
        content=[
            FakeBlock(
                type="tool_use",
                name="submit_hotel_candidates",
                input={
                    "candidates": [
                        {"name": "Hotel Lumiere", "price_usd_per_night": 180.0, "rating": 4.3, "address": "Paris"}
                    ]
                },
            )
        ],
        stop_reason="tool_use",
        usage=FakeUsage(input_tokens=55, output_tokens=12),
    )
    client = FakeClient([search_call, submit_call])
    amadeus = FakeAmadeus(
        hotel_results=[{"name": "Hotel Lumiere", "price_usd_per_night": 180.0, "rating": 4.3, "address": "Paris"}]
    )

    candidates, usage = await run_hotel_agent(client, _brief(), amadeus)

    assert candidates == [HotelCandidate(name="Hotel Lumiere", price_usd_per_night=180.0, rating=4.3, address="Paris")]
    assert amadeus.hotel_calls == [("PAR", "2026-11-01", "2026-11-05")]
    assert usage.input_tokens == 145
