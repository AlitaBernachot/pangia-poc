"""
Geo Buffer Agent – spatial buffer zone analysis.

Specialises in:
  • Creating circular buffer zones around point locations
  • Generating GeoJSON polygons approximating buffer areas
  • Computing buffer statistics (area, perimeter)
  • Supporting multiple buffer radii (multi-ring buffers)

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
from libs.geo.buffer import circular_buffer_coords


_SYSTEM_PROMPT = """You are the Buffer Analysis Agent of the PangIA GeoIA platform.
Your role is to create and analyse spatial buffer zones around geographic features.

## Capabilities
- `create_circular_buffer`: Generate a circular buffer polygon around a point.
- `create_multi_ring_buffer`: Generate multiple concentric buffer rings around a point.
- `calculate_buffer_area`: Compute the area of a buffer zone.

## Guidelines
- Buffers are approximated as regular polygons (default 64 vertices) on the WGS-84 ellipsoid.
- Always state the buffer radius and resulting area in your answer.
- Use appropriate units (metres for small buffers, km for large ones).
- GeoJSON coordinates are [longitude, latitude].
- Answer in the same language as the user's question.
- **Never** include map embed code, Mapbox snippets, Leaflet HTML, access tokens, or
  rendering instructions in your answer – maps are rendered by the frontend.
"""

@tool
def create_circular_buffer(
    latitude: float,
    longitude: float,
    radius_metres: float,
    label: str = "",
) -> str:
    """Create a circular buffer polygon around a geographic point.

    Args:
        latitude: Centre latitude in decimal degrees.
        longitude: Centre longitude in decimal degrees.
        radius_metres: Buffer radius in metres.
        label: Optional name/label for the buffer feature.
    Returns a GeoJSON Feature with a Polygon geometry representing the buffer.
    """
    if not (-90 <= latitude <= 90):
        return json.dumps({"error": f"Invalid latitude: {latitude}."})
    if not (-180 <= longitude <= 180):
        return json.dumps({"error": f"Invalid longitude: {longitude}."})
    if radius_metres <= 0:
        return json.dumps({"error": "radius_metres must be positive."})

    coords = circular_buffer_coords(latitude, longitude, radius_metres)
    area_m2 = math.pi * radius_metres ** 2

    feature: dict[str, Any] = {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [coords]},
        "properties": {
            "name": label or f"Buffer {radius_metres}m around ({latitude},{longitude})",
            "center": {"latitude": latitude, "longitude": longitude},
            "radius_metres": radius_metres,
            "radius_km": round(radius_metres / 1000, 4),
            "area_m2": round(area_m2, 2),
            "area_km2": round(area_m2 / 1_000_000, 6),
            "buffer_type": "circular",
        },
    }
    return json.dumps(feature)


@tool
def create_multi_ring_buffer(
    latitude: float,
    longitude: float,
    radii_json: str,
    label: str = "",
) -> str:
    """Create multiple concentric circular buffer rings around a geographic point.

    Args:
        latitude: Centre latitude in decimal degrees.
        longitude: Centre longitude in decimal degrees.
        radii_json: JSON array of radii in metres, e.g. '[500, 1000, 2000]'.
        label: Optional base name for the buffer features.
    Returns a GeoJSON FeatureCollection with one Polygon Feature per ring.
    """
    try:
        radii: list[float] = [float(r) for r in json.loads(radii_json)]
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return json.dumps({"error": f"Invalid radii JSON: {exc}"})

    if not radii:
        return json.dumps({"error": "Provide at least one radius value."})

    radii_sorted = sorted(radii)
    features = []
    for r in radii_sorted:
        coords = circular_buffer_coords(latitude, longitude, r)
        area_m2 = math.pi * r ** 2
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [coords]},
                "properties": {
                    "name": f"{label} {r}m" if label else f"Buffer {r}m",
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius_metres": r,
                    "radius_km": round(r / 1000, 4),
                    "area_m2": round(area_m2, 2),
                    "area_km2": round(area_m2 / 1_000_000, 6),
                },
            }
        )

    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": features,
            "properties": {
                "center": {"latitude": latitude, "longitude": longitude},
                "ring_count": len(features),
                "radii_metres": radii_sorted,
            },
        }
    )


@tool
def calculate_buffer_area(radius_metres: float) -> str:
    """Calculate the area and perimeter of a circular buffer given its radius.

    Args:
        radius_metres: Buffer radius in metres.
    Returns a JSON object with area and perimeter in multiple units.
    """
    if radius_metres <= 0:
        return json.dumps({"error": "radius_metres must be positive."})

    area_m2 = math.pi * radius_metres ** 2
    perimeter_m = 2 * math.pi * radius_metres

    return json.dumps(
        {
            "radius": {
                "metres": radius_metres,
                "kilometres": round(radius_metres / 1000, 6),
                "miles": round(radius_metres / 1609.344, 6),
            },
            "area": {
                "m2": round(area_m2, 2),
                "km2": round(area_m2 / 1_000_000, 8),
                "hectares": round(area_m2 / 10_000, 4),
                "acres": round(area_m2 / 4046.856, 4),
            },
            "perimeter": {
                "metres": round(perimeter_m, 2),
                "kilometres": round(perimeter_m / 1000, 4),
            },
        }
    )


GEO_BUFFER_TOOLS = [create_circular_buffer, create_multi_ring_buffer, calculate_buffer_area]
_TOOL_MAP = {t.name: t for t in GEO_BUFFER_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the Geo Buffer sub-agent."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"geo_buffer": f"[geo_buffer agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    llm = build_llm(
        get_agent_model_config("geo_buffer_agent"), streaming=True
    ).bind_tools(GEO_BUFFER_TOOLS)

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]

    collected_features: list[dict] = []

    for _ in range(get_agent_max_iterations("geo_buffer_agent")):
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

            if tc["name"] in ("create_circular_buffer", "create_multi_ring_buffer"):
                try:
                    gj = json.loads(str(result))
                    if isinstance(gj, dict):
                        if gj.get("type") == "Feature":
                            collected_features.append(gj)
                        elif gj.get("type") == "FeatureCollection":
                            collected_features.extend(gj.get("features", []))
                except (json.JSONDecodeError, AttributeError):
                    pass

            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    result_text = (
        messages[-1].content if messages else "geo_buffer agent returned no result."
    )

    if collected_features:
        payload = {
            "text": str(result_text),
            "geojson": {"type": "FeatureCollection", "features": collected_features},
        }
        return {"sub_results": {"geo_buffer": json.dumps(payload)}}

    return {"sub_results": {"geo_buffer": str(result_text)}}
