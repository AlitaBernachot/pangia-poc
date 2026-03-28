"""
Map Agent – geographic data extraction and GeoJSON structuring.

Specialises in:
  • extracting coordinates from free text
  • geocoding addresses / place names to coordinates
  • building structured GeoJSON FeatureCollections
  • computing map bounds for auto-centering
  • enriching GeoJSON features with popup content

The agent returns a GeoJSON FeatureCollection (stored in state["geojson"])
alongside a human-readable summary (stored in state["sub_results"]["map"]).
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agent.model_config import build_llm, get_agent_model_config, get_agent_max_iterations
from app.agent.state import AgentState

# ─── System prompt ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are the Map Agent of the PangIA GeoIA platform.
Your role is to extract geographic entities from the provided context (results from
other agents and the original user question) and build a structured GeoJSON
FeatureCollection that can be displayed on an interactive map.

## Workflow
1. Read the **[AGENT RESULTS]** section carefully: it contains the output of other
   specialised sub-agents (e.g. Neo4j, PostGIS) enriched with coordinates, site
   names, and country information.
2. For each location found in the context:
   - If exact coordinates (lat/lon) are present in the text, use
     `extract_geojson_from_text` passing the relevant excerpt.
   - If only a name or address is given, use `geocode_address` to obtain
     coordinates.
3. Use the site name and country from the context to set a meaningful `name`
   property on each feature.
4. Collect all resulting Feature objects and assemble them into a single
   FeatureCollection using `create_geojson`.
5. Enrich every feature with a descriptive popup using `add_popup_content`
   (include the site name, country, and any other relevant facts from the context).
6. Compute the map viewport with `calculate_bounds`.
7. **Your final message must be a single valid JSON object** with exactly these
   two keys:
   {{"geojson": <FeatureCollection or null>, "summary": "<one-line description>"}}

## Rules
- GeoJSON coordinates are [longitude, latitude] (not lat, lon).
- If no geographic data can be extracted, return:
  {{"geojson": null, "summary": "No geographic data found."}}
- Keep popup content concise (2–4 lines of plain text or simple HTML).
"""


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
async def extract_geojson_from_text(text: str) -> str:
    """Extract latitude/longitude coordinate pairs from free text and return a GeoJSON FeatureCollection."""
    patterns = [
        # lat: 48.8566, lon: 2.3522
        r"(?:lat(?:itude)?)\s*[=:]\s*(-?\d+\.?\d*)[,\s]+(?:lon(?:gitude)?)\s*[=:]\s*(-?\d+\.?\d*)",
        # (48.8566, 2.3522)
        r"\(\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*\)",
        # standalone 48.8566, 2.3522  (requires at least 1 decimal digit)
        r"(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)",
    ]
    # Hemisphere pattern: 48.8566°N 2.3522°E (no negative sign with hemisphere indicator)
    hemisphere_pattern = re.compile(
        r"(\d+\.?\d*)°\s*([NS])\s+(\d+\.?\d*)°\s*([EW])", re.IGNORECASE
    )

    features: list[dict[str, Any]] = []
    seen: set[tuple[float, float]] = set()

    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            try:
                lat, lon = float(m.group(1)), float(m.group(2))
            except ValueError:
                continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            key = (round(lat, 5), round(lon, 5))
            if key in seen:
                continue
            seen.add(key)
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {"name": f"{lat}, {lon}"},
                }
            )

    # Handle hemisphere notation separately
    for m in hemisphere_pattern.finditer(text):
        lat = float(m.group(1)) * (-1 if m.group(2).upper() == "S" else 1)
        lon = float(m.group(3)) * (-1 if m.group(4).upper() == "W" else 1)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        key = (round(lat, 5), round(lon, 5))
        if key in seen:
            continue
        seen.add(key)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {"name": f"{lat}, {lon}"},
            }
        )

    if not features:
        return "No coordinate pairs found in the provided text."
    return json.dumps({"type": "FeatureCollection", "features": features})


@tool
async def geocode_address(address: str) -> str:
    """Convert a place name or address to geographic coordinates using OpenStreetMap Nominatim."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address, "format": "json", "limit": 1}
    headers = {"User-Agent": "PangIA-GeoIA/0.1 (contact@pangia.io)"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            results = resp.json()
        if not results:
            return f"No coordinates found for: {address}"
        r = results[0]
        lat, lon = float(r["lat"]), float(r["lon"])
        feature: dict[str, Any] = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "name": address,
                "display_name": r.get("display_name", address),
                "place_type": r.get("type", ""),
                "osm_id": r.get("osm_id", ""),
            },
        }
        return json.dumps(feature)
    except Exception as exc:
        return f"Geocoding failed for '{address}': {exc}"


@tool
def create_geojson(features_json: str) -> str:
    """Create a GeoJSON FeatureCollection from a JSON array of Feature objects or a single Feature."""
    try:
        data = json.loads(features_json)
    except json.JSONDecodeError as exc:
        return f"Invalid JSON: {exc}"

    if isinstance(data, dict):
        if data.get("type") == "FeatureCollection":
            return features_json
        if data.get("type") == "Feature":
            data = [data]
        else:
            return f"Expected a Feature or FeatureCollection, got type={data.get('type')!r}"

    if not isinstance(data, list):
        return "Expected a JSON array of features or a single Feature object."

    collection: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    for item in data:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "Feature":
            collection["features"].append(item)
        elif "geometry" in item:
            collection["features"].append(
                {
                    "type": "Feature",
                    "geometry": item["geometry"],
                    "properties": item.get("properties") or {},
                }
            )
    return json.dumps(collection)


@tool
def calculate_bounds(geojson: str) -> str:
    """Calculate the bounding box and center of a GeoJSON object for map auto-zoom."""
    try:
        data = json.loads(geojson)
    except json.JSONDecodeError as exc:
        return f"Invalid GeoJSON: {exc}"

    coords: list[list[float]] = []

    def _collect(geometry: dict[str, Any]) -> None:
        gtype = geometry.get("type", "")
        raw = geometry.get("coordinates", [])
        if gtype == "Point":
            coords.append(raw)
        elif gtype in ("MultiPoint", "LineString"):
            coords.extend(raw)
        elif gtype in ("MultiLineString", "Polygon"):
            for ring in raw:
                coords.extend(ring)
        elif gtype == "MultiPolygon":
            for poly in raw:
                for ring in poly:
                    coords.extend(ring)

    if data.get("type") == "FeatureCollection":
        for f in data.get("features", []):
            if f.get("geometry"):
                _collect(f["geometry"])
    elif data.get("type") == "Feature":
        if data.get("geometry"):
            _collect(data["geometry"])
    else:
        _collect(data)

    if not coords:
        return "No coordinates found in the provided GeoJSON."

    lons = [c[0] for c in coords if len(c) >= 2]
    lats = [c[1] for c in coords if len(c) >= 2]
    west, east = min(lons), max(lons)
    south, north = min(lats), max(lats)

    return json.dumps(
        {
            "bounds": [[south, west], [north, east]],
            "center": [(south + north) / 2, (west + east) / 2],
            "west": west,
            "south": south,
            "east": east,
            "north": north,
        }
    )


@tool
def add_popup_content(geojson: str, popup_content: str) -> str:
    """Add a popup_content property to every feature in a GeoJSON FeatureCollection or Feature."""
    try:
        data = json.loads(geojson)
    except json.JSONDecodeError as exc:
        return f"Invalid GeoJSON: {exc}"

    def _enrich(feature: dict[str, Any]) -> None:
        if feature.get("properties") is None:
            feature["properties"] = {}
        feature["properties"]["popup_content"] = popup_content

    # Accept a raw array of Feature objects
    if isinstance(data, list):
        for feature in data:
            if isinstance(feature, dict):
                _enrich(feature)
        return json.dumps({"type": "FeatureCollection", "features": data})
    if data.get("type") == "FeatureCollection":
        for feature in data.get("features", []):
            _enrich(feature)
        return json.dumps(data)
    if data.get("type") == "Feature":
        _enrich(data)
        return json.dumps(data)
    return "Expected a GeoJSON Feature, FeatureCollection, or array of Features."


MAP_TOOLS = [
    extract_geojson_from_text,
    geocode_address,
    create_geojson,
    calculate_bounds,
    add_popup_content,
]
_TOOL_MAP = {t.name: t for t in MAP_TOOLS}


# ─── Node function ────────────────────────────────────────────────────────────

_COORD_HINT_RE = re.compile(
    r"lat(?:itude)?|lon(?:gitude)?|°[NS]|°[EW]|\b\d{1,3}\.\d+\b",
    re.IGNORECASE,
)


async def run(state: AgentState) -> dict:
    """LangGraph node: run the Map Agent after parallel sub-agents complete.

    Reads sub_results produced by other agents (e.g. Neo4j) and extracts
    geographic coordinates to build a GeoJSON FeatureCollection.  Skips the
    LLM entirely when no coordinate-like content is detected.
    """
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"map": f"[Map agent unavailable: {exc}]"}, "geojson": None}


async def _run(state: AgentState) -> dict:
    sub_results: dict[str, str] = state.get("sub_results", {})
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    # Build enriched context from all sub-agent results
    sub_text = "\n\n".join(
        f"[{agent.upper()} RESULTS]:\n{result}"
        for agent, result in sub_results.items()
        if result and result.strip()
    )

    # Quick heuristic: skip entirely if there is no geographic signal
    combined_check = f"{sub_text} {user_query}"
    if not _COORD_HINT_RE.search(combined_check):
        return {"sub_results": {"map": ""}, "geojson": None}

    llm = build_llm(get_agent_model_config("map_agent"), streaming=True).bind_tools(MAP_TOOLS)

    # Primary LLM input: enriched context from other agents + original question
    map_input = (
        f"{sub_text}\n\nOriginal user question: {user_query}"
        if sub_text
        else user_query
    )

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=map_input)]

    for _ in range(get_agent_max_iterations("map_agent")):
        response: AIMessage = await llm.ainvoke(messages)
        messages.append(response)

        if not getattr(response, "tool_calls", None):
            break

        for tc in response.tool_calls:
            tool_fn = _TOOL_MAP.get(tc["name"])
            if tool_fn is None:
                result = f"Unknown tool: {tc['name']}"
            else:
                try:
                    result = await tool_fn.ainvoke(tc["args"])
                except Exception as exc:
                    result = f"Tool error: {exc}"
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    result_content = messages[-1].content if messages else ""

    # Extract GeoJSON from the agent's final response
    geojson_data: dict[str, Any] | None = None
    summary = "Geographic data processed."

    if result_content:
        # The agent should have returned a JSON object {"geojson": ..., "summary": ...}
        try:
            parsed = json.loads(result_content)
            if isinstance(parsed, dict):
                geojson_data = parsed.get("geojson") or None
                summary = parsed.get("summary", summary)
        except (json.JSONDecodeError, ValueError):
            # Fallback: search for a JSON block in the text
            match = re.search(r'\{[^{}]*"geojson"[^{}]*\}', result_content, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                    if isinstance(parsed, dict):
                        geojson_data = parsed.get("geojson") or None
                        summary = parsed.get("summary", summary)
                except (json.JSONDecodeError, ValueError):
                    pass

    return {
        "sub_results": {"map": summary},
        "geojson": geojson_data,
    }
