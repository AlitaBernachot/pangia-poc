"""Route distance and travel-time helpers."""
from __future__ import annotations

from typing import Any

from libs.geo.geodesy import haversine

# Approximate travel speeds in m/s
TRAVEL_SPEEDS_MS: dict[str, float] = {
    "walking": 1.4,   # ~5 km/h
    "cycling": 4.2,   # ~15 km/h
    "driving": 13.9,  # ~50 km/h
}


def route_distance(waypoints: list[dict[str, Any]]) -> float:
    """Return the total straight-line distance in metres along *waypoints*.

    Each element must have ``"latitude"`` and ``"longitude"`` keys.
    """
    total = 0.0
    for i in range(len(waypoints) - 1):
        total += haversine(
            float(waypoints[i]["latitude"]),
            float(waypoints[i]["longitude"]),
            float(waypoints[i + 1]["latitude"]),
            float(waypoints[i + 1]["longitude"]),
        )
    return total
