"""Temporal helpers for geographic time-series data."""
from __future__ import annotations

from datetime import datetime, timezone

TIMESTAMP_FORMATS: tuple[str, ...] = (
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)


def parse_ts(ts_str: str) -> float | None:
    """Try to parse an ISO 8601 timestamp string; return POSIX seconds or ``None``."""
    for fmt in TIMESTAMP_FORMATS:
        try:
            dt = datetime.strptime(ts_str, fmt).replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    return None
