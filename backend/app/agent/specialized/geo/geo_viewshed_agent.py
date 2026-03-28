"""
Geo Viewshed Agent – terrain visibility analysis.

Specialises in:
  • Estimating the theoretical line-of-sight visibility radius from a point
  • Computing the geometric horizon distance based on observer height and elevation
  • Generating approximate viewshed zones as circular GeoJSON polygons
  • Providing visibility analysis parameters for further processing

Note: True viewshed analysis requires a Digital Elevation Model (DEM) and
terrain-aware ray-casting.  This agent computes geometric approximations based
on the Earth's curvature and an assumed observer height.  For precise viewsheds,
a dedicated GIS tool (GDAL, GRASS, or a PostGIS raster extension) is required.

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
# Standard atmospheric refraction coefficient (reduces effective Earth radius)
_REFRACTION_COEFF = 0.13
_SYSTEM_PROMPT = """You are the Viewshed Analysis Agent of the PangIA GeoIA platform.
Your role is to analyse geographic visibility from observer points.

## Capabilities
- `compute_horizon_distance`: Calculate the geometric horizon distance from an observer.
- `estimate_viewshed_radius`: Estimate the maximum visibility radius accounting for curvature.
- `generate_viewshed_zone`: Produce a GeoJSON polygon representing the estimated viewshed.
- `check_line_of_sight`: Check if two points have theoretical line-of-sight (ignoring terrain).

## Important note
These visibility computations are purely geometric and do NOT account for terrain,
vegetation, buildings, or atmospheric conditions.  They represent the theoretical
maximum visibility on a smooth spherical Earth.  For realistic viewsheds, a DEM
and ray-casting algorithm would be required.

## Guidelines
- Always state observer height and the flat-Earth vs curved-Earth method used.
- Express distances in kilometres and heights in metres.
- GeoJSON coordinates are [longitude, latitude].
- Answer in the same language as the user's question.
"""


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the Haversine great-circle distance in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


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


def _effective_radius() -> float:
    """Earth radius corrected for atmospheric refraction."""
    return _EARTH_RADIUS_M / (1 - _REFRACTION_COEFF)


def _horizon_distance_m(observer_height_m: float, target_height_m: float = 0.0) -> float:
    """Geometric horizon distance accounting for atmospheric refraction.

    d = sqrt(2 * R_eff * h_obs) + sqrt(2 * R_eff * h_target)
    """
    r = _effective_radius()
    return math.sqrt(2 * r * observer_height_m) + math.sqrt(2 * r * target_height_m)


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
def compute_horizon_distance(
    observer_height_metres: float,
    target_height_metres: float = 0.0,
) -> str:
    """Calculate the geometric horizon distance from an observer at a given height.

    Args:
        observer_height_metres: Height of the observer above the surface in metres.
        target_height_metres: Height of the target object above the surface (default 0).
    Returns a JSON object with the horizon distance and formula details.
    """
    if observer_height_metres < 0:
        return json.dumps({"error": "observer_height_metres must be non-negative."})
    if target_height_metres < 0:
        return json.dumps({"error": "target_height_metres must be non-negative."})

    dist_m = _horizon_distance_m(observer_height_metres, target_height_metres)
    r_eff = _effective_radius()

    return json.dumps(
        {
            "observer_height_m": observer_height_metres,
            "target_height_m": target_height_metres,
            "effective_earth_radius_km": round(r_eff / 1000, 1),
            "refraction_coefficient": _REFRACTION_COEFF,
            "horizon_distance": {
                "metres": round(dist_m, 1),
                "kilometres": round(dist_m / 1000, 3),
                "miles": round(dist_m / 1609.344, 3),
            },
            "method": "geometric (curved Earth + standard refraction, no DEM)",
        }
    )


@tool
def estimate_viewshed_radius(
    observer_height_metres: float,
    elevation_asl_metres: float = 0.0,
) -> str:
    """Estimate the maximum visibility radius from an observer point.

    Args:
        observer_height_metres: Height of the observer above the local ground surface in metres.
        elevation_asl_metres: Elevation of the observer location above sea level (default 0).
    Returns a JSON object with visibility radius and area estimate.
    """
    if observer_height_metres < 0:
        return json.dumps({"error": "observer_height_metres must be non-negative."})

    total_height = observer_height_metres + elevation_asl_metres
    radius_m = _horizon_distance_m(total_height)
    area_km2 = math.pi * (radius_m / 1000) ** 2

    return json.dumps(
        {
            "observer_height_m": observer_height_metres,
            "observer_elevation_asl_m": elevation_asl_metres,
            "total_height_m": total_height,
            "visibility_radius": {
                "metres": round(radius_m, 1),
                "kilometres": round(radius_m / 1000, 3),
            },
            "viewshed_area_km2": round(area_km2, 2),
            "method": "geometric approximation (no DEM, no terrain occlusion)",
        }
    )


@tool
def generate_viewshed_zone(
    latitude: float,
    longitude: float,
    observer_height_metres: float,
    elevation_asl_metres: float = 0.0,
    label: str = "",
    n_vertices: int = 64,
) -> str:
    """Generate a GeoJSON polygon representing the estimated viewshed zone.

    Args:
        latitude: Observer latitude in decimal degrees.
        longitude: Observer longitude in decimal degrees.
        observer_height_metres: Height of the observer above the ground in metres.
        elevation_asl_metres: Ground elevation above sea level in metres (default 0).
        label: Optional label for the viewshed feature.
        n_vertices: Number of vertices in the approximating polygon (default 64).
    Returns a GeoJSON Feature with a Polygon geometry.
    """
    if not (-90 <= latitude <= 90):
        return json.dumps({"error": f"Invalid latitude: {latitude}."})
    if not (-180 <= longitude <= 180):
        return json.dumps({"error": f"Invalid longitude: {longitude}."})

    total_height = max(0.0, observer_height_metres + elevation_asl_metres)
    radius_m = _horizon_distance_m(total_height)

    coords = []
    for i in range(n_vertices):
        bearing = 360.0 * i / n_vertices
        dlat, dlon = _destination_point(latitude, longitude, bearing, radius_m)
        coords.append([round(dlon, 7), round(dlat, 7)])
    coords.append(coords[0])

    area_km2 = math.pi * (radius_m / 1000) ** 2

    feature: dict[str, Any] = {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [coords]},
        "properties": {
            "name": label or f"Viewshed from ({latitude},{longitude}) h={observer_height_metres}m",
            "observer": {"latitude": latitude, "longitude": longitude},
            "observer_height_m": observer_height_metres,
            "elevation_asl_m": elevation_asl_metres,
            "visibility_radius_km": round(radius_m / 1000, 3),
            "viewshed_area_km2": round(area_km2, 2),
            "method": "geometric approximation (no DEM)",
        },
    }
    return json.dumps(feature)


@tool
def check_line_of_sight(
    obs_lat: float,
    obs_lon: float,
    obs_height_m: float,
    target_lat: float,
    target_lon: float,
    target_height_m: float = 0.0,
) -> str:
    """Check whether two points have theoretical line-of-sight (ignoring terrain).

    Compares the actual distance between points to the geometric horizon distance.

    Args:
        obs_lat: Observer latitude in decimal degrees.
        obs_lon: Observer longitude in decimal degrees.
        obs_height_m: Observer height above the surface in metres.
        target_lat: Target latitude in decimal degrees.
        target_lon: Target longitude in decimal degrees.
        target_height_m: Target height above the surface in metres (default 0).
    Returns a JSON object with line-of-sight assessment.
    """
    dist_m = _haversine(obs_lat, obs_lon, target_lat, target_lon)
    max_dist_m = _horizon_distance_m(obs_height_m, target_height_m)
    visible = dist_m <= max_dist_m

    return json.dumps(
        {
            "observer": {"latitude": obs_lat, "longitude": obs_lon, "height_m": obs_height_m},
            "target": {"latitude": target_lat, "longitude": target_lon, "height_m": target_height_m},
            "actual_distance_km": round(dist_m / 1000, 4),
            "max_visible_distance_km": round(max_dist_m / 1000, 4),
            "line_of_sight": visible,
            "note": "Geometric check only – terrain, vegetation, and buildings not considered.",
        }
    )


GEO_VIEWSHED_TOOLS = [
    compute_horizon_distance,
    estimate_viewshed_radius,
    generate_viewshed_zone,
    check_line_of_sight,
]
_TOOL_MAP = {t.name: t for t in GEO_VIEWSHED_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the Geo Viewshed sub-agent."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"geo_viewshed": f"[geo_viewshed agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    llm = build_llm(
        get_agent_model_config("geo_viewshed_agent"), streaming=True
    ).bind_tools(GEO_VIEWSHED_TOOLS)

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]

    for _ in range(get_agent_max_iterations("geo_viewshed_agent")):
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
        messages[-1].content if messages else "geo_viewshed agent returned no result."
    )
    return {"sub_results": {"geo_viewshed": str(result_content)}}
