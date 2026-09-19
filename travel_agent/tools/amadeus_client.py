import asyncio
import datetime
import time

import httpx

# Amadeus can return hundreds of hotel ids for a city; the hotel-offers query
# takes them as a comma-joined query string, so cap it to keep the URL sane.
MAX_HOTEL_IDS = 20

EXPECTED_CURRENCY = "USD"


class AmadeusAPIError(Exception):
    pass


class AmadeusClient:
    def __init__(self, client_id: str, client_secret: str, base_url: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = base_url.rstrip("/")
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def _get_token(self, http: httpx.AsyncClient) -> str:
        # Flight and Hotel agents run concurrently, so serialize the
        # check-and-refresh to avoid two cold-start token fetches.
        async with self._token_lock:
            if self._token and time.monotonic() < self._token_expires_at:
                return self._token
            resp = await http.post(
                f"{self._base_url}/v1/security/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            if resp.status_code != 200:
                raise AmadeusAPIError(f"token request failed: {resp.status_code}")
            body = resp.json()
            self._token = body["access_token"]
            self._token_expires_at = time.monotonic() + body["expires_in"] - 30
            return self._token

    async def search_flights(
        self, origin: str, destination: str, departure_date: str, return_date: str | None = None, adults: int = 1
    ) -> list[dict]:
        async with httpx.AsyncClient() as http:
            token = await self._get_token(http)
            params = {
                "originLocationCode": origin,
                "destinationLocationCode": destination,
                "departureDate": departure_date,
                "adults": adults,
                "currencyCode": EXPECTED_CURRENCY,
            }
            if return_date:
                params["returnDate"] = return_date
            resp = await http.get(
                f"{self._base_url}/v2/shopping/flight-offers",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                raise AmadeusAPIError(f"flight search failed: {resp.status_code}")
            data = resp.json().get("data", [])
            return [self._parse_flight_offer(offer) for offer in data]

    def _parse_flight_offer(self, offer: dict) -> dict:
        segments = offer["itineraries"][0]["segments"]
        first, last = segments[0], segments[-1]
        _check_currency(offer["price"].get("currency"), "flight offer")
        return {
            "carrier": first["carrierCode"],
            "price_usd": float(offer["price"]["total"]),
            "departure_time": first["departure"]["at"],
            "arrival_time": last["arrival"]["at"],
            "origin": first["departure"]["iataCode"],
            "destination": last["arrival"]["iataCode"],
            "stops": len(segments) - 1,
        }

    async def search_hotels(self, city_code: str, check_in: str, check_out: str) -> list[dict]:
        nights = _night_count(check_in, check_out)
        async with httpx.AsyncClient() as http:
            token = await self._get_token(http)
            headers = {"Authorization": f"Bearer {token}"}

            resp = await http.get(
                f"{self._base_url}/v1/reference-data/locations/hotels/by-city",
                params={"cityCode": city_code},
                headers=headers,
            )
            if resp.status_code != 200:
                raise AmadeusAPIError(f"hotel lookup failed: {resp.status_code}")
            hotel_ids = [h["hotelId"] for h in resp.json().get("data", [])]
            if not hotel_ids:
                return []
            hotel_ids = hotel_ids[:MAX_HOTEL_IDS]

            resp = await http.get(
                f"{self._base_url}/v3/shopping/hotel-offers",
                params={
                    "hotelIds": ",".join(hotel_ids),
                    "checkInDate": check_in,
                    "checkOutDate": check_out,
                    "currencyCode": EXPECTED_CURRENCY,
                },
                headers=headers,
            )
            if resp.status_code != 200:
                raise AmadeusAPIError(f"hotel offers failed: {resp.status_code}")
            return [self._parse_hotel_offer(entry, nights) for entry in resp.json().get("data", [])]

    def _parse_hotel_offer(self, entry: dict, nights: int) -> dict:
        hotel = entry["hotel"]
        offer = entry["offers"][0]
        _check_currency(offer["price"].get("currency"), "hotel offer")
        # Amadeus `price.total` covers the whole check-in -> check-out stay.
        total = float(offer["price"]["total"])
        return {
            "name": hotel["name"],
            "price_usd_per_night": round(total / nights, 2),
            "rating": float(hotel["rating"]) if hotel.get("rating") else None,
            "address": ", ".join(hotel.get("address", {}).get("lines", [])),
        }


def _check_currency(currency: str | None, what: str) -> None:
    """Never let a non-USD price through as a USD one.

    We always request ``currencyCode=USD``, so a compliant response echoes it
    back; a missing or different currency means we cannot trust the number.
    """
    if currency != EXPECTED_CURRENCY:
        raise AmadeusAPIError(f"{what} priced in {currency!r}, expected {EXPECTED_CURRENCY!r}")


def _night_count(check_in: str, check_out: str) -> int:
    try:
        nights = (datetime.date.fromisoformat(check_out) - datetime.date.fromisoformat(check_in)).days
    except ValueError as exc:
        raise AmadeusAPIError(f"invalid check-in/check-out dates: {check_in!r}/{check_out!r}") from exc
    if nights < 1:
        raise AmadeusAPIError(f"check_out {check_out!r} must be after check_in {check_in!r}")
    return nights
