"""Spatial hotspot / clustering helpers."""
from __future__ import annotations

from typing import Any


def centroid(points: list[dict[str, Any]]) -> tuple[float, float]:
    """Return the arithmetic mean *(lat, lon)* centroid of *points*.

    Each element must have ``"latitude"`` and ``"longitude"`` keys.
    """
    lats = [float(p["latitude"]) for p in points]
    lons = [float(p["longitude"]) for p in points]
    return sum(lats) / len(lats), sum(lons) / len(lons)
