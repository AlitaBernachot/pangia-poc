"""
Geo Area Agent – surface area calculations.

Specialises in:
  • Computing the approximate area of geographic polygons using the spherical excess formula
  • Summing and comparing multiple polygon areas
  • Converting areas between different units (m², km², hectares, acres, etc.)
  • Reporting relative sizes (e.g. "X times the size of France")

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
from libs.geo.area import REFERENCE_AREAS_KM2, format_area, spherical_polygon_area

_SYSTEM_PROMPT = """You are the Area Calculation Agent of the PangIA GeoIA platform.
Your role is to compute and compare surface areas of geographic features.

## Capabilities
- `calculate_polygon_area`: Compute the area of a polygon defined by lat/lon coordinates.
- `convert_area`: Convert an area value between different units.
- `compare_to_reference`: Compare an area to well-known reference regions.
- `sum_areas`: Sum multiple area values (e.g. from multiple polygons).

## Guidelines
- Polygon area calculations use the spherical excess formula on the WGS-84 sphere.
- Always report areas in multiple units for clarity (m², km², hectares).
- Use reference comparisons to make large areas intuitive.
- Answer in the same language as the user's question.
- **Never** include map embed code, Mapbox snippets, Leaflet HTML, access tokens, or
  rendering instructions in your answer – maps are rendered by the frontend.
"""

# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
def calculate_polygon_area(coordinates_json: str) -> str:
    """Compute the approximate area of a geographic polygon.

    Args:
        coordinates_json: JSON array of coordinate pairs. Accepts:
            - Array of [lon, lat] pairs (GeoJSON order): '[[2.35, 48.85], [2.40, 48.85], ...]'
            - Array of {'lat': ..., 'lon': ...} objects
            - GeoJSON Polygon geometry object
    Returns a JSON object with the area in multiple units.
    """
    try:
        data = json.loads(coordinates_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    # Handle GeoJSON Polygon
    if isinstance(data, dict) and data.get("type") == "Polygon":
        ring = data["coordinates"][0]
        coords = [(c[1], c[0]) for c in ring]  # GeoJSON is [lon, lat]
    elif isinstance(data, dict) and data.get("type") == "Feature":
        geom = data.get("geometry", {})
        if geom.get("type") == "Polygon":
            ring = geom["coordinates"][0]
            coords = [(c[1], c[0]) for c in ring]
        else:
            return json.dumps({"error": "Feature geometry must be a Polygon."})
    elif isinstance(data, list):
        coords = []
        for item in data:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                # Assume [lon, lat] (GeoJSON order)
                coords.append((float(item[1]), float(item[0])))
            elif isinstance(item, dict) and "lat" in item:
                coords.append((float(item["lat"]), float(item.get("lon", item.get("lng", 0)))))
            else:
                return json.dumps({"error": f"Unrecognised coordinate format: {item}"})
    else:
        return json.dumps({"error": "Provide a GeoJSON Polygon, Feature, or coordinate array."})

    if len(coords) < 3:
        return json.dumps({"error": "A polygon needs at least 3 coordinates."})

    area_m2 = spherical_polygon_area(coords)
    return json.dumps(
        {
            "vertex_count": len(coords),
            "area": format_area(area_m2),
            "method": "spherical excess (WGS-84 sphere)",
        }
    )


@tool
def convert_area(value: float, from_unit: str, to_unit: str) -> str:
    """Convert an area value between supported units.

    Supported units: 'm2', 'km2', 'hectares', 'acres', 'sq_miles', 'sq_feet'.
    Args:
        value: Numeric area value.
        from_unit: Source unit string.
        to_unit: Target unit string.
    """
    to_m2: dict[str, float] = {
        "m2": 1.0,
        "km2": 1_000_000.0,
        "hectares": 10_000.0,
        "ha": 10_000.0,
        "acres": 4046.856,
        "acre": 4046.856,
        "sq_miles": 2_589_988.11,
        "sq_feet": 0.0929,
        "sq_ft": 0.0929,
    }
    fk = from_unit.lower().strip().replace(" ", "_")
    tk = to_unit.lower().strip().replace(" ", "_")

    if fk not in to_m2:
        return json.dumps({"error": f"Unknown unit: {from_unit}. Supported: {list(to_m2.keys())}"})
    if tk not in to_m2:
        return json.dumps({"error": f"Unknown unit: {to_unit}. Supported: {list(to_m2.keys())}"})

    m2 = value * to_m2[fk]
    converted = m2 / to_m2[tk]
    return json.dumps(
        {
            "input": {"value": value, "unit": from_unit},
            "output": {"value": round(converted, 8), "unit": to_unit},
            "intermediate_m2": round(m2, 4),
        }
    )


@tool
def compare_to_reference(area_km2: float) -> str:
    """Compare an area (in km²) to well-known geographic reference regions.

    Args:
        area_km2: Area to compare in square kilometres.
    Returns a JSON object with ratio comparisons to reference regions.
    """
    if area_km2 <= 0:
        return json.dumps({"error": "area_km2 must be positive."})

    comparisons = []
    for name, ref_km2 in REFERENCE_AREAS_KM2.items():
        ratio = area_km2 / ref_km2
        comparisons.append(
            {
                "reference": name,
                "reference_km2": ref_km2,
                "ratio": round(ratio, 4),
                "description": (
                    f"{round(ratio, 2)}x the size of {name}"
                    if ratio >= 1
                    else f"{round(1/ratio, 1)}x smaller than {name}"
                ),
            }
        )

    comparisons.sort(key=lambda x: abs(math.log(x["ratio"])))

    return json.dumps(
        {
            "input_area_km2": area_km2,
            "comparisons": comparisons,
        }
    )


@tool
def sum_areas(areas_json: str) -> str:
    """Sum multiple area values (expressed in the same unit).

    Args:
        areas_json: JSON array of objects with 'value' (float) and 'unit' (str) fields,
            or a simple JSON array of numbers (assumed to be in m²).
            Example: '[{"value": 100, "unit": "km2"}, {"value": 50000, "unit": "hectares"}]'
    Returns a JSON object with the total in multiple units.
    """
    try:
        data = json.loads(areas_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    to_m2_map: dict[str, float] = {
        "m2": 1.0, "km2": 1_000_000.0, "hectares": 10_000.0,
        "ha": 10_000.0, "acres": 4046.856, "sq_miles": 2_589_988.11,
    }

    total_m2 = 0.0
    items_processed = 0

    if isinstance(data, list):
        for item in data:
            if isinstance(item, (int, float)):
                total_m2 += float(item)
                items_processed += 1
            elif isinstance(item, dict):
                val = float(item.get("value", 0))
                unit = item.get("unit", "m2").lower().strip()
                factor = to_m2_map.get(unit, 1.0)
                total_m2 += val * factor
                items_processed += 1
    else:
        return json.dumps({"error": "Provide a JSON array of area values."})

    return json.dumps(
        {
            "items_summed": items_processed,
            "total": _format_area(total_m2),
        }
    )


GEO_AREA_TOOLS = [calculate_polygon_area, convert_area, compare_to_reference, sum_areas]
_TOOL_MAP = {t.name: t for t in GEO_AREA_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the Geo Area sub-agent."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"geo_area": f"[geo_area agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    llm = build_llm(
        get_agent_model_config("geo_area_agent"), streaming=True
    ).bind_tools(GEO_AREA_TOOLS)

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]

    for _ in range(get_agent_max_iterations("geo_area_agent")):
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
        messages[-1].content if messages else "geo_area agent returned no result."
    )
    return {"sub_results": {"geo_area": str(result_content)}}
