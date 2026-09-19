import httpx
import pytest
import respx

from travel_agent.tools.amadeus_client import AmadeusAPIError, AmadeusClient

BASE_URL = "https://test.api.amadeus.com"


@pytest.fixture
def client():
    return AmadeusClient(client_id="id", client_secret="secret", base_url=BASE_URL)


@respx.mock
async def test_search_flights_returns_parsed_candidates(client):
    respx.post(f"{BASE_URL}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-123", "expires_in": 1799})
    )
    respx.get(f"{BASE_URL}/v2/shopping/flight-offers").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "price": {"total": "812.50"},
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
            },
        )
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


@respx.mock
async def test_search_flights_raises_on_api_error(client):
    respx.post(f"{BASE_URL}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-123", "expires_in": 1799})
    )
    respx.get(f"{BASE_URL}/v2/shopping/flight-offers").mock(return_value=httpx.Response(429))

    with pytest.raises(AmadeusAPIError):
        await client.search_flights("ICN", "CDG", "2026-11-01")


@respx.mock
async def test_search_hotels_returns_parsed_candidates(client):
    respx.post(f"{BASE_URL}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-123", "expires_in": 1799})
    )
    respx.get(f"{BASE_URL}/v1/reference-data/locations/hotels/by-city").mock(
        return_value=httpx.Response(200, json={"data": [{"hotelId": "HTL1"}]})
    )
    respx.get(f"{BASE_URL}/v3/shopping/hotel-offers").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "hotel": {"name": "Hotel Lumiere", "rating": "4", "address": {"lines": ["12 Rue de Rivoli"]}},
                        "offers": [{"price": {"total": "180.00"}}],
                    }
                ]
            },
        )
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
