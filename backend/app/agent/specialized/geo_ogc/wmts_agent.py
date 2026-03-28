"""WMTS Agent – Web Map Tile Service interaction.

Specialises in:
  • Fetching and parsing WMTS GetCapabilities documents
  • Listing layers and tile matrix sets exposed by a WMTS server
  • Requesting individual tiles via GetTile

Exposed as a single async function `run` usable as a LangGraph node or called
directly by the geo_ogc_agent orchestrator.
"""
from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agent.model_config import build_llm, get_agent_model_config, get_agent_max_iterations
from app.agent.state import AgentState
from libs.geo_ogc.wmts import (
    wmts_get_capabilities,
    wmts_get_tile,
)

_SYSTEM_PROMPT = """You are the WMTS Agent of the PangIA GeoIA platform.
Your role is to interact with OGC Web Map Tile Service (WMTS) endpoints on behalf of the user.

## Capabilities
- `get_wmts_capabilities`: Fetch and parse the capabilities of a WMTS server, listing all
  available layers, their supported formats, tile matrix sets, and bounding boxes.
- `list_wmts_layers`: List all layers available on a WMTS server in a human-readable format.
- `get_wmts_tile`: Request a specific map tile from a WMTS server.

## Guidelines
- Always call `get_wmts_capabilities` first if you need to discover available layers or
  tile matrix sets.
- When describing layers, include supported image formats and tile matrix set identifiers.
- For tile requests, include the tile metadata in your answer rather than the raw base64 data.
- Answer in the same language as the user's question.
- **Never** include map embed code, Mapbox snippets, Leaflet HTML, access tokens, or
  rendering instructions in your answer – maps are rendered by the frontend.
"""


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
async def get_wmts_capabilities(url: str) -> str:
    """Fetch and parse the GetCapabilities document of a WMTS server.

    Args:
        url: WMTS service endpoint URL (e.g. 'https://example.com/wmts').
    Returns a JSON summary of the service with available layers, tile matrix sets,
    and their metadata.
    """
    try:
        result = await wmts_get_capabilities(url)
        summary = {
            "service_title": result["service_title"],
            "service_abstract": result["service_abstract"],
            "layer_count": len(result["layers"]),
            "tile_matrix_set_count": len(result["tile_matrix_sets"]),
            "layers": result["layers"],
            "tile_matrix_sets": result["tile_matrix_sets"],
        }
        return json.dumps(summary)
    except Exception as exc:
        return json.dumps({"error": f"Failed to fetch WMTS capabilities from '{url}': {exc}"})


@tool
async def list_wmts_layers(url: str) -> str:
    """List all layers available on a WMTS server with their identifiers and metadata.

    Args:
        url: WMTS service endpoint URL.
    Returns a JSON array of layer descriptors (identifier, title, formats,
    tile matrix sets, bounding box).
    """
    try:
        result = await wmts_get_capabilities(url)
        layers = [
            {
                "identifier": layer["identifier"],
                "title": layer["title"],
                "abstract": layer["abstract"],
                "formats": layer["formats"],
                "tile_matrix_sets": layer["tile_matrix_sets"],
                "bbox": layer["bbox"],
            }
            for layer in result["layers"]
        ]
        return json.dumps({
            "url": url,
            "layer_count": len(layers),
            "layers": layers,
            "tile_matrix_sets": result["tile_matrix_sets"],
        })
    except Exception as exc:
        return json.dumps({"error": f"Failed to list WMTS layers from '{url}': {exc}"})


@tool
async def get_wmts_tile(
    url: str,
    layer: str,
    tile_matrix_set: str,
    tile_matrix: str,
    tile_row: int,
    tile_col: int,
    image_format: str = "image/png",
    style: str = "default",
) -> str:
    """Request a single map tile from a WMTS server.

    Args:
        url: WMTS service endpoint URL.
        layer: Layer identifier (from GetCapabilities).
        tile_matrix_set: Tile matrix set identifier (e.g. 'EPSG:3857' or 'GoogleMapsCompatible').
        tile_matrix: Tile matrix (zoom level) identifier (e.g. '5' or 'EPSG:3857:5').
        tile_row: Tile row index.
        tile_col: Tile column index.
        image_format: Tile MIME type (default 'image/png').
        style: Style identifier (default 'default').
    Returns a JSON object with tile metadata and base64-encoded image data.
    """
    try:
        result = await wmts_get_tile(
            url=url,
            layer=layer,
            tile_matrix_set=tile_matrix_set,
            tile_matrix=tile_matrix,
            tile_row=tile_row,
            tile_col=tile_col,
            image_format=image_format,
            style=style,
        )
        return json.dumps({
            "url": url,
            "layer": result["layer"],
            "tile_matrix_set": result["tile_matrix_set"],
            "tile_matrix": result["tile_matrix"],
            "tile_row": result["tile_row"],
            "tile_col": result["tile_col"],
            "content_type": result["content_type"],
            "image_base64": result["image_base64"],
        })
    except Exception as exc:
        return json.dumps({"error": f"Failed to get WMTS tile from '{url}': {exc}"})


WMTS_AGENT_TOOLS = [get_wmts_capabilities, list_wmts_layers, get_wmts_tile]
_TOOL_MAP = {t.name: t for t in WMTS_AGENT_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the WMTS sub-agent."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"ogc_wmts": f"[wmts agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    llm = build_llm(
        get_agent_model_config("ogc_wmts_agent"), streaming=True
    ).bind_tools(WMTS_AGENT_TOOLS)

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]

    for _ in range(get_agent_max_iterations("ogc_wmts_agent")):
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

    result_text = (
        messages[-1].content if messages else "wmts agent returned no result."
    )

    return {"sub_results": {"ogc_wmts": str(result_text)}}
