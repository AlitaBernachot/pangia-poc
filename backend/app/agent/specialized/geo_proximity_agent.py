"""
Geo Proximity Agent – nearest-entity analysis.

Specialises in:
  • Finding the N nearest geographic features to a reference point
  • Ranking entities by distance from a location
  • Computing proximity scores and summaries
  • Supporting multiple distance thresholds and entity types

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

_SYSTEM_PROMPT = """You are the Proximity Analysis Agent of the PangIA GeoIA platform.
Your role is to find and rank geographic features by their distance from a reference point.

## Capabilities
- `find_nearest`: Find the N nearest features to a reference point from a list.
- `filter_within_radius`: Keep only features within a given radius from a reference point.
- `rank_by_proximity`: Rank a list of features from nearest to farthest.

## Guidelines
- Always report the distance to each found feature.
- Specify whether the result is within or outside a threshold if given.
- GeoJSON coordinates are [longitude, latitude].
- Answer in the same language as the user's question.
"""


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
def find_nearest(
    ref_lat: float,
    ref_lon: float,
    features_json: str,
    n: int = 5,
) -> str:
    """Find the N nearest features to a reference point.

    Args:
        ref_lat: Reference latitude in decimal degrees.
        ref_lon: Reference longitude in decimal degrees.
        features_json: JSON array of features, each with 'name', 'latitude', 'longitude'.
        n: Number of nearest features to return (default 5).
    Returns a JSON array of the nearest features with their distances.
    """
    try:
        features: list[dict[str, Any]] = json.loads(features_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if not isinstance(features, list) or not features:
        return json.dumps({"error": "Provide at least one feature."})

    ranked = []
    for i, ft in enumerate(features):
        try:
            lat, lon = float(ft["latitude"]), float(ft["longitude"])
        except (KeyError, ValueError, TypeError) as exc:
            return json.dumps({"error": f"Feature at index {i} has invalid coordinates: {exc}"})
        dist_m = _haversine(ref_lat, ref_lon, lat, lon)
        ranked.append({**ft, "_distance_m": dist_m, "_distance_km": round(dist_m / 1000, 4)})

    ranked.sort(key=lambda x: x["_distance_m"])
    top_n = ranked[:max(1, n)]

    return json.dumps(
        {
            "reference": {"latitude": ref_lat, "longitude": ref_lon},
            "nearest": [
                {
                    "rank": idx + 1,
                    "name": ft.get("name", f"feature_{idx}"),
                    "latitude": ft.get("latitude"),
                    "longitude": ft.get("longitude"),
                    "distance_km": ft["_distance_km"],
                    "distance_m": round(ft["_distance_m"], 1),
                }
                for idx, ft in enumerate(top_n)
            ],
            "total_features_searched": len(features),
        }
    )


@tool
def filter_within_radius(
    ref_lat: float,
    ref_lon: float,
    features_json: str,
    radius_metres: float,
) -> str:
    """Keep only features within a given radius from a reference point.

    Args:
        ref_lat: Reference latitude in decimal degrees.
        ref_lon: Reference longitude in decimal degrees.
        features_json: JSON array of features with 'name', 'latitude', 'longitude'.
        radius_metres: Maximum distance in metres.
    Returns a JSON object with matching and excluded features.
    """
    try:
        features: list[dict[str, Any]] = json.loads(features_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    inside = []
    outside = []
    for i, ft in enumerate(features):
        try:
            lat, lon = float(ft["latitude"]), float(ft["longitude"])
        except (KeyError, ValueError, TypeError) as exc:
            return json.dumps({"error": f"Feature at index {i} has invalid coordinates: {exc}"})
        dist_m = _haversine(ref_lat, ref_lon, lat, lon)
        entry = {
            "name": ft.get("name", f"feature_{i}"),
            "latitude": ft.get("latitude"),
            "longitude": ft.get("longitude"),
            "distance_m": round(dist_m, 1),
            "distance_km": round(dist_m / 1000, 4),
        }
        if dist_m <= radius_metres:
            inside.append(entry)
        else:
            outside.append(entry)

    inside.sort(key=lambda x: x["distance_m"])

    return json.dumps(
        {
            "reference": {"latitude": ref_lat, "longitude": ref_lon},
            "radius_metres": radius_metres,
            "within_radius": inside,
            "outside_radius_count": len(outside),
            "total_features": len(features),
        }
    )


@tool
def rank_by_proximity(
    ref_lat: float,
    ref_lon: float,
    features_json: str,
) -> str:
    """Rank all features from nearest to farthest relative to a reference point.

    Args:
        ref_lat: Reference latitude in decimal degrees.
        ref_lon: Reference longitude in decimal degrees.
        features_json: JSON array of features with 'name', 'latitude', 'longitude'.
    Returns the full ranked list with distances.
    """
    try:
        features: list[dict[str, Any]] = json.loads(features_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    ranked = []
    for i, ft in enumerate(features):
        try:
            lat, lon = float(ft["latitude"]), float(ft["longitude"])
        except (KeyError, ValueError, TypeError) as exc:
            return json.dumps({"error": f"Feature at index {i} has invalid coordinates: {exc}"})
        dist_m = _haversine(ref_lat, ref_lon, lat, lon)
        ranked.append(
            {
                "name": ft.get("name", f"feature_{i}"),
                "latitude": ft.get("latitude"),
                "longitude": ft.get("longitude"),
                "distance_m": round(dist_m, 1),
                "distance_km": round(dist_m / 1000, 4),
            }
        )

    ranked.sort(key=lambda x: x["distance_m"])
    for idx, item in enumerate(ranked):
        item["rank"] = idx + 1

    return json.dumps(
        {
            "reference": {"latitude": ref_lat, "longitude": ref_lon},
            "ranked": ranked,
            "count": len(ranked),
        }
    )


GEO_PROXIMITY_TOOLS = [find_nearest, filter_within_radius, rank_by_proximity]
_TOOL_MAP = {t.name: t for t in GEO_PROXIMITY_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the Geo Proximity sub-agent."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"geo_proximity": f"[geo_proximity agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    llm = build_llm(
        get_agent_model_config("geo_proximity_agent"), streaming=True
    ).bind_tools(GEO_PROXIMITY_TOOLS)

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]

    for _ in range(get_agent_max_iterations("geo_proximity_agent")):
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
        messages[-1].content if messages else "geo_proximity agent returned no result."
    )
    return {"sub_results": {"geo_proximity": str(result_content)}}
