import time

import httpx


class AmadeusAPIError(Exception):
    pass


class AmadeusClient:
    def __init__(self, client_id: str, client_secret: str, base_url: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = base_url.rstrip("/")
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def _get_token(self, http: httpx.AsyncClient) -> str:
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

            resp = await http.get(
                f"{self._base_url}/v3/shopping/hotel-offers",
                params={"hotelIds": ",".join(hotel_ids), "checkInDate": check_in, "checkOutDate": check_out},
                headers=headers,
            )
            if resp.status_code != 200:
                raise AmadeusAPIError(f"hotel offers failed: {resp.status_code}")
            return [self._parse_hotel_offer(entry) for entry in resp.json().get("data", [])]

    def _parse_hotel_offer(self, entry: dict) -> dict:
        hotel = entry["hotel"]
        offer = entry["offers"][0]
        return {
            "name": hotel["name"],
            "price_usd_per_night": float(offer["price"]["total"]),
            "rating": float(hotel["rating"]) if hotel.get("rating") else None,
            "address": ", ".join(hotel.get("address", {}).get("lines", [])),
        }
