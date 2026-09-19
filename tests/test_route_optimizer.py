import pytest

from travel_agent.tools import route_optimizer
from travel_agent.tools.weather_client import WeatherAPIError


def test_haversine_km_zero_for_same_point():
    assert route_optimizer.haversine_km(37.5, 127.0, 37.5, 127.0) == pytest.approx(0.0, abs=1e-6)


def test_haversine_km_seoul_to_tokyo_is_plausible():
    # Seoul (37.5665, 126.9780) to Tokyo (35.6762, 139.6503); real great-circle
    # distance is about 1160km.
    d = route_optimizer.haversine_km(37.5665, 126.9780, 35.6762, 139.6503)
    assert 1100 < d < 1250


async def test_optimize_route_returns_as_is_for_zero_or_one_city(monkeypatch):
    async def fail_geocode(place):
        raise AssertionError("should not geocode for 0 or 1 city")

    monkeypatch.setattr(route_optimizer, "geocode", fail_geocode)

    assert await route_optimizer.optimize_route("Origin", []) == []
    assert await route_optimizer.optimize_route("Origin", ["OnlyCity"]) == ["OnlyCity"]


async def test_optimize_route_keeps_nearby_cities_adjacent(monkeypatch):
    # "Far" is way off in another direction; "NearA"/"NearB" sit right next
    # to each other. Any optimal round trip from Origin should visit the two
    # close cities back-to-back rather than sandwiching Far between them.
    coords = {
        "Origin": (0.0, 0.0),
        "Far": (50.0, 50.0),
        "NearA": (0.0, 1.0),
        "NearB": (0.0, 1.1),
    }

    async def fake_geocode(place):
        return coords[place]

    monkeypatch.setattr(route_optimizer, "geocode", fake_geocode)

    order = await route_optimizer.optimize_route("Origin", ["Far", "NearA", "NearB"])

    assert set(order) == {"Far", "NearA", "NearB"}
    assert abs(order.index("NearA") - order.index("NearB")) == 1


async def test_optimize_route_propagates_geocode_failure(monkeypatch):
    async def failing_geocode(place):
        raise WeatherAPIError(f"no location found for {place!r}")

    monkeypatch.setattr(route_optimizer, "geocode", failing_geocode)

    with pytest.raises(WeatherAPIError):
        await route_optimizer.optimize_route("Origin", ["Nowhereville", "Elsewhere"])


async def test_optimize_route_falls_back_to_greedy_above_exact_solve_limit(monkeypatch):
    # 8 stops exceeds the brute-force limit (7); this should still return a
    # full, valid permutation via the greedy path instead of raising or
    # hanging on 8! permutations.
    cities = [f"City{i}" for i in range(8)]
    coords = {"Origin": (0.0, 0.0)}
    coords.update({city: (float(i), float(i)) for i, city in enumerate(cities, start=1)})

    async def fake_geocode(place):
        return coords[place]

    monkeypatch.setattr(route_optimizer, "geocode", fake_geocode)

    order = await route_optimizer.optimize_route("Origin", cities)

    assert sorted(order) == sorted(cities)
