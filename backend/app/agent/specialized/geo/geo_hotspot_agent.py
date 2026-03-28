"""
Geo Hotspot Agent – spatial cluster detection.

Specialises in:
  • Detecting geographic hotspots and clusters of point data
  • Computing spatial density and identifying high-concentration areas
  • Generating cluster summary statistics (centroid, radius, count)
  • Applying simple grid-based or distance-based clustering heuristics

Note: This agent implements lightweight clustering heuristics (DBSCAN-inspired
distance grouping) without external ML libraries.  For advanced cluster analysis,
a PostGIS query with ST_ClusterDBSCAN is recommended.

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

_SYSTEM_PROMPT = """You are the Hotspot Detection Agent of the PangIA GeoIA platform.
Your role is to identify geographic clusters and density hotspots in point datasets.

## Capabilities
- `detect_clusters`: Group points into spatial clusters using a distance threshold.
- `compute_spatial_density`: Compute the density of points within a grid.
- `find_cluster_centroid`: Compute the geographic centroid of a cluster.

## Guidelines
- Clearly state the clustering parameters (distance threshold, minimum cluster size).
- Report the number of clusters found and their sizes.
- For each cluster, provide the centroid coordinates and approximate radius.
- Outliers (points not belonging to any cluster) should be reported separately.
- Answer in the same language as the user's question.
"""


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _centroid(points: list[dict[str, Any]]) -> tuple[float, float]:
    """Compute the arithmetic mean centroid of a list of points."""
    lats = [float(p["latitude"]) for p in points]
    lons = [float(p["longitude"]) for p in points]
    return sum(lats) / len(lats), sum(lons) / len(lons)


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
def detect_clusters(
    points_json: str,
    eps_metres: float = 1000.0,
    min_cluster_size: int = 2,
) -> str:
    """Group geographic points into spatial clusters using a distance-based approach.

    Implements a simple single-linkage clustering: two points belong to the same
    cluster if they are within eps_metres of each other.

    Args:
        points_json: JSON array of points with 'name' (optional), 'latitude', 'longitude'.
        eps_metres: Maximum distance in metres between points in the same cluster (default 1000).
        min_cluster_size: Minimum number of points for a group to be a cluster (default 2).
    Returns a JSON object with clusters and outliers.
    """
    try:
        points: list[dict[str, Any]] = json.loads(points_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if not isinstance(points, list) or not points:
        return json.dumps({"error": "Provide a non-empty JSON array of points."})

    n = len(points)
    labels = [-1] * n  # -1 = unassigned
    cluster_id = 0

    for i in range(n):
        if labels[i] != -1:
            continue
        # Start a new cluster
        cluster = [i]
        queue = [i]
        labels[i] = cluster_id

        while queue:
            current = queue.pop()
            try:
                lat1 = float(points[current]["latitude"])
                lon1 = float(points[current]["longitude"])
            except (KeyError, ValueError, TypeError):
                continue
            for j in range(n):
                if labels[j] != -1:
                    continue
                try:
                    lat2 = float(points[j]["latitude"])
                    lon2 = float(points[j]["longitude"])
                except (KeyError, ValueError, TypeError):
                    continue
                if _haversine(lat1, lon1, lat2, lon2) <= eps_metres:
                    labels[j] = cluster_id
                    cluster.append(j)
                    queue.append(j)

        cluster_id += 1

    # Build cluster summaries
    cluster_map: dict[int, list[dict[str, Any]]] = {}
    for idx, label in enumerate(labels):
        cluster_map.setdefault(label, []).append(points[idx])

    clusters = []
    outliers = []

    for cid, members in cluster_map.items():
        if len(members) < min_cluster_size:
            outliers.extend(members)
            continue
        clat, clon = _centroid(members)
        max_radius = max(
            _haversine(clat, clon, float(m["latitude"]), float(m["longitude"]))
            for m in members
        )
        clusters.append(
            {
                "cluster_id": cid,
                "size": len(members),
                "centroid": {"latitude": round(clat, 6), "longitude": round(clon, 6)},
                "radius_metres": round(max_radius, 1),
                "members": [m.get("name", f"pt_{i}") for i, m in enumerate(members)],
            }
        )

    clusters.sort(key=lambda x: -x["size"])
    for idx, c in enumerate(clusters):
        c["rank"] = idx + 1

    return json.dumps(
        {
            "parameters": {"eps_metres": eps_metres, "min_cluster_size": min_cluster_size},
            "total_points": n,
            "cluster_count": len(clusters),
            "clusters": clusters,
            "outlier_count": len(outliers),
            "outliers": [p.get("name", str(p)) for p in outliers],
        }
    )


@tool
def compute_spatial_density(
    points_json: str,
    grid_size_degrees: float = 1.0,
) -> str:
    """Compute point density on a regular lat/lon grid.

    Args:
        points_json: JSON array of points with 'latitude' and 'longitude'.
        grid_size_degrees: Size of each grid cell in decimal degrees (default 1.0°).
    Returns a JSON object with grid cells sorted by density (highest first).
    """
    try:
        points: list[dict[str, Any]] = json.loads(points_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if not isinstance(points, list) or not points:
        return json.dumps({"error": "Provide a non-empty JSON array of points."})

    grid: dict[tuple[int, int], list[str]] = {}
    for i, pt in enumerate(points):
        try:
            lat = float(pt["latitude"])
            lon = float(pt["longitude"])
        except (KeyError, ValueError, TypeError):
            continue
        cell = (
            int(math.floor(lat / grid_size_degrees)),
            int(math.floor(lon / grid_size_degrees)),
        )
        grid.setdefault(cell, []).append(pt.get("name", f"pt_{i}"))

    cells = [
        {
            "cell_lat_min": round(r * grid_size_degrees, 4),
            "cell_lat_max": round((r + 1) * grid_size_degrees, 4),
            "cell_lon_min": round(c * grid_size_degrees, 4),
            "cell_lon_max": round((c + 1) * grid_size_degrees, 4),
            "count": len(names),
            "points": names,
        }
        for (r, c), names in grid.items()
    ]
    cells.sort(key=lambda x: -x["count"])

    return json.dumps(
        {
            "grid_size_degrees": grid_size_degrees,
            "total_points": len(points),
            "cell_count": len(cells),
            "cells": cells,
        }
    )


@tool
def find_cluster_centroid(points_json: str) -> str:
    """Compute the geographic centroid of a set of points.

    Args:
        points_json: JSON array of points with 'latitude' and 'longitude'.
    Returns the arithmetic mean centroid coordinates.
    """
    try:
        points: list[dict[str, Any]] = json.loads(points_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if not isinstance(points, list) or not points:
        return json.dumps({"error": "Provide a non-empty JSON array of points."})

    valid = []
    for i, pt in enumerate(points):
        try:
            lat = float(pt["latitude"])
            lon = float(pt["longitude"])
            valid.append({"latitude": lat, "longitude": lon})
        except (KeyError, ValueError, TypeError):
            continue

    if not valid:
        return json.dumps({"error": "No valid (latitude, longitude) pairs found."})

    clat, clon = _centroid(valid)
    max_r = max(_haversine(clat, clon, p["latitude"], p["longitude"]) for p in valid)

    return json.dumps(
        {
            "centroid": {"latitude": round(clat, 6), "longitude": round(clon, 6)},
            "point_count": len(valid),
            "max_radius_metres": round(max_r, 1),
            "max_radius_km": round(max_r / 1000, 4),
        }
    )


GEO_HOTSPOT_TOOLS = [detect_clusters, compute_spatial_density, find_cluster_centroid]
_TOOL_MAP = {t.name: t for t in GEO_HOTSPOT_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the Geo Hotspot sub-agent."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"geo_hotspot": f"[geo_hotspot agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    llm = build_llm(
        get_agent_model_config("geo_hotspot_agent"), streaming=True
    ).bind_tools(GEO_HOTSPOT_TOOLS)

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]

    for _ in range(get_agent_max_iterations("geo_hotspot_agent")):
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
        messages[-1].content if messages else "geo_hotspot agent returned no result."
    )
    return {"sub_results": {"geo_hotspot": str(result_content)}}
