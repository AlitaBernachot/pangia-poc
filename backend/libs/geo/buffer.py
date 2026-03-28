"""Geographic buffer (offset polygon) helpers."""
from __future__ import annotations

from libs.geo.geodesy import destination_point


def circular_buffer_coords(
    lat: float,
    lon: float,
    radius_m: float,
    n_vertices: int = 64,
) -> list[list[float]]:
    """Return a closed GeoJSON ring ``[[lon, lat], ...]`` for a circular buffer.

    The polygon is approximated by *n_vertices* equally-spaced points on a
    geodesic circle of *radius_m* metres centred at *(lat, lon)*.
    The first and last point are identical (closed ring).
    """
    coords: list[list[float]] = []
    for i in range(n_vertices):
        bearing_deg = 360.0 * i / n_vertices
        dlat, dlon = destination_point(lat, lon, bearing_deg, radius_m)
        coords.append([round(dlon, 7), round(dlat, 7)])
    coords.append(coords[0])
    return coords
