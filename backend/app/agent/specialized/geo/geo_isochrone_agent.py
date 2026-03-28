"""
Geo Isochrone Agent – accessibility zone computation.

Specialises in:
  • Generating approximate isochrone polygons (areas reachable within a given time/distance)
  • Computing travel-time zones using simplified circular approximations
  • Estimating multi-modal accessibility zones (walking, cycling, driving)
  • Producing GeoJSON FeatureCollections for isochrone visualisation

Note: This agent produces geometric approximations based on straight-line distances
and average travel speeds.  For precise road-network isochrones, integrate with
a routing engine (e.g. OSRM, Valhalla, or ORS) via an external API.

Exposed as a single async function `run` usable as a LangGraph node or called
directly by the geo_agent orchestrator.
"""
from __future__ import annotations

import json
import math
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agent.model_config import build_llm, get_agent_model_config, get_agent_max_iterations
from app.agent.state import AgentState

_EARTH_RADIUS_M = 6_371_000.0

# Average travel speeds in m/s (used for straight-line approximations)
_SPEEDS_MS: dict[str, float] = {
    "walking": 1.4,       # ~5 km/h
    "cycling": 4.2,       # ~15 km/h
    "driving": 13.9,      # ~50 km/h (urban)
    "driving_highway": 27.8,  # ~100 km/h (highway)
}

_SYSTEM_PROMPT = """You are the Isochrone Agent of the PangIA GeoIA platform.
Your role is to compute accessibility zones – areas reachable from a given point
within a specified time or distance threshold.

## Capabilities
- `generate_isochrone`: Create an approximate isochrone polygon for a given travel mode and time.
- `generate_multi_isochrone`: Create multiple nested isochrone rings (e.g. 5 min, 10 min, 15 min).
- `estimate_reachable_radius`: Compute the straight-line radius for a given travel time and mode.

## Important note
These isochrones are geometric approximations based on average travel speeds and
straight-line distances.  They do not account for road networks, terrain, or traffic.
For precise isochrones, a routing engine (OSRM, Valhalla, ORS) would be required.

## Guidelines
- Always state the travel mode and time/distance threshold clearly.
- Explain that results are approximations.
- Supported travel modes: walking, cycling, driving, driving_highway.
- Answer in the same language as the user's question.
"""


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _destination_point(lat: float, lon: float, bearing_deg: float, dist_m: float) -> tuple[float, float]:
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    bearing_r = math.radians(bearing_deg)
    angular = dist_m / _EARTH_RADIUS_M
    dest_lat = math.asin(
        math.sin(lat_r) * math.cos(angular)
        + math.cos(lat_r) * math.sin(angular) * math.cos(bearing_r)
    )
    dest_lon = lon_r + math.atan2(
        math.sin(bearing_r) * math.sin(angular) * math.cos(lat_r),
        math.cos(angular) - math.sin(lat_r) * math.sin(dest_lat),
    )
    return math.degrees(dest_lat), math.degrees(dest_lon)


def _isochrone_polygon(lat: float, lon: float, radius_m: float, n_vertices: int = 64) -> list[list[float]]:
    coords = []
    for i in range(n_vertices):
        bearing = 360.0 * i / n_vertices
        dlat, dlon = _destination_point(lat, lon, bearing, radius_m)
        coords.append([round(dlon, 7), round(dlat, 7)])
    coords.append(coords[0])
    return coords


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
def estimate_reachable_radius(
    travel_time_minutes: float,
    travel_mode: str = "walking",
) -> str:
    """Estimate the straight-line radius reachable from a point within a given travel time.

    Args:
        travel_time_minutes: Travel time threshold in minutes.
        travel_mode: One of 'walking', 'cycling', 'driving', 'driving_highway'.
    Returns a JSON object with the estimated radius and area.
    """
    mode = travel_mode.lower().strip()
    speed = _SPEEDS_MS.get(mode)
    if speed is None:
        return json.dumps(
            {
                "error": f"Unknown travel mode: {travel_mode}.",
                "supported_modes": list(_SPEEDS_MS.keys()),
            }
        )

    radius_m = speed * travel_time_minutes * 60
    area_km2 = math.pi * (radius_m / 1000) ** 2

    return json.dumps(
        {
            "travel_mode": mode,
            "travel_time_minutes": travel_time_minutes,
            "speed_ms": speed,
            "speed_kmh": round(speed * 3.6, 1),
            "radius_metres": round(radius_m, 1),
            "radius_km": round(radius_m / 1000, 3),
            "area_km2": round(area_km2, 4),
            "note": "Straight-line approximation – does not account for road network.",
        }
    )


@tool
def generate_isochrone(
    latitude: float,
    longitude: float,
    travel_time_minutes: float,
    travel_mode: str = "walking",
    label: str = "",
) -> str:
    """Generate an approximate isochrone polygon for a given point, travel time, and mode.

    Args:
        latitude: Centre latitude in decimal degrees.
        longitude: Centre longitude in decimal degrees.
        travel_time_minutes: Travel time threshold in minutes.
        travel_mode: One of 'walking', 'cycling', 'driving', 'driving_highway'.
        label: Optional label for the isochrone feature.
    Returns a GeoJSON Feature with a Polygon geometry.
    """
    mode = travel_mode.lower().strip()
    speed = _SPEEDS_MS.get(mode)
    if speed is None:
        return json.dumps(
            {
                "error": f"Unknown travel mode: {travel_mode}.",
                "supported_modes": list(_SPEEDS_MS.keys()),
            }
        )

    if not (-90 <= latitude <= 90):
        return json.dumps({"error": f"Invalid latitude: {latitude}."})
    if not (-180 <= longitude <= 180):
        return json.dumps({"error": f"Invalid longitude: {longitude}."})
    if travel_time_minutes <= 0:
        return json.dumps({"error": "travel_time_minutes must be positive."})

    radius_m = speed * travel_time_minutes * 60
    coords = _isochrone_polygon(latitude, longitude, radius_m)
    area_km2 = math.pi * (radius_m / 1000) ** 2

    feature: dict[str, Any] = {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [coords]},
        "properties": {
            "name": label or f"{travel_time_minutes}min {mode} isochrone",
            "center": {"latitude": latitude, "longitude": longitude},
            "travel_mode": mode,
            "travel_time_minutes": travel_time_minutes,
            "radius_metres": round(radius_m, 1),
            "area_km2": round(area_km2, 4),
            "approximation": "straight-line (no road network)",
        },
    }
    return json.dumps(feature)


@tool
def generate_multi_isochrone(
    latitude: float,
    longitude: float,
    travel_times_json: str,
    travel_mode: str = "walking",
    label: str = "",
) -> str:
    """Generate multiple nested isochrone polygons for different travel times.

    Args:
        latitude: Centre latitude in decimal degrees.
        longitude: Centre longitude in decimal degrees.
        travel_times_json: JSON array of travel time thresholds in minutes, e.g. '[5, 10, 15]'.
        travel_mode: One of 'walking', 'cycling', 'driving', 'driving_highway'.
        label: Optional base label for the isochrone features.
    Returns a GeoJSON FeatureCollection with one polygon per travel time.
    """
    mode = travel_mode.lower().strip()
    speed = _SPEEDS_MS.get(mode)
    if speed is None:
        return json.dumps(
            {
                "error": f"Unknown travel mode: {travel_mode}.",
                "supported_modes": list(_SPEEDS_MS.keys()),
            }
        )

    try:
        times: list[float] = [float(t) for t in json.loads(travel_times_json)]
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        return json.dumps({"error": f"Invalid travel_times JSON: {exc}"})

    if not times:
        return json.dumps({"error": "Provide at least one travel time value."})

    features = []
    for t in sorted(times):
        radius_m = speed * t * 60
        coords = _isochrone_polygon(latitude, longitude, radius_m)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [coords]},
                "properties": {
                    "name": f"{label} {t}min" if label else f"{t}min {mode}",
                    "travel_mode": mode,
                    "travel_time_minutes": t,
                    "radius_metres": round(radius_m, 1),
                    "area_km2": round(math.pi * (radius_m / 1000) ** 2, 4),
                },
            }
        )

    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": features,
            "properties": {
                "center": {"latitude": latitude, "longitude": longitude},
                "travel_mode": mode,
                "isochrone_count": len(features),
                "approximation": "straight-line (no road network)",
            },
        }
    )


GEO_ISOCHRONE_TOOLS = [estimate_reachable_radius, generate_isochrone, generate_multi_isochrone]
_TOOL_MAP = {t.name: t for t in GEO_ISOCHRONE_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the Geo Isochrone sub-agent."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"geo_isochrone": f"[geo_isochrone agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    llm = build_llm(
        get_agent_model_config("geo_isochrone_agent"), streaming=True
    ).bind_tools(GEO_ISOCHRONE_TOOLS)

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]

    for _ in range(get_agent_max_iterations("geo_isochrone_agent")):
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
        messages[-1].content if messages else "geo_isochrone agent returned no result."
    )
    return {"sub_results": {"geo_isochrone": str(result_content)}}
