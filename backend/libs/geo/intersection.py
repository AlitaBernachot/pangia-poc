"""Bounding-box intersection helpers."""
from __future__ import annotations

import json


def parse_bbox(bbox_json: str) -> tuple[float, float, float, float] | None:
    """Parse *bbox_json* into a *(west, south, east, north)* tuple, or return ``None`` on error.

    Accepts either a JSON array ``[min_lon, min_lat, max_lon, max_lat]`` or a dict
    with ``west``, ``south``, ``east``, ``north`` keys.
    """
    try:
        b = json.loads(bbox_json)
        if isinstance(b, dict):
            return (float(b["west"]), float(b["south"]), float(b["east"]), float(b["north"]))
        if isinstance(b, list) and len(b) == 4:
            return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        pass
    return None


def bbox_area_deg2(w: float, s: float, e: float, n: float) -> float:
    """Return the area of a bounding box in square degrees."""
    return max(0.0, e - w) * max(0.0, n - s)
