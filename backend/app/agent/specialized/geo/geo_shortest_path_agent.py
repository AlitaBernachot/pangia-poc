"""
Geo Shortest Path Agent – route and itinerary computation.

Specialises in:
  • Computing the shortest path between waypoints using graph algorithms
  • Estimating travel time and distance along a sequence of waypoints
  • Optimising visit order for multiple stops (Travelling Salesman approximation)
  • Producing route summaries with cumulative distances

Note: This agent computes straight-line (geodesic) routes without road-network
data.  For precise road-based routing, integrate with OSRM, Valhalla, or ORS.

Exposed as a single async function `run` usable as a LangGraph node or called
directly by the geo_agent orchestrator.
"""
from __future__ import annotations

import json
import math
from itertools import permutations
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agent.model_config import build_llm, get_agent_model_config, get_agent_max_iterations
from app.agent.state import AgentState

_EARTH_RADIUS_M = 6_371_000.0

_SPEEDS_MS: dict[str, float] = {
    "walking": 1.4,
    "cycling": 4.2,
    "driving": 13.9,
}

_SYSTEM_PROMPT = """You are the Shortest Path Agent of the PangIA GeoIA platform.
Your role is to compute routes and itineraries between geographic waypoints.

## Capabilities
- `compute_route`: Compute the total straight-line distance along a sequence of waypoints.
- `optimise_tour`: Find the approximate shortest tour visiting all waypoints (greedy TSP).
- `estimate_travel_time`: Estimate travel time along a route for a given travel mode.

## Important note
These routes are based on straight-line (great-circle) distances only and do NOT
account for roads, terrain, or traffic.  For real road-network routing, an external
routing engine (OSRM, Valhalla, ORS) would be required.

## Guidelines
- List the waypoints in order with the cumulative distance at each step.
- Report total distance and estimated travel time.
- Clearly state that results are straight-line approximations.
- Answer in the same language as the user's question.
"""


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _route_distance(waypoints: list[dict[str, Any]]) -> float:
    total = 0.0
    for i in range(len(waypoints) - 1):
        total += _haversine(
            float(waypoints[i]["latitude"]), float(waypoints[i]["longitude"]),
            float(waypoints[i + 1]["latitude"]), float(waypoints[i + 1]["longitude"]),
        )
    return total


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
def compute_route(waypoints_json: str) -> str:
    """Compute the total straight-line distance along an ordered sequence of waypoints.

    Args:
        waypoints_json: JSON array of waypoints with 'name' (optional), 'latitude', 'longitude'.
            Example: '[{"name":"Paris","latitude":48.8566,"longitude":2.3522}, ...]'
    Returns a JSON object with the route segments and total distance.
    """
    try:
        waypoints: list[dict[str, Any]] = json.loads(waypoints_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if not isinstance(waypoints, list) or len(waypoints) < 2:
        return json.dumps({"error": "Provide at least 2 waypoints."})

    segments = []
    cumulative_m = 0.0

    for i in range(len(waypoints) - 1):
        try:
            lat1 = float(waypoints[i]["latitude"])
            lon1 = float(waypoints[i]["longitude"])
            lat2 = float(waypoints[i + 1]["latitude"])
            lon2 = float(waypoints[i + 1]["longitude"])
        except (KeyError, ValueError, TypeError) as exc:
            return json.dumps({"error": f"Invalid waypoint at index {i}: {exc}"})

        dist_m = _haversine(lat1, lon1, lat2, lon2)
        cumulative_m += dist_m
        segments.append(
            {
                "from": waypoints[i].get("name", f"waypoint_{i}"),
                "to": waypoints[i + 1].get("name", f"waypoint_{i + 1}"),
                "distance_km": round(dist_m / 1000, 4),
                "cumulative_km": round(cumulative_m / 1000, 4),
            }
        )

    return json.dumps(
        {
            "waypoint_count": len(waypoints),
            "segments": segments,
            "total_distance_km": round(cumulative_m / 1000, 4),
            "total_distance_m": round(cumulative_m, 1),
            "approximation": "straight-line (no road network)",
        }
    )


@tool
def optimise_tour(waypoints_json: str) -> str:
    """Find the approximate shortest tour visiting all waypoints (greedy nearest-neighbour TSP).

    This is an approximation – the optimal TSP solution is NP-hard.
    For small sets (≤10 waypoints), exact brute-force is used.

    Args:
        waypoints_json: JSON array of waypoints with 'name', 'latitude', 'longitude'.
    Returns the suggested visit order and total tour distance.
    """
    try:
        waypoints: list[dict[str, Any]] = json.loads(waypoints_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if not isinstance(waypoints, list) or len(waypoints) < 2:
        return json.dumps({"error": "Provide at least 2 waypoints."})
    if len(waypoints) > 12:
        return json.dumps({"error": "Maximum 12 waypoints supported for tour optimisation."})

    # Precompute distance matrix
    n = len(waypoints)
    try:
        dist = [
            [
                _haversine(
                    float(waypoints[i]["latitude"]), float(waypoints[i]["longitude"]),
                    float(waypoints[j]["latitude"]), float(waypoints[j]["longitude"]),
                )
                for j in range(n)
            ]
            for i in range(n)
        ]
    except (KeyError, ValueError, TypeError) as exc:
        return json.dumps({"error": f"Invalid waypoint coordinates: {exc}"})

    # Use exact brute-force for ≤8 waypoints, greedy NN otherwise
    if n <= 8:
        best_order = list(range(n))
        best_dist = sum(dist[best_order[i]][best_order[i + 1]] for i in range(n - 1))
        for perm in permutations(range(1, n)):
            order = [0] + list(perm)
            d = sum(dist[order[i]][order[i + 1]] for i in range(n - 1))
            if d < best_dist:
                best_dist = d
                best_order = order
    else:
        # Greedy nearest-neighbour starting from index 0
        unvisited = set(range(1, n))
        best_order = [0]
        current = 0
        while unvisited:
            nearest = min(unvisited, key=lambda j: dist[current][j])
            best_order.append(nearest)
            unvisited.remove(nearest)
            current = nearest
        best_dist = sum(dist[best_order[i]][best_order[i + 1]] for i in range(n - 1))

    ordered = [waypoints[i] for i in best_order]

    return json.dumps(
        {
            "optimised_order": [
                {"step": idx + 1, "name": wp.get("name", f"waypoint_{best_order[idx]}")}
                for idx, wp in enumerate(ordered)
            ],
            "total_distance_km": round(best_dist / 1000, 4),
            "method": "exact brute-force" if n <= 8 else "greedy nearest-neighbour",
            "approximation": "straight-line distances (no road network)",
        }
    )


@tool
def estimate_travel_time(
    total_distance_km: float,
    travel_mode: str = "driving",
) -> str:
    """Estimate travel time for a given route distance and travel mode.

    Args:
        total_distance_km: Route distance in kilometres.
        travel_mode: One of 'walking', 'cycling', 'driving'.
    Returns estimated travel time in hours and minutes.
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

    dist_m = total_distance_km * 1000
    time_s = dist_m / speed
    hours = int(time_s // 3600)
    minutes = int((time_s % 3600) // 60)
    seconds = int(time_s % 60)

    return json.dumps(
        {
            "distance_km": total_distance_km,
            "travel_mode": mode,
            "speed_kmh": round(speed * 3.6, 1),
            "estimated_time": {
                "hours": hours,
                "minutes": minutes,
                "seconds": seconds,
                "total_minutes": round(time_s / 60, 1),
                "formatted": f"{hours}h {minutes:02d}min" if hours else f"{minutes}min {seconds:02d}s",
            },
            "note": "Straight-line approximation – does not account for road network or stops.",
        }
    )


GEO_SHORTEST_PATH_TOOLS = [compute_route, optimise_tour, estimate_travel_time]
_TOOL_MAP = {t.name: t for t in GEO_SHORTEST_PATH_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the Geo Shortest Path sub-agent."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"geo_shortest_path": f"[geo_shortest_path agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    llm = build_llm(
        get_agent_model_config("geo_shortest_path_agent"), streaming=True
    ).bind_tools(GEO_SHORTEST_PATH_TOOLS)

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]

    for _ in range(get_agent_max_iterations("geo_shortest_path_agent")):
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
        messages[-1].content if messages else "geo_shortest_path agent returned no result."
    )
    return {"sub_results": {"geo_shortest_path": str(result_content)}}
