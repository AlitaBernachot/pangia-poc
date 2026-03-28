"""GeoJSON geometry helpers: coordinate collection, simplification, and validation."""
from __future__ import annotations

import math
from typing import Any


def collect_coords(geometry: dict[str, Any]) -> list[list[float]]:
    """Recursively collect all ``[lon, lat]`` coordinate pairs from a GeoJSON geometry."""
    gtype = geometry.get("type", "")
    raw = geometry.get("coordinates", [])
    if gtype == "Point":
        return [raw] if raw else []
    if gtype in ("MultiPoint", "LineString"):
        return list(raw)
    if gtype in ("MultiLineString", "Polygon"):
        return [c for ring in raw for c in ring]
    if gtype == "MultiPolygon":
        return [c for poly in raw for ring in poly for c in ring]
    if gtype == "GeometryCollection":
        return [c for g in geometry.get("geometries", []) for c in collect_coords(g)]
    return []


def perpendicular_distance(
    point: list[float],
    line_start: list[float],
    line_end: list[float],
) -> float:
    """Compute the perpendicular distance from *point* to the line defined by the two endpoints."""
    if line_start == line_end:
        return math.hypot(point[0] - line_start[0], point[1] - line_start[1])
    dx = line_end[0] - line_start[0]
    dy = line_end[1] - line_start[1]
    d = abs(
        dy * point[0]
        - dx * point[1]
        + line_end[0] * line_start[1]
        - line_end[1] * line_start[0]
    )
    return d / math.hypot(dx, dy)


def rdp(coords: list[list[float]], epsilon: float) -> list[list[float]]:
    """Simplify *coords* using the Ramer-Douglas-Peucker algorithm with tolerance *epsilon*."""
    if len(coords) < 3:
        return coords
    max_dist = 0.0
    max_idx = 0
    for i in range(1, len(coords) - 1):
        d = perpendicular_distance(coords[i], coords[0], coords[-1])
        if d > max_dist:
            max_dist = d
            max_idx = i
    if max_dist > epsilon:
        left = rdp(coords[: max_idx + 1], epsilon)
        right = rdp(coords[max_idx:], epsilon)
        return left[:-1] + right
    return [coords[0], coords[-1]]
