"""Viewshed / line-of-sight geometric helpers."""
from __future__ import annotations

import math

from libs.geo.geodesy import EARTH_RADIUS_M

REFRACTION_COEFF: float = 0.13


def effective_earth_radius() -> float:
    """Return the Earth radius corrected for standard atmospheric refraction."""
    return EARTH_RADIUS_M / (1 - REFRACTION_COEFF)


def horizon_distance_m(observer_height_m: float, target_height_m: float = 0.0) -> float:
    """Return the geometric horizon distance in metres accounting for atmospheric refraction.

    ``d = sqrt(2 * R_eff * h_obs) + sqrt(2 * R_eff * h_target)``
    """
    r = effective_earth_radius()
    return math.sqrt(2 * r * observer_height_m) + math.sqrt(2 * r * target_height_m)
