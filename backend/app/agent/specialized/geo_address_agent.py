"""
Geo Address Agent – geocoding and reverse-geocoding.

Specialises in:
  • Converting addresses and place names to geographic coordinates (geocoding)
  • Converting geographic coordinates to human-readable addresses (reverse geocoding)
  • Batch geocoding of multiple locations
  • Normalising and validating addresses

Exposed as a single async function `run` usable as a LangGraph node or called
directly by the geo_agent orchestrator.
"""
from __future__ import annotations

import json

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agent.model_config import build_llm, get_agent_model_config, get_agent_max_iterations
from app.agent.state import AgentState

_NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
_HEADERS = {"User-Agent": "PangIA-GeoIA/0.1 (contact@pangia.io)"}

_SYSTEM_PROMPT = """You are the Geocoding Agent of the PangIA GeoIA platform.
Your role is to resolve geographic references (addresses, place names, regions) to
coordinates and vice-versa.

## Capabilities
- `geocode_address`: Convert an address or place name to latitude/longitude.
- `reverse_geocode`: Convert latitude/longitude coordinates to a human-readable address.
- `batch_geocode`: Geocode multiple addresses in a single call.

## Guidelines
- Always prefer the most precise result available.
- Include the full display name and bounding box in your answer when available.
- Clearly state when a location cannot be found.
- GeoJSON coordinates are [longitude, latitude] (not lat, lon).
- Answer in the same language as the user's question.
"""


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
async def geocode_address(address: str) -> str:
    """Convert a place name or address to geographic coordinates using OpenStreetMap Nominatim.

    Returns a GeoJSON Feature with coordinates and metadata.
    """
    url = f"{_NOMINATIM_BASE}/search"
    params = {"q": address, "format": "json", "limit": 3, "addressdetails": 1}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params, headers=_HEADERS)
            resp.raise_for_status()
            results = resp.json()
        if not results:
            return json.dumps({"error": f"No results found for: {address}"})
        features = []
        for r in results:
            lat, lon = float(r["lat"]), float(r["lon"])
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "name": address,
                        "display_name": r.get("display_name", address),
                        "place_type": r.get("type", ""),
                        "place_rank": r.get("place_rank"),
                        "importance": r.get("importance"),
                        "osm_id": r.get("osm_id", ""),
                        "address": r.get("address", {}),
                        "boundingbox": r.get("boundingbox"),
                    },
                }
            )
        return json.dumps({"type": "FeatureCollection", "features": features})
    except Exception as exc:
        return json.dumps({"error": f"Geocoding failed for '{address}': {exc}"})


@tool
async def reverse_geocode(latitude: float, longitude: float) -> str:
    """Convert geographic coordinates to a human-readable address using OpenStreetMap Nominatim.

    Args:
        latitude: Latitude in decimal degrees (-90 to 90).
        longitude: Longitude in decimal degrees (-180 to 180).
    Returns a JSON object with address components.
    """
    if not (-90 <= latitude <= 90):
        return json.dumps({"error": f"Invalid latitude: {latitude}. Must be between -90 and 90."})
    if not (-180 <= longitude <= 180):
        return json.dumps({"error": f"Invalid longitude: {longitude}. Must be between -180 and 180."})

    url = f"{_NOMINATIM_BASE}/reverse"
    params = {"lat": latitude, "lon": longitude, "format": "json", "addressdetails": 1}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params, headers=_HEADERS)
            resp.raise_for_status()
            result = resp.json()
        if "error" in result:
            return json.dumps({"error": result["error"]})
        return json.dumps(
            {
                "display_name": result.get("display_name", ""),
                "address": result.get("address", {}),
                "osm_type": result.get("osm_type", ""),
                "osm_id": result.get("osm_id", ""),
                "coordinates": {"latitude": latitude, "longitude": longitude},
            }
        )
    except Exception as exc:
        return json.dumps({"error": f"Reverse geocoding failed for ({latitude}, {longitude}): {exc}"})


@tool
async def batch_geocode(addresses_json: str) -> str:
    """Geocode a list of addresses provided as a JSON array of strings.

    Args:
        addresses_json: JSON array of address strings, e.g. '["Paris, France", "Berlin, Germany"]'.
    Returns a JSON array of geocoding results, one per input address.
    """
    try:
        addresses = json.loads(addresses_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON input: {exc}"})

    if not isinstance(addresses, list):
        return json.dumps({"error": "Input must be a JSON array of address strings."})

    results = []
    for address in addresses:
        if not isinstance(address, str):
            results.append({"address": str(address), "error": "Address must be a string."})
            continue
        url = f"{_NOMINATIM_BASE}/search"
        params = {"q": address, "format": "json", "limit": 1}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params, headers=_HEADERS)
                resp.raise_for_status()
                hits = resp.json()
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
        except Exception as exc:
            results.append({"address": address, "error": str(exc)})

    return json.dumps(results)


GEO_ADDRESS_TOOLS = [geocode_address, reverse_geocode, batch_geocode]
_TOOL_MAP = {t.name: t for t in GEO_ADDRESS_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the Geo Address sub-agent."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"geo_address": f"[geo_address agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    llm = build_llm(
        get_agent_model_config("geo_address_agent"), streaming=True
    ).bind_tools(GEO_ADDRESS_TOOLS)

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]

    for _ in range(get_agent_max_iterations("geo_address_agent")):
        response: AIMessage = await llm.ainvoke(messages)
        messages.append(response)

        if not getattr(response, "tool_calls", None):
            break

        for tc in response.tool_calls:
            tool_fn = _TOOL_MAP.get(tc["name"])
            if tool_fn is None:
                result = (
                    f"Unknown tool: {tc['name']}. "
                    f"Available tools: {list(_TOOL_MAP.keys())}"
                )
            else:
                try:
                    result = await tool_fn.ainvoke(tc["args"])
                except Exception as exc:
                    result = f"Tool error: {exc}"
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    result_content = (
        messages[-1].content if messages else "geo_address agent returned no result."
    )
    return {"sub_results": {"geo_address": str(result_content)}}
