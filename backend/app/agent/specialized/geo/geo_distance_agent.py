"""
Geo Distance Agent – geographic distance calculations.

Specialises in:
  • Computing great-circle (Haversine) distances between two geographic points
  • Computing distance matrices between multiple points
  • Converting between distance units (metres, kilometres, miles, nautical miles)
  • Finding the closest point from a set to a reference location

Exposed as a single async function `run` usable as a LangGraph node or called
directly by the geo_agent orchestrator.
"""
from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agent.model_config import build_llm, get_agent_model_config, get_agent_max_iterations
from app.agent.state import AgentState
from libs.geo.geodesy import format_distance, haversine


_SYSTEM_PROMPT = """You are the Distance Calculation Agent of the PangIA GeoIA platform.
Your role is to compute geographic distances between locations.

## Capabilities
- `haversine_distance`: Calculate the great-circle distance between two points.
- `distance_matrix`: Compute pairwise distances between multiple points.
- `find_closest_point`: Find the nearest point to a reference location from a set.
- `convert_distance`: Convert a distance value between units.

## Guidelines
- Use the Haversine formula for great-circle distances (appropriate for most use cases).
- Always state the unit of the result clearly.
- For large datasets, summarise with min/max/mean distances.
- Answer in the same language as the user's question.
- **Never** include map embed code, Mapbox snippets, Leaflet HTML, access tokens, or
  rendering instructions in your answer – maps are rendered by the frontend.
"""


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
def haversine_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> str:
    """Calculate the great-circle (Haversine) distance between two geographic points.

    Args:
        lat1: Latitude of point A in decimal degrees.
        lon1: Longitude of point A in decimal degrees.
        lat2: Latitude of point B in decimal degrees.
        lon2: Longitude of point B in decimal degrees.
    Returns a JSON object with the distance in multiple units.
    """
    for name, val, lo, hi in [
        ("lat1", lat1, -90, 90), ("lon1", lon1, -180, 180),
        ("lat2", lat2, -90, 90), ("lon2", lon2, -180, 180),
    ]:
        if not (lo <= val <= hi):
            return json.dumps({"error": f"Invalid {name}: {val}. Must be between {lo} and {hi}."})

    dist_m = haversine(lat1, lon1, lat2, lon2)
    return json.dumps(
        {
            "point_a": {"latitude": lat1, "longitude": lon1},
            "point_b": {"latitude": lat2, "longitude": lon2},
            "distance": format_distance(dist_m),
        }
    )


@tool
def distance_matrix(points_json: str) -> str:
    """Compute pairwise Haversine distances between a list of geographic points.

    Args:
        points_json: JSON array of objects with 'name', 'latitude', and 'longitude' fields.
            Example: '[{"name":"Paris","latitude":48.8566,"longitude":2.3522}]'
    Returns a JSON object with the full distance matrix and summary statistics.
    """
    try:
        points: list[dict[str, Any]] = json.loads(points_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if not isinstance(points, list) or len(points) < 2:
        return json.dumps({"error": "Provide at least 2 points as a JSON array."})

    matrix: list[dict[str, Any]] = []
    all_distances: list[float] = []

    for i, p1 in enumerate(points):
        for j, p2 in enumerate(points):
            if i >= j:
                continue
            try:
                lat1, lon1 = float(p1["latitude"]), float(p1["longitude"])
                lat2, lon2 = float(p2["latitude"]), float(p2["longitude"])
            except (KeyError, ValueError, TypeError) as exc:
                return json.dumps({"error": f"Invalid point format: {exc}. Each point needs 'latitude' and 'longitude'."})

            dist_m = haversine(lat1, lon1, lat2, lon2)
            all_distances.append(dist_m)
            matrix.append(
                {
                    "from": p1.get("name", f"point_{i}"),
                    "to": p2.get("name", f"point_{j}"),
                    "distance": format_distance(dist_m),
                }
            )

    summary = {
        "min_km": round(min(all_distances) / 1000, 4) if all_distances else 0,
        "max_km": round(max(all_distances) / 1000, 4) if all_distances else 0,
        "mean_km": round(sum(all_distances) / len(all_distances) / 1000, 4) if all_distances else 0,
    }

    return json.dumps({"matrix": matrix, "summary": summary, "pair_count": len(matrix)})


@tool
def find_closest_point(
    ref_lat: float,
    ref_lon: float,
    candidates_json: str,
) -> str:
    """Find the nearest point to a reference location from a list of candidate points.

    Args:
        ref_lat: Latitude of the reference point.
        ref_lon: Longitude of the reference point.
        candidates_json: JSON array of candidate points with 'name', 'latitude', 'longitude'.
    Returns the closest point and its distance from the reference.
    """
    try:
        candidates: list[dict[str, Any]] = json.loads(candidates_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if not isinstance(candidates, list) or not candidates:
        return json.dumps({"error": "Provide at least one candidate point."})

    best = None
    best_dist = float("inf")

    for i, pt in enumerate(candidates):
        try:
            lat, lon = float(pt["latitude"]), float(pt["longitude"])
        except (KeyError, ValueError, TypeError) as exc:
            return json.dumps({"error": f"Invalid candidate at index {i}: {exc}."})
        dist_m = haversine(ref_lat, ref_lon, lat, lon)
        if dist_m < best_dist:
            best_dist = dist_m
            best = pt

    return json.dumps(
        {
            "reference": {"latitude": ref_lat, "longitude": ref_lon},
            "closest_point": best,
            "distance": format_distance(best_dist),
        }
    )


@tool
def convert_distance(value: float, from_unit: str, to_unit: str) -> str:
    """Convert a distance value between supported units.

    Supported units: 'metres', 'kilometres', 'miles', 'nautical_miles', 'feet'.
    Args:
        value: Numeric distance value to convert.
        from_unit: Source unit string.
        to_unit: Target unit string.
    Returns the converted value as a JSON object.
    """
    to_metres: dict[str, float] = {
        "metres": 1.0,
        "kilometers": 1000.0,
        "kilometres": 1000.0,
        "km": 1000.0,
        "miles": 1609.344,
        "mile": 1609.344,
        "nautical_miles": 1852.0,
        "feet": 0.3048,
        "foot": 0.3048,
        "ft": 0.3048,
    }
    from_key = from_unit.lower().strip()
    to_key = to_unit.lower().strip()

    if from_key not in to_metres:
        return json.dumps({"error": f"Unknown unit: {from_unit}. Supported: {list(to_metres.keys())}"})
    if to_key not in to_metres:
        return json.dumps({"error": f"Unknown unit: {to_unit}. Supported: {list(to_metres.keys())}"})

    metres = value * to_metres[from_key]
    converted = metres / to_metres[to_key]

    return json.dumps(
        {
            "input": {"value": value, "unit": from_unit},
            "output": {"value": round(converted, 6), "unit": to_unit},
            "intermediate_metres": round(metres, 4),
        }
    )


GEO_DISTANCE_TOOLS = [haversine_distance, distance_matrix, find_closest_point, convert_distance]
_TOOL_MAP = {t.name: t for t in GEO_DISTANCE_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the Geo Distance sub-agent."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"geo_distance": f"[geo_distance agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    llm = build_llm(
        get_agent_model_config("geo_distance_agent"), streaming=True
    ).bind_tools(GEO_DISTANCE_TOOLS)

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]

    for _ in range(get_agent_max_iterations("geo_distance_agent")):
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
        messages[-1].content if messages else "geo_distance agent returned no result."
    )
    return {"sub_results": {"geo_distance": str(result_content)}}
