"""
Geo Elevation Agent – altitude and terrain data.

Specialises in:
  • Retrieving elevation data for geographic coordinates
  • Computing elevation profiles along routes
  • Analysing terrain characteristics (slope, rise/fall)
  • Estimating elevation statistics for point sets

The primary elevation source is the Open-Elevation API (open-elevation.com).
A fallback using the Open-Meteo elevation API is also available.

Exposed as a single async function `run` usable as a LangGraph node or called
directly by the geo_agent orchestrator.
"""
from __future__ import annotations

import json
import math
from typing import Any

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agent.model_config import build_llm, get_agent_model_config, get_agent_max_iterations
from app.agent.state import AgentState

_EARTH_RADIUS_M = 6_371_000.0

_SYSTEM_PROMPT = """You are the Elevation Agent of the PangIA GeoIA platform.
Your role is to retrieve and analyse terrain elevation data for geographic locations.

## Capabilities
- `get_elevation`: Fetch elevation for one or more geographic coordinates.
- `compute_elevation_profile`: Get elevation values along a series of waypoints.
- `analyse_elevation_stats`: Compute min, max, mean, and total ascent/descent statistics.

## Guidelines
- Elevation is expressed in metres above sea level (m ASL).
- Always cite the data source for elevation values.
- Clearly state when elevation data is unavailable for a location.
- Answer in the same language as the user's question.
"""


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


async def _fetch_open_meteo_elevation(locations: list[dict[str, float]]) -> list[float | None]:
    """Fetch elevation from the Open-Meteo elevation API (free, no key required)."""
    lats = ",".join(str(loc["latitude"]) for loc in locations)
    lons = ",".join(str(loc["longitude"]) for loc in locations)
    url = "https://api.open-meteo.com/v1/elevation"
    params = {"latitude": lats, "longitude": lons}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        elevations = data.get("elevation", [])
        return [float(e) if e is not None else None for e in elevations]
    except Exception:
        return [None] * len(locations)


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
async def get_elevation(locations_json: str) -> str:
    """Fetch elevation (metres above sea level) for one or more geographic coordinates.

    Args:
        locations_json: JSON array of objects with 'latitude' and 'longitude', or a single
            object. Example: '[{"latitude": 45.8326, "longitude": 6.8652, "name": "Mont Blanc"}]'
    Returns a JSON array with elevation data for each location.
    """
    try:
        data = json.loads(locations_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        return json.dumps({"error": "Provide a JSON array of location objects."})

    locations: list[dict[str, Any]] = []
    for i, item in enumerate(data):
        try:
            locations.append(
                {
                    "latitude": float(item["latitude"]),
                    "longitude": float(item["longitude"]),
                    "name": item.get("name", f"location_{i}"),
                }
            )
        except (KeyError, ValueError, TypeError) as exc:
            return json.dumps({"error": f"Invalid location at index {i}: {exc}"})

    elevations = await _fetch_open_meteo_elevation(locations)

    results = []
    for loc, elev in zip(locations, elevations):
        results.append(
            {
                "name": loc["name"],
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "elevation_metres": elev,
                "source": "Open-Meteo" if elev is not None else None,
                "available": elev is not None,
            }
        )

    return json.dumps({"locations": results, "count": len(results)})


@tool
async def compute_elevation_profile(waypoints_json: str) -> str:
    """Compute an elevation profile along a sequence of waypoints.

    Args:
        waypoints_json: JSON array of waypoints with 'name' (optional), 'latitude', 'longitude'.
    Returns elevation at each waypoint plus segment and cumulative distances.
    """
    try:
        waypoints: list[dict[str, Any]] = json.loads(waypoints_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if not isinstance(waypoints, list) or len(waypoints) < 2:
        return json.dumps({"error": "Provide at least 2 waypoints."})

    locations = []
    for i, wp in enumerate(waypoints):
        try:
            locations.append(
                {
                    "latitude": float(wp["latitude"]),
                    "longitude": float(wp["longitude"]),
                    "name": wp.get("name", f"waypoint_{i}"),
                }
            )
        except (KeyError, ValueError, TypeError) as exc:
            return json.dumps({"error": f"Invalid waypoint at index {i}: {exc}"})

    elevations = await _fetch_open_meteo_elevation(locations)

    profile = []
    cumulative_m = 0.0
    for i, (loc, elev) in enumerate(zip(locations, elevations)):
        seg_km = 0.0
        if i > 0:
            prev = locations[i - 1]
            seg_m = _haversine(
                prev["latitude"], prev["longitude"],
                loc["latitude"], loc["longitude"],
            )
            cumulative_m += seg_m
            seg_km = round(seg_m / 1000, 4)
        profile.append(
            {
                "step": i + 1,
                "name": loc["name"],
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "elevation_m": elev,
                "segment_km": seg_km,
                "cumulative_km": round(cumulative_m / 1000, 4),
            }
        )

    return json.dumps(
        {
            "profile": profile,
            "total_distance_km": round(cumulative_m / 1000, 4),
            "source": "Open-Meteo",
        }
    )


@tool
def analyse_elevation_stats(elevations_json: str) -> str:
    """Compute elevation statistics (min, max, mean, ascent, descent) from a list of values.

    Args:
        elevations_json: JSON array of elevation values in metres (floats), or an array of
            objects with 'elevation_metres' field.
    Returns summary statistics including total ascent and descent.
    """
    try:
        data = json.loads(elevations_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if not isinstance(data, list) or not data:
        return json.dumps({"error": "Provide a non-empty JSON array of elevation values."})

    values: list[float] = []
    for item in data:
        if isinstance(item, (int, float)):
            values.append(float(item))
        elif isinstance(item, dict) and "elevation_metres" in item:
            v = item["elevation_metres"]
            if v is not None:
                values.append(float(v))

    if not values:
        return json.dumps({"error": "No valid elevation values found."})

    total_ascent = sum(
        max(0, values[i + 1] - values[i]) for i in range(len(values) - 1)
    )
    total_descent = sum(
        max(0, values[i] - values[i + 1]) for i in range(len(values) - 1)
    )

    return json.dumps(
        {
            "count": len(values),
            "min_m": round(min(values), 1),
            "max_m": round(max(values), 1),
            "mean_m": round(sum(values) / len(values), 1),
            "range_m": round(max(values) - min(values), 1),
            "total_ascent_m": round(total_ascent, 1),
            "total_descent_m": round(total_descent, 1),
        }
    )


GEO_ELEVATION_TOOLS = [get_elevation, compute_elevation_profile, analyse_elevation_stats]
_TOOL_MAP = {t.name: t for t in GEO_ELEVATION_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the Geo Elevation sub-agent."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"geo_elevation": f"[geo_elevation agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    llm = build_llm(
        get_agent_model_config("geo_elevation_agent"), streaming=True
    ).bind_tools(GEO_ELEVATION_TOOLS)

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]

    for _ in range(get_agent_max_iterations("geo_elevation_agent")):
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
        messages[-1].content if messages else "geo_elevation agent returned no result."
    )
    return {"sub_results": {"geo_elevation": str(result_content)}}
