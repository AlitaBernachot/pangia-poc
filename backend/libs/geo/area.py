"""Geographic area calculation helpers."""
from __future__ import annotations

import math

from libs.geo.geodesy import EARTH_RADIUS_M

# Reference areas in km² for comparison
REFERENCE_AREAS_KM2: dict[str, float] = {
    "France": 551_695,
    "Germany": 357_114,
    "Spain": 505_990,
    "UK": 243_610,
    "Italy": 301_340,
    "Belgium": 30_528,
    "Switzerland": 41_285,
    "Paris (city)": 105.4,
    "London (Greater)": 1_572,
    "Central Park NYC": 3.41,
}


def spherical_polygon_area(coords: list[tuple[float, float]]) -> float:
    """Compute the area of a spherical polygon in m² using the spherical excess formula.

    *coords* is a list of *(lat, lon)* pairs in decimal degrees.
    """
    n = len(coords)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        j = (i + 1) % n
        lat1, lon1 = math.radians(coords[i][0]), math.radians(coords[i][1])
        lat2, lon2 = math.radians(coords[j][0]), math.radians(coords[j][1])
        total += (lon2 - lon1) * (2 + math.sin(lat1) + math.sin(lat2))
    return abs(total) * EARTH_RADIUS_M**2 / 2


def format_area(m2: float) -> dict[str, float]:
    """Return *m2* expressed as a dict with m², km², hectares, acres, and sq_miles."""
    return {
        "m2": round(m2, 2),
        "km2": round(m2 / 1_000_000, 6),
        "hectares": round(m2 / 10_000, 4),
        "acres": round(m2 / 4046.856, 4),
        "sq_miles": round(m2 / 2_589_988.11, 6),
    }
