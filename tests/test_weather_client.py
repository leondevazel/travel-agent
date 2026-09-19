import datetime

import httpx
import pytest
import respx

from travel_agent.tools.weather_client import WeatherAPIError, get_daily_summary

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


@respx.mock
async def test_get_daily_summary_returns_parsed_days():
    respx.get(GEOCODE_URL).mock(
        return_value=httpx.Response(200, json={"results": [{"latitude": 48.85, "longitude": 2.35}]})
    )
    respx.get(FORECAST_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "daily": {
                    "time": ["2026-11-01", "2026-11-02"],
                    "temperature_2m_max": [14.2, 13.8],
                    "temperature_2m_min": [7.1, 6.9],
                    "weathercode": [3, 61],
                }
            },
        )
    )

    days = await get_daily_summary("Paris", datetime.date(2026, 11, 1), datetime.date(2026, 11, 2))

    assert days == [
        {"date": "2026-11-01", "temp_max_c": 14.2, "temp_min_c": 7.1, "condition": "overcast"},
        {"date": "2026-11-02", "temp_max_c": 13.8, "temp_min_c": 6.9, "condition": "rain"},
    ]


@respx.mock
async def test_get_daily_summary_raises_when_city_not_found():
    respx.get(GEOCODE_URL).mock(return_value=httpx.Response(200, json={"results": []}))

    with pytest.raises(WeatherAPIError):
        await get_daily_summary("Nowhereville", datetime.date(2026, 11, 1), datetime.date(2026, 11, 2))


@respx.mock
async def test_get_daily_summary_raises_on_forecast_failure():
    respx.get(GEOCODE_URL).mock(
        return_value=httpx.Response(200, json={"results": [{"latitude": 48.85, "longitude": 2.35}]})
    )
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(500))

    with pytest.raises(WeatherAPIError):
        await get_daily_summary("Paris", datetime.date(2026, 11, 1), datetime.date(2026, 11, 2))
