"""
Geo Geometry Ops Agent – geometric operations and transformations.

Specialises in:
  • Simplifying GeoJSON geometries (Douglas-Peucker-inspired reduction)
  • Computing geometric properties (centroid, bounding box, convex hull approximation)
  • Transforming coordinate systems (WGS-84 ↔ common projected CRS)
  • Merging and splitting GeoJSON feature collections
  • Validating GeoJSON structure and coordinate ranges

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

_SYSTEM_PROMPT = """You are the Geometry Operations Agent of the PangIA GeoIA platform.
Your role is to perform geometric transformations and analyses on GeoJSON features.

## Capabilities
- `compute_bbox`: Compute the bounding box of a GeoJSON object.
- `compute_centroid`: Compute the geometric centroid of a GeoJSON feature.
- `simplify_linestring`: Reduce the number of vertices in a LineString (Ramer-Douglas-Peucker).
- `validate_geojson`: Validate a GeoJSON object and report any issues.
- `merge_feature_collections`: Merge multiple GeoJSON FeatureCollections into one.

## Guidelines
- Always validate GeoJSON input before processing.
- Bounding boxes are expressed as [min_lon, min_lat, max_lon, max_lat].
- GeoJSON coordinates are [longitude, latitude] (not lat, lon).
- Answer in the same language as the user's question.
"""


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _collect_coords(geometry: dict[str, Any]) -> list[list[float]]:
    """Recursively collect all [lon, lat] coordinate pairs from a geometry."""
    gtype = geometry.get("type", "")
    raw = geometry.get("coordinates", [])
    if gtype == "Point":
        return [raw] if raw else []
    if gtype in ("MultiPoint", "LineString"):
        return list(raw)
    if gtype in ("MultiLineString", "Polygon"):
        return [c for ring in raw for c in ring]
    if gtype == "MultiPolygon":
        return [c for poly in raw for ring in poly for c in ring]
    if gtype == "GeometryCollection":
        return [c for g in geometry.get("geometries", []) for c in _collect_coords(g)]
    return []


def _perpendicular_distance(point: list[float], line_start: list[float], line_end: list[float]) -> float:
    """Compute the perpendicular distance from a point to a line segment (in coordinate units)."""
    if line_start == line_end:
        return math.hypot(point[0] - line_start[0], point[1] - line_start[1])
    dx = line_end[0] - line_start[0]
    dy = line_end[1] - line_start[1]
    d = abs(dy * point[0] - dx * point[1] + line_end[0] * line_start[1] - line_end[1] * line_start[0])
    return d / math.hypot(dx, dy)


def _rdp(coords: list[list[float]], epsilon: float) -> list[list[float]]:
    """Ramer-Douglas-Peucker simplification."""
    if len(coords) < 3:
        return coords
    max_dist = 0.0
    max_idx = 0
    for i in range(1, len(coords) - 1):
        d = _perpendicular_distance(coords[i], coords[0], coords[-1])
        if d > max_dist:
            max_dist = d
            max_idx = i
    if max_dist > epsilon:
        left = _rdp(coords[:max_idx + 1], epsilon)
        right = _rdp(coords[max_idx:], epsilon)
        return left[:-1] + right
    return [coords[0], coords[-1]]


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
def compute_bbox(geojson_str: str) -> str:
    """Compute the bounding box of a GeoJSON object.

    Args:
        geojson_str: A GeoJSON string (Feature, FeatureCollection, or Geometry).
    Returns a JSON object with the bounding box [min_lon, min_lat, max_lon, max_lat].
    """
    try:
        data = json.loads(geojson_str)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    coords: list[list[float]] = []
    if data.get("type") == "FeatureCollection":
        for f in data.get("features", []):
            if f.get("geometry"):
                coords.extend(_collect_coords(f["geometry"]))
    elif data.get("type") == "Feature":
        if data.get("geometry"):
            coords.extend(_collect_coords(data["geometry"]))
    else:
        coords.extend(_collect_coords(data))

    if not coords:
        return json.dumps({"error": "No coordinates found in the GeoJSON input."})

    lons = [c[0] for c in coords if len(c) >= 2]
    lats = [c[1] for c in coords if len(c) >= 2]

    return json.dumps(
        {
            "bbox": [min(lons), min(lats), max(lons), max(lats)],
            "west": min(lons), "south": min(lats), "east": max(lons), "north": max(lats),
            "center": {
                "longitude": round((min(lons) + max(lons)) / 2, 6),
                "latitude": round((min(lats) + max(lats)) / 2, 6),
            },
        }
    )


@tool
def compute_centroid(geojson_str: str) -> str:
    """Compute the arithmetic centroid of all coordinates in a GeoJSON object.

    Args:
        geojson_str: A GeoJSON string (Feature, FeatureCollection, or Geometry).
    Returns the centroid as a GeoJSON Point Feature.
    """
    try:
        data = json.loads(geojson_str)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    coords: list[list[float]] = []
    if data.get("type") == "FeatureCollection":
        for f in data.get("features", []):
            if f.get("geometry"):
                coords.extend(_collect_coords(f["geometry"]))
    elif data.get("type") == "Feature":
        if data.get("geometry"):
            coords.extend(_collect_coords(data["geometry"]))
    else:
        coords.extend(_collect_coords(data))

    if not coords:
        return json.dumps({"error": "No coordinates found."})

    lons = [c[0] for c in coords if len(c) >= 2]
    lats = [c[1] for c in coords if len(c) >= 2]
    clon = sum(lons) / len(lons)
    clat = sum(lats) / len(lats)

    return json.dumps(
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(clon, 7), round(clat, 7)]},
            "properties": {
                "centroid_longitude": round(clon, 7),
                "centroid_latitude": round(clat, 7),
                "point_count": len(coords),
            },
        }
    )


@tool
def simplify_linestring(coordinates_json: str, tolerance: float = 0.0001) -> str:
    """Simplify a LineString by reducing its vertices using Ramer-Douglas-Peucker.

    Args:
        coordinates_json: JSON array of [lon, lat] coordinate pairs, or a GeoJSON
            LineString geometry, or a GeoJSON Feature with a LineString geometry.
        tolerance: Simplification tolerance in coordinate degrees (default 0.0001 ≈ ~11m).
    Returns the simplified coordinate array and reduction statistics.
    """
    try:
        data = json.loads(coordinates_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if isinstance(data, dict):
        if data.get("type") == "Feature":
            data = data.get("geometry", {})
        if data.get("type") == "LineString":
            coords = data["coordinates"]
        else:
            return json.dumps({"error": "Provide a LineString geometry or array of coordinates."})
    elif isinstance(data, list):
        coords = data
    else:
        return json.dumps({"error": "Unrecognised input format."})

    if len(coords) < 2:
        return json.dumps({"error": "LineString needs at least 2 coordinate pairs."})

    simplified = _rdp(coords, tolerance)
    reduction_pct = round((1 - len(simplified) / len(coords)) * 100, 1)

    return json.dumps(
        {
            "original_vertex_count": len(coords),
            "simplified_vertex_count": len(simplified),
            "reduction_percent": reduction_pct,
            "tolerance": tolerance,
            "simplified_geometry": {
                "type": "LineString",
                "coordinates": [[round(c[0], 7), round(c[1], 7)] for c in simplified],
            },
        }
    )


@tool
def validate_geojson(geojson_str: str) -> str:
    """Validate a GeoJSON string and report structural or coordinate issues.

    Args:
        geojson_str: The GeoJSON string to validate.
    Returns a JSON object with validation status and any issues found.
    """
    issues: list[str] = []

    try:
        data = json.loads(geojson_str)
    except json.JSONDecodeError as exc:
        return json.dumps({"valid": False, "issues": [f"JSON parse error: {exc}"]})

    valid_types = {
        "Point", "MultiPoint", "LineString", "MultiLineString",
        "Polygon", "MultiPolygon", "GeometryCollection",
        "Feature", "FeatureCollection",
    }

    gtype = data.get("type")
    if gtype not in valid_types:
        issues.append(f"Invalid or missing 'type'. Got: {gtype!r}")

    if gtype == "FeatureCollection":
        features = data.get("features")
        if not isinstance(features, list):
            issues.append("'features' must be a JSON array.")
        else:
            for i, f in enumerate(features):
                if f.get("type") != "Feature":
                    issues.append(f"Feature at index {i} has invalid 'type': {f.get('type')!r}")

    if gtype == "Feature":
        if "geometry" not in data:
            issues.append("Feature is missing 'geometry'.")
        if "properties" not in data:
            issues.append("Feature is missing 'properties' (should be null or an object).")

    # Validate coordinate ranges
    all_coords: list[list[float]] = []
    if gtype == "FeatureCollection":
        for f in data.get("features", []):
            if f.get("geometry"):
                all_coords.extend(_collect_coords(f["geometry"]))
    elif gtype == "Feature":
        if data.get("geometry"):
            all_coords.extend(_collect_coords(data["geometry"]))
    else:
        all_coords.extend(_collect_coords(data))

    for c in all_coords:
        if len(c) < 2:
            issues.append(f"Coordinate {c!r} has fewer than 2 elements.")
            continue
        lon, lat = c[0], c[1]
        if not (-180 <= lon <= 180):
            issues.append(f"Longitude out of range: {lon}")
        if not (-90 <= lat <= 90):
            issues.append(f"Latitude out of range: {lat}")

    return json.dumps(
        {
            "valid": len(issues) == 0,
            "type": gtype,
            "coordinate_count": len(all_coords),
            "issues": issues,
        }
    )


@tool
def merge_feature_collections(collections_json: str) -> str:
    """Merge multiple GeoJSON FeatureCollections into a single FeatureCollection.

    Args:
        collections_json: JSON array of GeoJSON FeatureCollection objects.
    Returns a merged GeoJSON FeatureCollection.
    """
    try:
        collections = json.loads(collections_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if not isinstance(collections, list):
        return json.dumps({"error": "Provide a JSON array of FeatureCollection objects."})

    merged_features: list[dict[str, Any]] = []
    for i, col in enumerate(collections):
        if not isinstance(col, dict):
            return json.dumps({"error": f"Item at index {i} is not a JSON object."})
        if col.get("type") != "FeatureCollection":
            return json.dumps({"error": f"Item at index {i} is not a FeatureCollection (type={col.get('type')!r})."})
        merged_features.extend(col.get("features", []))

    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": merged_features,
            "properties": {"merged_count": len(collections), "total_features": len(merged_features)},
        }
    )


GEO_GEOMETRY_OPS_TOOLS = [
    compute_bbox,
    compute_centroid,
    simplify_linestring,
    validate_geojson,
    merge_feature_collections,
]
_TOOL_MAP = {t.name: t for t in GEO_GEOMETRY_OPS_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the Geo Geometry Ops sub-agent."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"geo_geometry_ops": f"[geo_geometry_ops agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    llm = build_llm(
        get_agent_model_config("geo_geometry_ops_agent"), streaming=True
    ).bind_tools(GEO_GEOMETRY_OPS_TOOLS)

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]

    for _ in range(get_agent_max_iterations("geo_geometry_ops_agent")):
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
        messages[-1].content if messages else "geo_geometry_ops agent returned no result."
    )
    return {"sub_results": {"geo_geometry_ops": str(result_content)}}
