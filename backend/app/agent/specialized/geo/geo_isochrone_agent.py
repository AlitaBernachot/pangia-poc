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
from app.agent.specialized.geo.geo_address_agent import geocode_address
from app.agent.state import AgentState
from libs.geo.isochrone import SPEEDS_MS, isochrone_polygon

_SYSTEM_PROMPT = """You are the Isochrone Agent of the PangIA GeoIA platform.
Your role is to compute accessibility zones – areas reachable from a given point
within a specified time or distance threshold.

## Workflow
1. **Geocode the origin first**: Call `geocode_address` with a precise query.
   - Always include the exact city name and country in the query.
   - For transport infrastructure use the local-language name:
     `"gare SNCF Roanne, Loire, France"` not `"train station of Roanne"`.
   - Always pass `countrycodes="fr"` (or the relevant ISO code) to prevent
     false matches in other countries or nearby communes.
   - Use the **first feature** returned (highest Nominatim relevance score).
2. **Generate the isochrone**: Use `generate_isochrone` (single threshold) or
   `generate_multi_isochrone` (multiple thresholds) with the coordinates from step 1.
3. Optionally call `estimate_reachable_radius` to report the theoretical radius.

## Capabilities
- `geocode_address`: Convert a place name to precise coordinates (required first step).
- `generate_isochrone`: Approximate isochrone polygon for a single travel time and mode.
- `generate_multi_isochrone`: Multiple nested isochrone rings (e.g. 5 min, 10 min, 15 min).
- `estimate_reachable_radius`: Compute the straight-line radius for a given travel time and mode.

## Important note
Isochrones are geometric approximations based on average travel speeds and
straight-line distances.  They do not account for road networks, terrain, or traffic.

## Guidelines
- **Always geocode first** – accurate coordinates are essential for correct map placement.
- Supported travel modes: walking, cycling, driving, driving_highway.
- Answer in the same language as the user's question.
- **Never** include map embed code, Mapbox snippets, Leaflet HTML, access tokens, or
  rendering instructions in your answer – maps are rendered by the frontend.
"""



# ─── Tools ────────────────────────────────────────────────────────────────────

# geocode_address is imported from geo_address_agent – no duplication.


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
    speed = SPEEDS_MS.get(mode)
    if speed is None:
        return json.dumps(
            {
                "error": f"Unknown travel mode: {travel_mode}.",
                "supported_modes": list(SPEEDS_MS.keys()),
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
    speed = SPEEDS_MS.get(mode)
    if speed is None:
        return json.dumps(
            {
                "error": f"Unknown travel mode: {travel_mode}.",
                "supported_modes": list(SPEEDS_MS.keys()),
            }
        )

    if not (-90 <= latitude <= 90):
        return json.dumps({"error": f"Invalid latitude: {latitude}."})
    if not (-180 <= longitude <= 180):
        return json.dumps({"error": f"Invalid longitude: {longitude}."})
    if travel_time_minutes <= 0:
        return json.dumps({"error": "travel_time_minutes must be positive."})

    radius_m = speed * travel_time_minutes * 60
    coords = isochrone_polygon(latitude, longitude, radius_m)
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
    speed = SPEEDS_MS.get(mode)
    if speed is None:
        return json.dumps(
            {
                "error": f"Unknown travel mode: {travel_mode}.",
                "supported_modes": list(SPEEDS_MS.keys()),
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
        coords = isochrone_polygon(latitude, longitude, radius_m)
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


GEO_ISOCHRONE_TOOLS = [geocode_address, estimate_reachable_radius, generate_isochrone, generate_multi_isochrone]
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

    collected_features: list[dict] = []

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

            # Collect GeoJSON features to forward directly to the map agent.
            if tc["name"] == "geocode_address":
                # Origin point(s) – shown as marker(s) on the map
                try:
                    gj = json.loads(str(result))
                    if isinstance(gj, dict):
                        if gj.get("type") == "Feature":
                            collected_features.append(gj)
                        elif gj.get("type") == "FeatureCollection":
                            # Take only the best match (first result)
                            feats = gj.get("features", [])
                            if feats:
                                collected_features.append(feats[0])
                except (json.JSONDecodeError, AttributeError):
                    pass
            elif tc["name"] in ("generate_isochrone", "generate_multi_isochrone"):
                # Isochrone polygon(s) – polygon features placed before point markers
                try:
                    gj = json.loads(str(result))
                    if isinstance(gj, dict):
                        if gj.get("type") == "Feature":
                            collected_features.insert(0, gj)
                        elif gj.get("type") == "FeatureCollection":
                            for feat in gj.get("features", []):
                                collected_features.insert(0, feat)
                except (json.JSONDecodeError, AttributeError):
                    pass

            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    result_text = (
        messages[-1].content if messages else "geo_isochrone agent returned no result."
    )

    # Return a structured payload so upstream agents and the map agent can
    # pass the GeoJSON polygon through without losing it in text summaries.
    if collected_features:
        payload: dict = {
            "text": str(result_text),
            "geojson": {"type": "FeatureCollection", "features": collected_features},
        }
        return {"sub_results": {"geo_isochrone": json.dumps(payload)}}

    return {"sub_results": {"geo_isochrone": str(result_text)}}
