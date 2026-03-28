"""WFS Agent – Web Feature Service interaction.

Specialises in:
  • Fetching and parsing WFS GetCapabilities documents
  • Listing feature types exposed by a WFS server
  • Retrieving vector features via GetFeature (returns GeoJSON)
  • Describing the schema of a feature type via DescribeFeatureType

Exposed as a single async function `run` usable as a LangGraph node or called
directly by the geo_ogc_agent orchestrator.
"""
from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agent.model_config import build_llm, get_agent_model_config, get_agent_max_iterations
from app.agent.state import AgentState
from libs.geo_ogc.wfs import (
    wfs_describe_feature_type,
    wfs_get_capabilities,
    wfs_get_feature,
)

_SYSTEM_PROMPT = """You are the WFS Agent of the PangIA GeoIA platform.
Your role is to interact with OGC Web Feature Service (WFS) endpoints on behalf of the user.

## Capabilities
- `get_wfs_capabilities`: Fetch and parse the capabilities of a WFS server, listing all
  available feature types with their metadata.
- `list_wfs_layers`: List all feature types (layers) available on a WFS server.
- `get_wfs_features`: Retrieve vector features from a WFS layer as GeoJSON.
- `describe_wfs_feature_type`: Retrieve the schema definition of a WFS feature type.

## Guidelines
- Always call `get_wfs_capabilities` first if you need to discover available feature types.
- When returning features, summarise their count and key attributes rather than dumping
  all raw coordinates.
- Use GeoJSON output format when possible for compatibility with the frontend map renderer.
- Answer in the same language as the user's question.
- **Never** include map embed code, Mapbox snippets, Leaflet HTML, access tokens, or
  rendering instructions in your answer – maps are rendered by the frontend.
"""


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
async def get_wfs_capabilities(url: str) -> str:
    """Fetch and parse the GetCapabilities document of a WFS server.

    Args:
        url: WFS service endpoint URL (e.g. 'https://example.com/wfs').
    Returns a JSON summary of the service with available feature types and their metadata.
    """
    try:
        result = await wfs_get_capabilities(url)
        summary = {
            "service_title": result["service_title"],
            "service_abstract": result["service_abstract"],
            "wfs_version": result["wfs_version"],
            "feature_type_count": len(result["feature_types"]),
            "feature_types": result["feature_types"],
        }
        return json.dumps(summary)
    except Exception as exc:
        return json.dumps({"error": f"Failed to fetch WFS capabilities from '{url}': {exc}"})


@tool
async def list_wfs_layers(url: str) -> str:
    """List all feature types (layers) available on a WFS server.

    Args:
        url: WFS service endpoint URL.
    Returns a JSON array of feature type descriptors (name, title, CRS, bounding box).
    """
    try:
        result = await wfs_get_capabilities(url)
        feature_types = [
            {
                "name": ft["name"],
                "title": ft["title"],
                "abstract": ft["abstract"],
                "crs": ft["crs"],
                "bbox": ft["bbox"],
            }
            for ft in result["feature_types"]
        ]
        return json.dumps({
            "url": url,
            "feature_type_count": len(feature_types),
            "feature_types": feature_types,
        })
    except Exception as exc:
        return json.dumps({"error": f"Failed to list WFS feature types from '{url}': {exc}"})


@tool
async def get_wfs_features(
    url: str,
    type_name: str,
    bbox: str = "",
    max_features: int = 100,
    version: str = "2.0.0",
) -> str:
    """Retrieve vector features from a WFS layer as GeoJSON.

    Args:
        url: WFS service endpoint URL.
        type_name: Feature type (layer) name to query (e.g. 'my:Roads').
        bbox: Optional bounding box filter as 'minx,miny,maxx,maxy'
              (e.g. '-5.0,41.0,10.0,52.0' for Western Europe in EPSG:4326).
              Leave empty for no spatial filter.
        max_features: Maximum number of features to return (default 100).
        version: WFS protocol version ('1.0.0', '1.1.0', or '2.0.0', default '2.0.0').
    Returns a JSON object with the GeoJSON FeatureCollection and feature count.
    """
    try:
        result = await wfs_get_feature(
            url=url,
            type_name=type_name,
            bbox=bbox,
            max_features=max_features,
            output_format="application/json",
            version=version,
        )
        if result["geojson"] is not None:
            return json.dumps({
                "url": url,
                "type_name": result["type_name"],
                "feature_count": result["feature_count"],
                "geojson": result["geojson"],
            })
        # Non-GeoJSON response (e.g. GML) – return raw content summary
        return json.dumps({
            "url": url,
            "type_name": result["type_name"],
            "output_format": result["output_format"],
            "content_length": len(result["content"]),
            "content_preview": result["content"][:500],
        })
    except Exception as exc:
        return json.dumps({"error": f"Failed to get WFS features from '{url}': {exc}"})


@tool
async def describe_wfs_feature_type(
    url: str,
    type_name: str,
    version: str = "2.0.0",
) -> str:
    """Retrieve the schema definition of a WFS feature type.

    Args:
        url: WFS service endpoint URL.
        type_name: Feature type name to describe (e.g. 'my:Roads').
        version: WFS protocol version (default '2.0.0').
    Returns a JSON object with the raw XSD schema describing the feature type attributes.
    """
    try:
        result = await wfs_describe_feature_type(url=url, type_name=type_name, version=version)
        return json.dumps({
            "url": url,
            "type_name": result["type_name"],
            "schema_length": len(result["content"]),
            "schema": result["content"],
        })
    except Exception as exc:
        return json.dumps({
            "error": f"Failed to describe WFS feature type '{type_name}' from '{url}': {exc}"
        })


WFS_AGENT_TOOLS = [
    get_wfs_capabilities,
    list_wfs_layers,
    get_wfs_features,
    describe_wfs_feature_type,
]
_TOOL_MAP = {t.name: t for t in WFS_AGENT_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the WFS sub-agent."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"ogc_wfs": f"[wfs agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    llm = build_llm(
        get_agent_model_config("ogc_wfs_agent"), streaming=True
    ).bind_tools(WFS_AGENT_TOOLS)

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]

    collected_features: list[dict] = []

    for _ in range(get_agent_max_iterations("ogc_wfs_agent")):
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

            # Collect GeoJSON features from GetFeature responses
            if tc["name"] == "get_wfs_features":
                try:
                    parsed = json.loads(str(result))
                    geojson = parsed.get("geojson")
                    if isinstance(geojson, dict):
                        if geojson.get("type") == "FeatureCollection":
                            collected_features.extend(geojson.get("features", []))
                        elif geojson.get("type") == "Feature":
                            collected_features.append(geojson)
                except (json.JSONDecodeError, AttributeError):
                    pass

            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    result_text = (
        messages[-1].content if messages else "wfs agent returned no result."
    )

    if collected_features:
        payload = {
            "text": str(result_text),
            "geojson": {"type": "FeatureCollection", "features": collected_features},
        }
        return {"sub_results": {"ogc_wfs": json.dumps(payload)}}

    return {"sub_results": {"ogc_wfs": str(result_text)}}
