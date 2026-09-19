import itertools
import math

from travel_agent.tools.weather_client import geocode

# Above this many stops, brute-force permutation (factorial growth) is no
# longer cheap enough to run per request; fall back to a nearest-neighbor
# greedy heuristic instead.
_EXACT_SOLVE_LIMIT = 7


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometers."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _route_length(coords: list[tuple[float, float]]) -> float:
    return sum(haversine_km(*coords[i], *coords[i + 1]) for i in range(len(coords) - 1))


def _best_order_exact(origin: tuple[float, float], stops: list[tuple[float, float]]) -> list[int]:
    best_indices: list[int] | None = None
    best_distance = float("inf")
    for perm in itertools.permutations(range(len(stops))):
        coords = [origin] + [stops[i] for i in perm] + [origin]
        distance = _route_length(coords)
        if distance < best_distance:
            best_distance = distance
            best_indices = list(perm)
    assert best_indices is not None
    return best_indices


def _best_order_greedy(origin: tuple[float, float], stops: list[tuple[float, float]]) -> list[int]:
    remaining = list(range(len(stops)))
    order: list[int] = []
    current = origin
    while remaining:
        nearest = min(remaining, key=lambda i: haversine_km(*current, *stops[i]))
        order.append(nearest)
        remaining.remove(nearest)
        current = stops[nearest]
    return order


async def optimize_route(origin: str, cities: list[str]) -> list[str]:
    """Return `cities` reordered to (approximately) minimize total travel
    distance for origin -> cities... -> origin, using real geocoded
    coordinates. Exact for up to 7 stops (brute-force permutation), a
    nearest-neighbor greedy heuristic above that. Raises WeatherAPIError
    (propagated from geocode) if any place can't be located -- callers
    should catch that and fall back to the un-optimized order."""
    if len(cities) <= 1:
        return list(cities)

    origin_coords = await geocode(origin)
    stop_coords = [await geocode(city) for city in cities]

    if len(cities) <= _EXACT_SOLVE_LIMIT:
        order = _best_order_exact(origin_coords, stop_coords)
    else:
        order = _best_order_greedy(origin_coords, stop_coords)

    return [cities[i] for i in order]
