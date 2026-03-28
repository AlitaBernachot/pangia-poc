"""
OGC Agent – OGC web-service orchestrator.

This agent is the top-level entry point for all OGC (Open Geospatial Consortium)
web-service interactions in PangIA.  It routes incoming requests to the most
appropriate OGC sub-agent(s) and merges their outputs into a coherent answer.

Sub-agent hierarchy
-------------------
  • ogc_wms  – WMS Agent: Web Map Service interaction
               (GetCapabilities, GetMap, GetFeatureInfo, layer listing)
  • ogc_wfs  – WFS Agent: Web Feature Service interaction
               (GetCapabilities, GetFeature, DescribeFeatureType, layer listing)
  • ogc_wmts – WMTS Agent: Web Map Tile Service interaction
               (GetCapabilities, GetTile, layer listing)

The orchestrator uses an LLM to select which sub-agents to invoke based on
the user's question, then merges their results into a single response stored
in ``state["sub_results"]["geo_ogc"]``.

Exposed as a single async function `run` usable as a LangGraph node.
"""
from __future__ import annotations

import json
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from app.agent.model_config import build_llm, get_agent_model_config
from app.agent.specialized.geo_ogc.wfs_agent import run as ogc_wfs_run
from app.agent.specialized.geo_ogc.wms_agent import run as ogc_wms_run
from app.agent.specialized.geo_ogc.wmts_agent import run as ogc_wmts_run
from app.agent.state import AgentState

# ─── Sub-agent registry ───────────────────────────────────────────────────────

_SUB_AGENTS: dict[str, object] = {
    "ogc_wms": ogc_wms_run,
    "ogc_wfs": ogc_wfs_run,
    "ogc_wmts": ogc_wmts_run,
}

_SUB_AGENT_DESCRIPTIONS = {
    "ogc_wms": (
        "  • ogc_wms  – Web Map Service (WMS).\n"
        "               Use for: discovering WMS layers (GetCapabilities), requesting map images\n"
        "               (GetMap), querying feature attributes at a map location (GetFeatureInfo),\n"
        "               listing available WMS layers, converting WMS layers to images for\n"
        "               visualisation."
    ),
    "ogc_wfs": (
        "  • ogc_wfs  – Web Feature Service (WFS).\n"
        "               Use for: discovering WFS feature types (GetCapabilities), retrieving\n"
        "               vector features as GeoJSON (GetFeature), describing feature schemas\n"
        "               (DescribeFeatureType), listing WFS layers, converting WFS data to\n"
        "               GeoJSON for spatial analysis or PostGIS integration."
    ),
    "ogc_wmts": (
        "  • ogc_wmts – Web Map Tile Service (WMTS).\n"
        "               Use for: discovering WMTS layers and tile matrix sets (GetCapabilities),\n"
        "               requesting individual pre-rendered map tiles (GetTile), listing available\n"
        "               WMTS layers and their supported formats."
    ),
}

_ROUTER_SYSTEM = (
    "You are the OGC Agent orchestrator of the PangIA GeoIA platform.\n"
    "Your role is to analyse a question about OGC web services and select the minimum set of\n"
    "specialised OGC sub-agents needed to answer it.\n\n"
    "Available sub-agents:\n"
    + "\n".join(_SUB_AGENT_DESCRIPTIONS.values())
    + "\n\nRules:\n"
    "  - Select the minimum set of sub-agents needed.\n"
    "  - For WMS questions (map images, raster layers, GetMap), use ogc_wms.\n"
    "  - For WFS questions (vector features, GeoJSON, GetFeature), use ogc_wfs.\n"
    "  - For WMTS questions (tile services, slippy maps, tile matrix sets), use ogc_wmts.\n"
    "  - For general OGC service discovery or unknown service type, use all three.\n"
    "  - Always include at least one sub-agent.\n"
    "  - Never include map embed code, Mapbox snippets, Leaflet HTML, access tokens, or "
    "rendering instructions – maps are rendered by the frontend.\n"
)

_OGC_SUB_AGENT_LITERALS = Literal["ogc_wms", "ogc_wfs", "ogc_wmts"]


class OgcRoutingDecision(BaseModel):
    sub_agents: list[_OGC_SUB_AGENT_LITERALS]  # type: ignore[valid-type]
    reasoning: str


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: orchestrate OGC sub-agents and return merged results."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"geo_ogc": f"[geo_ogc agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    # ── Step 1: Route to the appropriate sub-agents ────────────────────────────
    router_llm = build_llm(
        get_agent_model_config("geo_ogc_agent"), streaming=False
    ).with_structured_output(OgcRoutingDecision)

    decision: OgcRoutingDecision = router_llm.invoke(
        [SystemMessage(content=_ROUTER_SYSTEM), HumanMessage(content=user_query)]
    )

    # Validate – only keep known sub-agent names
    selected = [s for s in decision.sub_agents if s in _SUB_AGENTS]
    if not selected:
        selected = ["ogc_wms"]

    # ── Step 2: Run selected sub-agents sequentially ──────────────────────────
    all_sub_results: dict[str, str] = {}
    for sub_key in selected:
        sub_run = _SUB_AGENTS[sub_key]
        try:
            result = await sub_run(state)  # type: ignore[operator]
            all_sub_results.update(result.get("sub_results", {}))
        except Exception as exc:  # noqa: BLE001
            all_sub_results[sub_key] = f"[{sub_key} unavailable: {exc}]"

    # ── Step 3: Merge sub-results into a single OGC answer ────────────────────
    if not all_sub_results:
        return {"sub_results": {"geo_ogc": "No OGC service interaction could be performed."}}

    non_empty = {k: v for k, v in all_sub_results.items() if v and v.strip()}
    if not non_empty:
        return {"sub_results": {"geo_ogc": "OGC sub-agents returned no results."}}

    # ── Collect any structured GeoJSON features from sub-agent results ─────────
    direct_geo_features: list[dict] = []
    text_results: dict[str, str] = {}
    for key, val in non_empty.items():
        try:
            parsed = json.loads(val)
            if isinstance(parsed, dict) and "geojson" in parsed:
                gj = parsed.get("geojson") or {}
                if isinstance(gj, dict):
                    if gj.get("type") == "FeatureCollection":
                        direct_geo_features.extend(gj.get("features", []))
                    elif gj.get("type") == "Feature":
                        direct_geo_features.append(gj)
                text_results[key] = str(parsed.get("text", val))
            else:
                text_results[key] = val
        except (json.JSONDecodeError, AttributeError):
            text_results[key] = val

    if len(text_results) == 1:
        ogc_answer = next(iter(text_results.values()))
    else:
        merge_llm = build_llm(get_agent_model_config("geo_ogc_agent"), streaming=True)
        context = "\n\n".join(
            f"### {key.replace('_', ' ').title()} Result\n{val}"
            for key, val in text_results.items()
        )
        merge_prompt = (
            f"User question: {user_query}\n\n"
            f"OGC sub-agent results:\n\n{context}\n\n"
            "Synthesise the above results into a single, clear, and well-structured answer. "
            "Preserve all layer names, service URLs, and metadata exactly as provided. "
            "Never include map embed code, Mapbox snippets, Leaflet HTML, access tokens, or "
            "rendering instructions – maps are rendered by the frontend."
        )
        merge_response: AIMessage = await merge_llm.ainvoke(
            [HumanMessage(content=merge_prompt)]
        )
        ogc_answer = merge_response.content

    # Re-attach structured GeoJSON so the map agent can retrieve it
    if direct_geo_features:
        payload = {
            "text": str(ogc_answer),
            "geojson": {"type": "FeatureCollection", "features": direct_geo_features},
        }
        return {"sub_results": {"geo_ogc": json.dumps(payload)}}

    return {"sub_results": {"geo_ogc": str(ogc_answer)}}
