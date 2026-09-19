import datetime

import httpx

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_WMO_CONDITIONS = {
    0: "clear",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "fog",
    51: "drizzle",
    61: "rain",
    63: "rain",
    65: "heavy rain",
    71: "snow",
    73: "snow",
    75: "heavy snow",
    80: "rain showers",
    95: "thunderstorm",
}


class WeatherAPIError(Exception):
    pass


def _condition_for(code: int) -> str:
    return _WMO_CONDITIONS.get(code, "unknown")


async def _geocode(http: httpx.AsyncClient, place: str) -> tuple[float, float]:
    geo_resp = await http.get(GEOCODE_URL, params={"name": place, "count": 1})
    if geo_resp.status_code != 200:
        raise WeatherAPIError(f"geocoding failed: {geo_resp.status_code}")
    results = geo_resp.json().get("results") or []
    if not results:
        raise WeatherAPIError(f"no location found for {place!r}")
    return results[0]["latitude"], results[0]["longitude"]


async def geocode(place: str) -> tuple[float, float]:
    """Look up (latitude, longitude) for a place name. Raises WeatherAPIError
    if the place can't be found or the geocoding API fails."""
    async with httpx.AsyncClient() as http:
        return await _geocode(http, place)


async def get_daily_summary(destination: str, start_date: datetime.date, end_date: datetime.date) -> list[dict]:
    async with httpx.AsyncClient() as http:
        lat, lon = await _geocode(http, destination)

        forecast_resp = await http.get(
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,weathercode",
                "timezone": "auto",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )
        if forecast_resp.status_code != 200:
            raise WeatherAPIError(f"forecast failed: {forecast_resp.status_code}")

        daily = forecast_resp.json()["daily"]
        return [
            {
                "date": date,
                "temp_max_c": temp_max,
                "temp_min_c": temp_min,
                "condition": _condition_for(code),
            }
            for date, temp_max, temp_min, code in zip(
                daily["time"], daily["temperature_2m_max"], daily["temperature_2m_min"], daily["weathercode"]
            )
        ]
