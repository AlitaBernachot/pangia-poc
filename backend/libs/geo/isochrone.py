"""Isochrone polygon helpers."""
from __future__ import annotations

from libs.geo.geodesy import destination_point

# Approximate travel speeds in m/s
SPEEDS_MS: dict[str, float] = {
    "walking": 1.4,          # ~5 km/h
    "cycling": 4.2,          # ~15 km/h
    "driving": 13.9,         # ~50 km/h (urban)
    "driving_highway": 27.8, # ~100 km/h (highway)
}


def isochrone_polygon(
    lat: float,
    lon: float,
    radius_m: float,
    n_vertices: int = 64,
) -> list[list[float]]:
    """Return a closed GeoJSON ring ``[[lon, lat], ...]`` for an isochrone circle.

    The polygon is approximated by *n_vertices* equally-spaced points on a
    geodesic circle of *radius_m* metres centred at *(lat, lon)*.
    """
    coords: list[list[float]] = []
    for i in range(n_vertices):
        bearing = 360.0 * i / n_vertices
        dlat, dlon = destination_point(lat, lon, bearing, radius_m)
        coords.append([round(dlon, 7), round(dlat, 7)])
    coords.append(coords[0])
    return coords
