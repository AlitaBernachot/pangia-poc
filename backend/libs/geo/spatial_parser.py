"""Spatial text-parsing helpers: regex patterns and coordinate extraction."""
from __future__ import annotations

import re

# Regex patterns for detecting coordinate expressions in text
COORD_PATTERNS: list[str] = [
    r"(-?\d{1,3}\.\d+)\s*[,;]\s*(-?\d{1,3}\.\d+)",
    r"(\d{1,3})°\s*(\d{1,2})['′]\s*(\d{1,2}(?:\.\d+)?)[\"″]?\s*([NS])\s+"
    r"(\d{1,3})°\s*(\d{1,2})['′]\s*(\d{1,2}(?:\.\d+)?)[\"″]?\s*([EW])",
    r"lat(?:itude)?\s*[=:]\s*(-?\d+\.?\d*)",
    r"lon(?:gitude)?\s*[=:]\s*(-?\d+\.?\d*)",
]

# Regex for DMS notation: 48°51'23"N 2°21'08"E
DMS_PATTERN: re.Pattern[str] = re.compile(
    r"(\d{1,3})°\s*(\d{1,2})['′]\s*(\d{1,2}(?:\.\d+)?)[\"″]?\s*([NS])\s+"
    r"(\d{1,3})°\s*(\d{1,2})['′]\s*(\d{1,2}(?:\.\d+)?)[\"″]?\s*([EW])",
    re.IGNORECASE,
)

# Spatial relationship keywords
SPATIAL_KEYWORDS: list[str] = [
    r"\bnear\b", r"\bwithin\b", r"\binside\b", r"\boutside\b",
    r"\bnorth\s+of\b", r"\bsouth\s+of\b", r"\beast\s+of\b", r"\bwest\s+of\b",
    r"\bcontains\b", r"\bintersects\b", r"\badjacent\s+to\b",
    r"\bbetween\b", r"\balong\b", r"\bacross\b",
    r"\bprès\s+de\b", r"\bdans\b", r"\bau\s+nord\s+de\b", r"\bau\s+sud\s+de\b",
    r"\bà\s+l[''']est\s+de\b", r"\bà\s+l[''']ouest\s+de\b",
]

# Distance expressions
DISTANCE_PATTERNS: list[str] = [
    r"(\d+(?:\.\d+)?)\s*(km|kilomet(?:re|er)s?|miles?|m\b|meters?|metres?)",
    r"within\s+(\d+(?:\.\d+)?)\s*(km|miles?|meters?|metres?)",
]


def dms_to_decimal(deg: float, minutes: float, seconds: float, hemisphere: str) -> float:
    """Convert a DMS coordinate to decimal degrees; *hemisphere* is ``'N'``, ``'S'``, ``'E'``, or ``'W'``."""
    value = deg + minutes / 60 + seconds / 3600
    if hemisphere.upper() in ("S", "W"):
        value = -value
    return value
