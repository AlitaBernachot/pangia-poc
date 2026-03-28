"""
Geo Intersection Agent – spatial overlay and intersection analysis.

Specialises in:
  • Checking whether geographic features spatially intersect
  • Computing bounding-box overlap between rectangular regions
  • Identifying features contained within or overlapping a reference area
  • Producing intersection metadata (overlap ratio, shared extent)

Note: Full polygon intersection requires a geometry library such as Shapely.
This agent uses bounding-box approximations for intersection checks; for exact
polygon intersections, a PostGIS query via the postgis_agent is recommended.

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
from libs.geo.intersection import bbox_area_deg2, parse_bbox

_SYSTEM_PROMPT = """You are the Spatial Intersection Agent of the PangIA GeoIA platform.
Your role is to determine whether and how geographic features spatially overlap.

## Capabilities
- `check_bbox_intersection`: Check if two bounding boxes intersect.
- `compute_bbox_overlap`: Compute the overlapping region between two bounding boxes.
- `point_in_bbox`: Check if a point falls inside a bounding box.
- `classify_spatial_relationship`: Classify the spatial relationship between two bounding boxes
  (disjoint, intersects, contains, within, equals).

## Guidelines
- Bounding boxes are expressed as [min_lon, min_lat, max_lon, max_lat] (west, south, east, north).
- Clearly distinguish between bounding-box approximations and exact polygon results.
- For exact polygon intersection, recommend using the PostGIS agent.
- Answer in the same language as the user's question.
- **Never** include map embed code, Mapbox snippets, Leaflet HTML, access tokens, or
  rendering instructions in your answer – maps are rendered by the frontend.
"""


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
def check_bbox_intersection(bbox_a_json: str, bbox_b_json: str) -> str:
    """Check whether two bounding boxes spatially intersect.

    Args:
        bbox_a_json: JSON array [min_lon, min_lat, max_lon, max_lat] for bbox A.
        bbox_b_json: JSON array [min_lon, min_lat, max_lon, max_lat] for bbox B.
    Returns a JSON object with the intersection result.
    """
    a = parse_bbox(bbox_a_json)
    b = parse_bbox(bbox_b_json)
    if a is None:
        return json.dumps({"error": "Invalid bbox_a. Provide [min_lon, min_lat, max_lon, max_lat]."})
    if b is None:
        return json.dumps({"error": "Invalid bbox_b. Provide [min_lon, min_lat, max_lon, max_lat]."})

    aw, as_, ae, an = a
    bw, bs, be, bn = b
    intersects = not (ae < bw or aw > be or an < bs or as_ > bn)

    return json.dumps(
        {
            "bbox_a": {"west": aw, "south": as_, "east": ae, "north": an},
            "bbox_b": {"west": bw, "south": bs, "east": be, "north": bn},
            "intersects": intersects,
        }
    )


@tool
def compute_bbox_overlap(bbox_a_json: str, bbox_b_json: str) -> str:
    """Compute the overlapping region between two bounding boxes.

    Args:
        bbox_a_json: JSON array [min_lon, min_lat, max_lon, max_lat] for bbox A.
        bbox_b_json: JSON array [min_lon, min_lat, max_lon, max_lat] for bbox B.
    Returns a JSON object describing the overlap extent and ratio.
    """
    a = parse_bbox(bbox_a_json)
    b = parse_bbox(bbox_b_json)
    if a is None:
        return json.dumps({"error": "Invalid bbox_a. Provide [min_lon, min_lat, max_lon, max_lat]."})
    if b is None:
        return json.dumps({"error": "Invalid bbox_b. Provide [min_lon, min_lat, max_lon, max_lat]."})

    aw, as_, ae, an = a
    bw, bs, be, bn = b

    ow = max(aw, bw)
    os = max(as_, bs)
    oe = min(ae, be)
    on = min(an, bn)

    if ow >= oe or os >= on:
        return json.dumps(
            {
                "bbox_a": {"west": aw, "south": as_, "east": ae, "north": an},
                "bbox_b": {"west": bw, "south": bs, "east": be, "north": bn},
                "intersects": False,
                "overlap": None,
            }
        )

    overlap_area = bbox_area_deg2(ow, os, oe, on)
    area_a = bbox_area_deg2(aw, as_, ae, an)
    area_b = bbox_area_deg2(bw, bs, be, bn)
    ratio_a = overlap_area / area_a if area_a > 0 else 0.0
    ratio_b = overlap_area / area_b if area_b > 0 else 0.0

    return json.dumps(
        {
            "bbox_a": {"west": aw, "south": as_, "east": ae, "north": an},
            "bbox_b": {"west": bw, "south": bs, "east": be, "north": bn},
            "intersects": True,
            "overlap": {
                "west": ow, "south": os, "east": oe, "north": on,
                "area_deg2": round(overlap_area, 8),
            },
            "overlap_ratio_a": round(ratio_a, 4),
            "overlap_ratio_b": round(ratio_b, 4),
        }
    )


@tool
def point_in_bbox(latitude: float, longitude: float, bbox_json: str) -> str:
    """Check whether a geographic point falls inside a bounding box.

    Args:
        latitude: Point latitude in decimal degrees.
        longitude: Point longitude in decimal degrees.
        bbox_json: JSON array [min_lon, min_lat, max_lon, max_lat].
    Returns a JSON object indicating containment.
    """
    bbox = parse_bbox(bbox_json)
    if bbox is None:
        return json.dumps({"error": "Invalid bbox. Provide [min_lon, min_lat, max_lon, max_lat]."})

    w, s, e, n = bbox
    inside = (w <= longitude <= e) and (s <= latitude <= n)

    return json.dumps(
        {
            "point": {"latitude": latitude, "longitude": longitude},
            "bbox": {"west": w, "south": s, "east": e, "north": n},
            "inside": inside,
        }
    )


@tool
def classify_spatial_relationship(bbox_a_json: str, bbox_b_json: str) -> str:
    """Classify the spatial relationship between two bounding boxes.

    Possible relationships: 'disjoint', 'intersects', 'contains', 'within', 'equals'.

    Args:
        bbox_a_json: JSON array [min_lon, min_lat, max_lon, max_lat] for bbox A.
        bbox_b_json: JSON array [min_lon, min_lat, max_lon, max_lat] for bbox B.
    Returns a JSON object with the DE-9IM-inspired classification.
    """
    a = parse_bbox(bbox_a_json)
    b = parse_bbox(bbox_b_json)
    if a is None:
        return json.dumps({"error": "Invalid bbox_a."})
    if b is None:
        return json.dumps({"error": "Invalid bbox_b."})

    aw, as_, ae, an = a
    bw, bs, be, bn = b

    # Check equality
    if aw == bw and as_ == bs and ae == be and an == bn:
        rel = "equals"
    # Check disjoint
    elif ae < bw or aw > be or an < bs or as_ > bn:
        rel = "disjoint"
    # Check A contains B
    elif aw <= bw and as_ <= bs and ae >= be and an >= bn:
        rel = "contains"
    # Check A within B
    elif bw <= aw and bs <= as_ and be >= ae and bn >= an:
        rel = "within"
    else:
        rel = "intersects"

    return json.dumps(
        {
            "bbox_a": {"west": aw, "south": as_, "east": ae, "north": an},
            "bbox_b": {"west": bw, "south": bs, "east": be, "north": bn},
            "relationship": rel,
            "note": "Bounding-box approximation. For exact polygon relationships use PostGIS.",
        }
    )


GEO_INTERSECTION_TOOLS = [
    check_bbox_intersection,
    compute_bbox_overlap,
    point_in_bbox,
    classify_spatial_relationship,
]
_TOOL_MAP = {t.name: t for t in GEO_INTERSECTION_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the Geo Intersection sub-agent."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"geo_intersection": f"[geo_intersection agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    llm = build_llm(
        get_agent_model_config("geo_intersection_agent"), streaming=True
    ).bind_tools(GEO_INTERSECTION_TOOLS)

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]

    for _ in range(get_agent_max_iterations("geo_intersection_agent")):
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
        messages[-1].content if messages else "geo_intersection agent returned no result."
    )
    return {"sub_results": {"geo_intersection": str(result_content)}}
