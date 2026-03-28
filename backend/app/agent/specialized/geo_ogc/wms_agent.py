"""WMS Agent – Web Map Service interaction.

Specialises in:
  • Fetching and parsing WMS GetCapabilities documents
  • Listing layers exposed by a WMS server
  • Requesting map images via GetMap
  • Querying feature information via GetFeatureInfo

Exposed as a single async function `run` usable as a LangGraph node or called
directly by the geo_ogc_agent orchestrator.
"""
from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agent.model_config import build_llm, get_agent_model_config, get_agent_max_iterations
from app.agent.state import AgentState
from libs.geo_ogc.wms import (
    wms_get_capabilities,
    wms_get_feature_info,
    wms_get_map,
)

_SYSTEM_PROMPT = """You are the WMS Agent of the PangIA GeoIA platform.
Your role is to interact with OGC Web Map Service (WMS) endpoints on behalf of the user.

## Capabilities
- `get_wms_capabilities`: Fetch and parse the capabilities of a WMS server, listing all
  available layers with their metadata (title, abstract, CRS, bounding box).
- `list_wms_layers`: List all layers available on a WMS server in a human-readable format.
- `get_wms_map`: Request a map image from a WMS server for given layers and bounding box.
- `get_wms_feature_info`: Query attribute information for features at a specific map pixel.

## Guidelines
- Always call `get_wms_capabilities` first if you need to discover available layers.
- For map images, return the metadata (layers, bbox, dimensions) rather than the raw base64 data.
- Clearly describe the layers available and their geographic coverage.
- Answer in the same language as the user's question.
- **Never** include map embed code, Mapbox snippets, Leaflet HTML, access tokens, or
  rendering instructions in your answer – maps are rendered by the frontend.
"""


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
async def get_wms_capabilities(url: str) -> str:
    """Fetch and parse the GetCapabilities document of a WMS server.

    Args:
        url: WMS service endpoint URL (e.g. 'https://example.com/wms').
    Returns a JSON summary of the service with available layers and their metadata.
    """
    try:
        result = await wms_get_capabilities(url)
        # Omit raw_xml from the tool output to keep the context manageable
        summary = {
            "service_title": result["service_title"],
            "service_abstract": result["service_abstract"],
            "wms_version": result["wms_version"],
            "layer_count": len(result["layers"]),
            "layers": result["layers"],
        }
        return json.dumps(summary)
    except Exception as exc:
        return json.dumps({"error": f"Failed to fetch WMS capabilities from '{url}': {exc}"})


@tool
async def list_wms_layers(url: str) -> str:
    """List all layers available on a WMS server with their names, titles, and CRS.

    Args:
        url: WMS service endpoint URL.
    Returns a JSON array of layer descriptors.
    """
    try:
        result = await wms_get_capabilities(url)
        layers = [
            {
                "name": layer["name"],
                "title": layer["title"],
                "abstract": layer["abstract"],
                "crs": layer["crs"],
                "bbox": layer["bbox"],
            }
            for layer in result["layers"]
        ]
        return json.dumps({"url": url, "layer_count": len(layers), "layers": layers})
    except Exception as exc:
        return json.dumps({"error": f"Failed to list WMS layers from '{url}': {exc}"})


@tool
async def get_wms_map(
    url: str,
    layers: str,
    bbox: str,
    width: int = 512,
    height: int = 512,
    srs: str = "EPSG:4326",
    image_format: str = "image/png",
    version: str = "1.3.0",
) -> str:
    """Request a map image from a WMS server.

    Args:
        url: WMS service endpoint URL.
        layers: Comma-separated layer names to render (e.g. 'layer1,layer2').
        bbox: Bounding box as 'minx,miny,maxx,maxy' in the given SRS
              (e.g. '-5.0,41.0,10.0,52.0' for Western Europe in EPSG:4326).
        width: Image width in pixels (default 512).
        height: Image height in pixels (default 512).
        srs: Coordinate reference system identifier (default 'EPSG:4326').
        image_format: Image MIME type (default 'image/png').
        version: WMS protocol version ('1.1.1' or '1.3.0', default '1.3.0').
    Returns a JSON object with image metadata. The base64 image data is included
    for frontend rendering.
    """
    try:
        result = await wms_get_map(
            url=url,
            layers=layers,
            bbox=bbox,
            width=width,
            height=height,
            srs=srs,
            image_format=image_format,
            version=version,
        )
        return json.dumps({
            "url": url,
            "layers": result["layers"],
            "bbox": result["bbox"],
            "srs": result["srs"],
            "width": result["width"],
            "height": result["height"],
            "content_type": result["content_type"],
            "image_base64": result["image_base64"],
        })
    except Exception as exc:
        return json.dumps({"error": f"Failed to get WMS map from '{url}': {exc}"})


@tool
async def get_wms_feature_info(
    url: str,
    layers: str,
    bbox: str,
    width: int,
    height: int,
    x: int,
    y: int,
    srs: str = "EPSG:4326",
    info_format: str = "application/json",
    version: str = "1.3.0",
) -> str:
    """Query feature information at a specific pixel position on a WMS map.

    Args:
        url: WMS service endpoint URL.
        layers: Comma-separated layer names to query.
        bbox: Bounding box of the map as 'minx,miny,maxx,maxy'.
        width: Width of the map image in pixels.
        height: Height of the map image in pixels.
        x: Pixel column of the query point (0 = left edge).
        y: Pixel row of the query point (0 = top edge).
        srs: Coordinate reference system identifier (default 'EPSG:4326').
        info_format: Response format ('application/json' or 'text/xml').
        version: WMS protocol version (default '1.3.0').
    Returns a JSON object with feature attribute information from the server.
    """
    try:
        result = await wms_get_feature_info(
            url=url,
            layers=layers,
            bbox=bbox,
            width=width,
            height=height,
            x=x,
            y=y,
            srs=srs,
            info_format=info_format,
            version=version,
        )
        # Try to parse the content as JSON if the format is application/json
        content = result["content"]
        parsed_content = None
        if "json" in info_format.lower():
            try:
                parsed_content = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                pass

        return json.dumps({
            "url": url,
            "layers": result["layers"],
            "x": result["x"],
            "y": result["y"],
            "info_format": result["info_format"],
            "content": parsed_content if parsed_content is not None else content,
        })
    except Exception as exc:
        return json.dumps({"error": f"Failed to get WMS feature info from '{url}': {exc}"})


WMS_AGENT_TOOLS = [get_wms_capabilities, list_wms_layers, get_wms_map, get_wms_feature_info]
_TOOL_MAP = {t.name: t for t in WMS_AGENT_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the WMS sub-agent."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"ogc_wms": f"[wms agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    llm = build_llm(
        get_agent_model_config("ogc_wms_agent"), streaming=True
    ).bind_tools(WMS_AGENT_TOOLS)

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]

    collected_features: list[dict] = []

    for _ in range(get_agent_max_iterations("ogc_wms_agent")):
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

            # Collect any GeoJSON features returned by GetFeatureInfo
            if tc["name"] == "get_wms_feature_info":
                try:
                    parsed = json.loads(str(result))
                    content = parsed.get("content")
                    if isinstance(content, dict):
                        if content.get("type") == "FeatureCollection":
                            collected_features.extend(content.get("features", []))
                        elif content.get("type") == "Feature":
                            collected_features.append(content)
                except (json.JSONDecodeError, AttributeError):
                    pass

            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    result_text = (
        messages[-1].content if messages else "wms agent returned no result."
    )

    if collected_features:
        payload = {
            "text": str(result_text),
            "geojson": {"type": "FeatureCollection", "features": collected_features},
        }
        return {"sub_results": {"ogc_wms": json.dumps(payload)}}

    return {"sub_results": {"ogc_wms": str(result_text)}}
