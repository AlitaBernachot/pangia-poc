"""
Geo Agent – geospatial analysis orchestrator.

This agent is the top-level entry point for all advanced geospatial analysis
tasks in PangIA.  It routes incoming requests to the most appropriate
specialised geo sub-agent(s) and merges their outputs into a coherent answer.

Sub-agent hierarchy
-------------------
Level 1 – MVP (core geospatial primitives):
  • geo_address      – Geocoder: address ↔ coordinates (Nominatim)
  • geo_spatial_parser – SpatialParser: natural language spatial understanding
  • geo_distance     – DistanceCalc: great-circle distance calculations
  • geo_buffer       – BufferAnalyser: circular and multi-ring buffer zones
  • geo_isochrone    – Isochrone: accessibility zone estimation

Level 2 – Evolution (spatial analysis):
  • geo_proximity    – Proximity: nearest-entity search and ranking
  • geo_intersection – Intersection: bounding-box overlap and containment
  • geo_area         – AreaCalculator: polygon surface area computation
  • geo_hotspot      – Hotspot: point-cluster detection and density
  • geo_shortest_path – ShortestPath: waypoint route optimisation

Level 3 – Specialised (advanced terrain & temporal):
  • geo_elevation    – Elevation: altitude retrieval (Open-Meteo)
  • geo_geometry_ops – GeometryOps: GeoJSON transformations and validation
  • geo_temporal     – TemporalAnalyst: spatio-temporal pattern detection
  • geo_viewshed     – Viewshed: geometric visibility analysis

The orchestrator uses an LLM to select which sub-agents to invoke based on
the user's question, then merges their results into a single response stored
in ``state["sub_results"]["geo"]``.

Exposed as a single async function `run` usable as a LangGraph node.
"""
from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from app.agent.model_config import build_llm, get_agent_model_config
from app.agent.specialized.geo.geo_address_agent import run as geo_address_run
from app.agent.specialized.geo.geo_area_agent import run as geo_area_run
from app.agent.specialized.geo.geo_buffer_agent import run as geo_buffer_run
from app.agent.specialized.geo.geo_distance_agent import run as geo_distance_run
from app.agent.specialized.geo.geo_elevation_agent import run as geo_elevation_run
from app.agent.specialized.geo.geo_geometry_ops_agent import run as geo_geometry_ops_run
from app.agent.specialized.geo.geo_hotspot_agent import run as geo_hotspot_run
from app.agent.specialized.geo.geo_intersection_agent import run as geo_intersection_run
from app.agent.specialized.geo.geo_isochrone_agent import run as geo_isochrone_run
from app.agent.specialized.geo.geo_proximity_agent import run as geo_proximity_run
from app.agent.specialized.geo.geo_shortest_path_agent import run as geo_shortest_path_run
from app.agent.specialized.geo.geo_spatial_parser_agent import run as geo_spatial_parser_run
from app.agent.specialized.geo.geo_temporal_agent import run as geo_temporal_run
from app.agent.specialized.geo.geo_viewshed_agent import run as geo_viewshed_run
from app.agent.state import AgentState

# ─── Sub-agent registry ───────────────────────────────────────────────────────

_SUB_AGENTS: dict[str, object] = {
    "geo_address": geo_address_run,
    "geo_spatial_parser": geo_spatial_parser_run,
    "geo_distance": geo_distance_run,
    "geo_buffer": geo_buffer_run,
    "geo_isochrone": geo_isochrone_run,
    "geo_proximity": geo_proximity_run,
    "geo_intersection": geo_intersection_run,
    "geo_area": geo_area_run,
    "geo_hotspot": geo_hotspot_run,
    "geo_shortest_path": geo_shortest_path_run,
    "geo_elevation": geo_elevation_run,
    "geo_geometry_ops": geo_geometry_ops_run,
    "geo_temporal": geo_temporal_run,
    "geo_viewshed": geo_viewshed_run,
}

_SUB_AGENT_DESCRIPTIONS = {
    "geo_address": (
        "  • geo_address       – Geocode addresses to coordinates or reverse-geocode.\n"
        "                        Use for: place name → lat/lon, lat/lon → address, batch geocoding."
    ),
    "geo_spatial_parser": (
        "  • geo_spatial_parser – Parse spatial language and extract geographic entities.\n"
        "                        Use for: interpreting 'north of', 'within 10 km', coordinate extraction."
    ),
    "geo_distance": (
        "  • geo_distance       – Compute great-circle distances between geographic points.\n"
        "                        Use for: distance between two places, distance matrices, unit conversion."
    ),
    "geo_buffer": (
        "  • geo_buffer         – Create circular buffer zones around points.\n"
        "                        Use for: 'all features within X km', zone of influence, multi-ring buffers."
    ),
    "geo_isochrone": (
        "  • geo_isochrone      – Estimate accessibility zones by travel time/mode.\n"
        "                        Use for: '15-minute walk', reachable area by car, multi-ring isochrones."
    ),
    "geo_proximity": (
        "  • geo_proximity      – Find nearest entities and rank by distance.\n"
        "                        Use for: nearest N features, filter within radius, ranked proximity lists."
    ),
    "geo_intersection": (
        "  • geo_intersection   – Spatial overlap and containment analysis.\n"
        "                        Use for: do two regions overlap, point inside bbox, spatial relationships."
    ),
    "geo_area": (
        "  • geo_area           – Compute polygon surface areas.\n"
        "                        Use for: area of a region, area unit conversion, compare to reference areas."
    ),
    "geo_hotspot": (
        "  • geo_hotspot        – Detect spatial clusters and density hotspots.\n"
        "                        Use for: clustering point data, finding high-density zones, centroids."
    ),
    "geo_shortest_path": (
        "  • geo_shortest_path  – Compute routes and optimise waypoint order.\n"
        "                        Use for: total route distance, optimise visit order (TSP), travel time."
    ),
    "geo_elevation": (
        "  • geo_elevation      – Retrieve terrain elevation data.\n"
        "                        Use for: altitude at a location, elevation profiles, ascent/descent stats."
    ),
    "geo_geometry_ops": (
        "  • geo_geometry_ops   – GeoJSON geometric transformations.\n"
        "                        Use for: bounding box, centroid, simplification, validation, merging."
    ),
    "geo_temporal": (
        "  • geo_temporal       – Spatio-temporal evolution analysis.\n"
        "                        Use for: movement analysis, velocity, trends over time, event summaries."
    ),
    "geo_viewshed": (
        "  • geo_viewshed       – Terrain visibility estimation.\n"
        "                        Use for: horizon distance, viewshed zone, line-of-sight check."
    ),
}

_ROUTER_SYSTEM = (
    "You are the Geo Agent orchestrator of the PangIA GeoIA platform.\n"
    "Your role is to analyse a geospatial question and select the minimum set of\n"
    "specialised geo sub-agents needed to answer it.\n\n"
    "Available sub-agents:\n"
    + "\n".join(_SUB_AGENT_DESCRIPTIONS.values())
    + "\n\nRules:\n"
    "  - Select the minimum set of sub-agents needed.\n"
    "  - For geocoding or address questions, use geo_address.\n"
    "  - For distance questions, use geo_distance.\n"
    "  - For buffer/zone questions, use geo_buffer.\n"
    "  - For accessibility/isochrone questions, use geo_isochrone.\n"
    "  - For natural-language spatial parsing, use geo_spatial_parser.\n"
    "  - Always include at least one sub-agent.\n"
)

_GEO_SUB_AGENT_LITERALS = Literal[
    "geo_address",
    "geo_spatial_parser",
    "geo_distance",
    "geo_buffer",
    "geo_isochrone",
    "geo_proximity",
    "geo_intersection",
    "geo_area",
    "geo_hotspot",
    "geo_shortest_path",
    "geo_elevation",
    "geo_geometry_ops",
    "geo_temporal",
    "geo_viewshed",
]


class GeoRoutingDecision(BaseModel):
    sub_agents: list[_GEO_SUB_AGENT_LITERALS]  # type: ignore[valid-type]
    reasoning: str


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: orchestrate geospatial sub-agents and return merged results."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"geo": f"[geo agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    # ── Step 1: Route to the appropriate sub-agents ────────────────────────────
    router_llm = build_llm(
        get_agent_model_config("geo_agent"), streaming=False
    ).with_structured_output(GeoRoutingDecision)

    decision: GeoRoutingDecision = router_llm.invoke(
        [SystemMessage(content=_ROUTER_SYSTEM), HumanMessage(content=user_query)]
    )

    # Validate – only keep known sub-agent names
    selected = [s for s in decision.sub_agents if s in _SUB_AGENTS]
    if not selected:
        selected = ["geo_address"]

    # ── Step 2: Run selected sub-agents sequentially ──────────────────────────
    # (Sequential execution keeps state management simple and avoids concurrency
    # issues; parallelism can be added via asyncio.gather if performance demands it.)
    all_sub_results: dict[str, str] = {}
    for sub_key in selected:
        sub_run = _SUB_AGENTS[sub_key]
        try:
            result = await sub_run(state)  # type: ignore[operator]
            all_sub_results.update(result.get("sub_results", {}))
        except Exception as exc:  # noqa: BLE001
            all_sub_results[sub_key] = f"[{sub_key} unavailable: {exc}]"

    # ── Step 3: Merge sub-results into a single geo answer ─────────────────────
    if not all_sub_results:
        return {"sub_results": {"geo": "No geospatial analysis could be performed."}}

    non_empty = {k: v for k, v in all_sub_results.items() if v and v.strip()}
    if not non_empty:
        return {"sub_results": {"geo": "Geospatial sub-agents returned no results."}}

    if len(non_empty) == 1:
        geo_answer = next(iter(non_empty.values()))
    else:
        merge_llm = build_llm(get_agent_model_config("geo_agent"), streaming=True)
        context = "\n\n".join(
            f"### {key.replace('_', ' ').title()} Result\n{val}"
            for key, val in non_empty.items()
        )
        merge_prompt = (
            f"User question: {user_query}\n\n"
            f"Geospatial sub-agent results:\n\n{context}\n\n"
            "Synthesise the above results into a single, clear, and well-structured answer. "
            "Preserve all numeric values, coordinates, and units exactly as provided."
        )
        merge_response: AIMessage = await merge_llm.ainvoke(
            [HumanMessage(content=merge_prompt)]
        )
        geo_answer = merge_response.content

    return {"sub_results": {"geo": str(geo_answer)}}
