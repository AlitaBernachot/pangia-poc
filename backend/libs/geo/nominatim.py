"""OpenStreetMap Nominatim HTTP helper functions.

Raw async functions that call the Nominatim REST API and return Python dicts/lists.
No LangChain, no JSON serialisation – those concerns belong in the agent tool wrappers.
"""
from __future__ import annotations

import httpx

NOMINATIM_BASE: str = "https://nominatim.openstreetmap.org"
HEADERS: dict[str, str] = {"User-Agent": "PangIA-GeoIA/0.1 (contact@pangia.io)"}


async def nominatim_search(
    address: str,
    countrycodes: str = "",
    limit: int = 3,
) -> list[dict]:
    """Search Nominatim for *address* and return raw result list (may be empty)."""
    params: dict = {"q": address, "format": "json", "limit": limit, "addressdetails": 1}
    if countrycodes:
        params["countrycodes"] = countrycodes
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{NOMINATIM_BASE}/search", params=params, headers=HEADERS)
        resp.raise_for_status()
        return resp.json()  # type: ignore[return-value]


async def nominatim_reverse(latitude: float, longitude: float) -> dict:
    """Reverse-geocode *(latitude, longitude)* and return the raw Nominatim result dict."""
    params = {"lat": latitude, "lon": longitude, "format": "json", "addressdetails": 1}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{NOMINATIM_BASE}/reverse", params=params, headers=HEADERS)
        resp.raise_for_status()
        return resp.json()  # type: ignore[return-value]


async def nominatim_batch_search(addresses: list[str]) -> list[dict]:
    """Geocode each address in *addresses* (limit=1 per query) and return a flat list of results.

    Each result dict contains the original *address* key plus the raw Nominatim hit
    (or ``{"address": ..., "found": False}`` when nothing is found).
    """
    results: list[dict] = []
    for address in addresses:
        params = {"q": address, "format": "json", "limit": 1}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{NOMINATIM_BASE}/search", params=params, headers=HEADERS
                )
                resp.raise_for_status()
                hits: list[dict] = resp.json()
            if not hits:
                results.append({"address": address, "found": False})
            else:
                r = hits[0]
                results.append(
                    {
                        "address": address,
                        "found": True,
                        "latitude": float(r["lat"]),
                        "longitude": float(r["lon"]),
                        "display_name": r.get("display_name", address),
                        "place_type": r.get("type", ""),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            results.append({"address": address, "error": str(exc)})
    return results
