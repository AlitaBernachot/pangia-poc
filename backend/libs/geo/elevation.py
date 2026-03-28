"""Open-Meteo elevation API helper."""
from __future__ import annotations

import httpx

_OPEN_METEO_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"


async def fetch_open_meteo_elevation(
    locations: list[dict[str, float]],
) -> list[float | None]:
    """Fetch elevation (metres ASL) for *locations* from the Open-Meteo API (no key required).

    *locations* must be a list of dicts with ``"latitude"`` and ``"longitude"`` keys.
    Returns a list of floats (or ``None`` where the API returned no value).
    """
    lats = ",".join(str(loc["latitude"]) for loc in locations)
    lons = ",".join(str(loc["longitude"]) for loc in locations)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                _OPEN_METEO_ELEVATION_URL,
                params={"latitude": lats, "longitude": lons},
            )
            resp.raise_for_status()
            data = resp.json()
        elevations = data.get("elevation", [])
        return [float(e) if e is not None else None for e in elevations]
    except Exception:  # noqa: BLE001
        return [None] * len(locations)
