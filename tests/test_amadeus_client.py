import httpx
import pytest
import respx

from travel_agent.tools.amadeus_client import AmadeusAPIError, AmadeusClient

BASE_URL = "https://test.api.amadeus.com"


@pytest.fixture
def client():
    return AmadeusClient(client_id="id", client_secret="secret", base_url=BASE_URL)


def _mock_token():
    respx.post(f"{BASE_URL}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-123", "expires_in": 1799})
    )


def _flight_payload(currency="USD"):
    return {
        "data": [
            {
                "price": {"total": "812.50", "currency": currency},
                "itineraries": [
                    {
                        "segments": [
                            {
                                "carrierCode": "KE",
                                "departure": {"iataCode": "ICN", "at": "2026-11-01T09:00:00"},
                                "arrival": {"iataCode": "CDG", "at": "2026-11-01T15:30:00"},
                            }
                        ]
                    }
                ],
            }
        ]
    }


def _hotel_payload(total="720.00", currency="USD"):
    return {
        "data": [
            {
                "hotel": {"name": "Hotel Lumiere", "rating": "4", "address": {"lines": ["12 Rue de Rivoli"]}},
                "offers": [{"price": {"total": total, "currency": currency}}],
            }
        ]
    }


@respx.mock
async def test_search_flights_returns_parsed_candidates(client):
    _mock_token()
    route = respx.get(f"{BASE_URL}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(200, json=_flight_payload())
    )

    offers = await client.search_flights("ICN", "CDG", "2026-11-01")

    assert offers == [
        {
            "carrier": "KE",
            "price_usd": 812.50,
            "departure_time": "2026-11-01T09:00:00",
            "arrival_time": "2026-11-01T15:30:00",
            "origin": "ICN",
            "destination": "CDG",
            "stops": 0,
        }
    ]
    assert route.calls.last.request.url.params["currencyCode"] == "USD"


@respx.mock
async def test_search_flights_raises_on_api_error(client):
    _mock_token()
    respx.get(f"{BASE_URL}/v2/shopping/flight-offers").mock(return_value=httpx.Response(429))

    with pytest.raises(AmadeusAPIError):
        await client.search_flights("ICN", "CDG", "2026-11-01")


@respx.mock
async def test_search_flights_raises_on_non_usd_currency(client):
    _mock_token()
    respx.get(f"{BASE_URL}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(200, json=_flight_payload(currency="EUR"))
    )

    with pytest.raises(AmadeusAPIError, match="EUR"):
        await client.search_flights("ICN", "CDG", "2026-11-01")


@respx.mock
async def test_search_hotels_divides_stay_total_into_per_night_price(client):
    _mock_token()
    respx.get(f"{BASE_URL}/v1/reference-data/locations/hotels/by-city").mock(
        return_value=httpx.Response(200, json={"data": [{"hotelId": "HTL1"}]})
    )
    # 720.00 total over 4 nights (2026-11-01 -> 2026-11-05) = 180.00 / night.
    route = respx.get(f"{BASE_URL}/v3/shopping/hotel-offers").mock(
        return_value=httpx.Response(200, json=_hotel_payload(total="720.00"))
    )

    offers = await client.search_hotels("PAR", "2026-11-01", "2026-11-05")

    assert offers == [
        {
            "name": "Hotel Lumiere",
            "price_usd_per_night": 180.0,
            "rating": 4.0,
            "address": "12 Rue de Rivoli",
        }
    ]
    assert route.calls.last.request.url.params["currencyCode"] == "USD"


@respx.mock
async def test_search_hotels_raises_on_non_usd_currency(client):
    _mock_token()
    respx.get(f"{BASE_URL}/v1/reference-data/locations/hotels/by-city").mock(
        return_value=httpx.Response(200, json={"data": [{"hotelId": "HTL1"}]})
    )
    respx.get(f"{BASE_URL}/v3/shopping/hotel-offers").mock(
        return_value=httpx.Response(200, json=_hotel_payload(currency="KRW"))
    )

    with pytest.raises(AmadeusAPIError, match="KRW"):
        await client.search_hotels("PAR", "2026-11-01", "2026-11-05")


@respx.mock
async def test_search_hotels_caps_hotel_ids_at_20(client):
    _mock_token()
    respx.get(f"{BASE_URL}/v1/reference-data/locations/hotels/by-city").mock(
        return_value=httpx.Response(200, json={"data": [{"hotelId": f"HTL{i}"} for i in range(50)]})
    )
    route = respx.get(f"{BASE_URL}/v3/shopping/hotel-offers").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    await client.search_hotels("PAR", "2026-11-01", "2026-11-05")

    sent_ids = route.calls.last.request.url.params["hotelIds"].split(",")
    assert len(sent_ids) == 20
    assert sent_ids[0] == "HTL0"


@respx.mock
async def test_search_hotels_rejects_non_positive_stay(client):
    _mock_token()

    with pytest.raises(AmadeusAPIError):
        await client.search_hotels("PAR", "2026-11-05", "2026-11-05")


@respx.mock
async def test_token_is_fetched_once_for_concurrent_searches(client):
    import asyncio

    token_route = respx.post(f"{BASE_URL}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-123", "expires_in": 1799})
    )
    respx.get(f"{BASE_URL}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(200, json=_flight_payload())
    )
    respx.get(f"{BASE_URL}/v1/reference-data/locations/hotels/by-city").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    await asyncio.gather(
        client.search_flights("ICN", "CDG", "2026-11-01"),
        client.search_hotels("PAR", "2026-11-01", "2026-11-05"),
    )

    assert token_route.call_count == 1
