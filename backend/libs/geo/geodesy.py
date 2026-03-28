"""Shared geodetic constants and helper functions.

Used across all geo lib modules – never import from app.agent here.
"""
from __future__ import annotations

import math

EARTH_RADIUS_M: float = 6_371_000.0  # Mean Earth radius in metres


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in metres using the Haversine formula."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def destination_point(
    lat: float, lon: float, bearing_deg: float, dist_m: float
) -> tuple[float, float]:
    """Return *(lat, lon)* of the point at *dist_m* metres and *bearing_deg* from origin."""
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    bearing_r = math.radians(bearing_deg)
    angular = dist_m / EARTH_RADIUS_M
    dest_lat = math.asin(
        math.sin(lat_r) * math.cos(angular)
        + math.cos(lat_r) * math.sin(angular) * math.cos(bearing_r)
    )
    dest_lon = lon_r + math.atan2(
        math.sin(bearing_r) * math.sin(angular) * math.cos(lat_r),
        math.cos(angular) - math.sin(lat_r) * math.sin(dest_lat),
    )
    return math.degrees(dest_lat), math.degrees(dest_lon)


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the initial bearing from point 1 to point 2 in degrees [0, 360)."""
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(lat2_r)
    y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def format_distance(metres: float) -> dict[str, float]:
    """Return *metres* expressed as a dict with metres, kilometres, miles, and nautical miles."""
    return {
        "metres": round(metres, 2),
        "kilometres": round(metres / 1000, 4),
        "miles": round(metres / 1609.344, 4),
        "nautical_miles": round(metres / 1852, 4),
    }
