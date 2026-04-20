# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""MapViz Agent – geographic data extraction and GeoJSON structuring.

Specialises in:
  • extracting coordinates from free text
  • geocoding addresses / place names to coordinates
  • building structured GeoJSON FeatureCollections
  • computing map bounds for auto-centering
  • enriching GeoJSON features with popup content
  • converting WKT geometry strings to GeoJSON

The agent returns a GeoJSON FeatureCollection stored in
``AgentOutput.state["geojson"]`` alongside a human-readable summary in
``AgentOutput.answer``.

Note: this agent is called directly inside ``mapviz_node`` after
``humanoutput_node`` has decided that map visualisation is needed.  It is
**not** part of the router fan-out and is therefore **not** registered in
the ``AGENTS`` dict.
"""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any, Callable, Coroutine

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.models import AgentInput, AgentOutput
from app.pangiagent.agents.base_agents.base_react_agent import BaseReActAgent
from app.pangiagent.model_config import build_llm, get_agent_model_config

if TYPE_CHECKING:
    from app.pangiagent.state import OrchestratorState
from libs.filereader import rows_to_geojson

logger = logging.getLogger(__name__)

# ─── System prompt ────────────────────────────────────────────────────────────

_DEFAULT_PROMPT = """You are the Map Agent of the PangIA GeoIA platform.
Your role is to extract geographic entities from the provided context (results from
other agents and the original user question) and build a structured GeoJSON
FeatureCollection that can be displayed on an interactive map.

## Workflow
1. Read the **[AGENT RESULTS]** section carefully: it contains the output of other
   specialised sub-agents (e.g. Neo4j, PostGIS) enriched with coordinates, site
   names, and country information.
2. For each location found in the context:
   - If a WKT geometry string is present (POLYGON, MULTIPOLYGON, LINESTRING, BOX, etc.),
     use `parse_wkt_to_geojson` to convert it to a GeoJSON Feature.
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
- Be concise: answer in the fewest words needed. No preambles, no repetition.
"""

# ─── Tools ────────────────────────────────────────────────────────────────────

_COORD_HINT_RE = re.compile(
    r"lat(?:itude)?|lon(?:gitude)?|°[NS]|°[EW]|\b\d{1,3}\.\d+\b"
    r"|\b(?:POLYGON|MULTIPOLYGON|LINESTRING|MULTILINESTRING|MULTIPOINT|GEOMETRYCOLLECTION|POINT)\s*\(",
    re.IGNORECASE,
)


@tool
async def extract_geojson_from_text(text: str) -> str:
    """Extract latitude/longitude coordinate pairs from free text and return a GeoJSON FeatureCollection."""
    patterns = [
        r"(?:lat(?:itude)?)\s*[=:]\s*(-?\d+\.?\d*)[,\s]+(?:lon(?:gitude)?)\s*[=:]\s*(-?\d+\.?\d*)",
        r"\(\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*\)",
        r"(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)",
    ]
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
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {"name": f"{lat}, {lon}"},
            })

    for m in hemisphere_pattern.finditer(text):
        lat = float(m.group(1)) * (-1 if m.group(2).upper() == "S" else 1)
        lon = float(m.group(3)) * (-1 if m.group(4).upper() == "W" else 1)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        key = (round(lat, 5), round(lon, 5))
        if key in seen:
            continue
        seen.add(key)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"name": f"{lat}, {lon}"},
        })

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
    raw = features_json.strip()
    raw = re.sub(r"^```[^\n]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw.strip())
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        try:
            data, _ = decoder.raw_decode(raw)
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
            collection["features"].append({
                "type": "Feature",
                "geometry": item["geometry"],
                "properties": item.get("properties") or {},
            })
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

    return json.dumps({
        "bounds": [[south, west], [north, east]],
        "center": [(south + north) / 2, (west + east) / 2],
        "west": west, "south": south, "east": east, "north": north,
    })


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


@tool
def parse_wkt_to_geojson(wkt: str) -> str:
    """Convert a WKT (Well-Known Text) or EWKT geometry string to a GeoJSON Feature.

    Handles POINT, LINESTRING, POLYGON, MULTIPOINT, MULTILINESTRING, MULTIPOLYGON,
    and BOX types returned by PostGIS.  Automatically strips SRID prefixes.
    """
    wkt = wkt.strip()
    wkt = re.sub(r"^SRID=\d+;", "", wkt, flags=re.IGNORECASE).strip()

    def _parse_point_pair(s: str) -> list[float]:
        parts = s.strip().split()
        return [float(parts[0]), float(parts[1])]

    def _parse_ring(s: str) -> list[list[float]]:
        return [_parse_point_pair(p) for p in s.strip().split(",") if p.strip()]

    try:
        box_m = re.match(
            r"BOX\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*,\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)",
            wkt, re.IGNORECASE,
        )
        if box_m:
            minx, miny, maxx, maxy = (float(box_m.group(i)) for i in range(1, 5))
            geometry: dict[str, Any] = {
                "type": "Polygon",
                "coordinates": [[
                    [minx, miny], [minx, maxy],
                    [maxx, maxy], [maxx, miny],
                    [minx, miny],
                ]],
            }
            return json.dumps({"type": "Feature", "geometry": geometry, "properties": {}})

        m = re.match(r"^(\w+)\s*\((.*)\)$", wkt, re.IGNORECASE | re.DOTALL)
        if not m:
            return f"Could not parse WKT: {wkt[:120]}"

        geom_type = m.group(1).upper()
        inner = m.group(2).strip()

        if geom_type == "POINT":
            geometry = {"type": "Point", "coordinates": _parse_point_pair(inner)}
        elif geom_type == "LINESTRING":
            geometry = {"type": "LineString", "coordinates": _parse_ring(inner)}
        elif geom_type == "POLYGON":
            rings_raw = re.findall(r"\(([^()]+)\)", inner)
            geometry = {"type": "Polygon", "coordinates": [_parse_ring(r) for r in rings_raw]}
        elif geom_type == "MULTIPOLYGON":
            polygons = []
            for poly_block in re.finditer(
                r"\(\s*(\((?:[^()]+)\)(?:\s*,\s*\([^()]+\))*)\s*\)", inner
            ):
                rings_raw = re.findall(r"\(([^()]+)\)", poly_block.group(1))
                polygons.append([_parse_ring(r) for r in rings_raw])
            geometry = {"type": "MultiPolygon", "coordinates": polygons}
        elif geom_type == "MULTILINESTRING":
            lines_raw = re.findall(r"\(([^()]+)\)", inner)
            geometry = {"type": "MultiLineString", "coordinates": [_parse_ring(r) for r in lines_raw]}
        elif geom_type == "MULTIPOINT":
            geometry = {"type": "MultiPoint", "coordinates": _parse_ring(inner)}
        else:
            return f"Unsupported WKT geometry type: {geom_type}"

        return json.dumps({"type": "Feature", "geometry": geometry, "properties": {}})

    except Exception as exc:
        return f"WKT parsing error: {exc}"


_MAP_TOOLS = [
    extract_geojson_from_text,
    geocode_address,
    create_geojson,
    calculate_bounds,
    add_popup_content,
    parse_wkt_to_geojson,
]
_TOOL_MAP = {t.name: t for t in _MAP_TOOLS}


# ─── Agent class ──────────────────────────────────────────────────────────────


class MapVizAgent(BaseReActAgent):
    """LLM-backed agent that extracts geographic data and builds GeoJSON.

    Note: this agent is **not** registered in the orchestrator fan-out; it is
    called directly inside ``mapviz_node`` after ``humanoutput_node`` has
    determined that map visualisation is needed.
    """

    _DEFAULT_PROMPT = _DEFAULT_PROMPT

    def __init__(self, **kwargs) -> None:
        super().__init__(name="mapviz_agent", **kwargs)
        self._system_prompt = self.get_prompt(self._DEFAULT_PROMPT)

    def get_capabilities(self) -> str:
        return (
            "Map Visualisation: extracts geographic coordinates and builds GeoJSON "
            "FeatureCollections from sub-agent results for frontend map rendering."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        """Core logic – reads sub_results and pre-built geojson/dataviz from context."""
        sub_results: dict[str, str] = inp.context.get("sub_results", {})
        existing_dataviz: dict[str, Any] | None = inp.context.get("dataviz")
        existing_geojson: dict[str, Any] | None = inp.context.get("geojson")
        user_query = inp.query

        # GeoJSON already computed by a connector — return it directly
        if existing_geojson:
            output = AgentOutput(
                agent_name=self.name,
                answer="GeoJSON pré-chargé par l'agent connecteur.",
                confidence=1.0,
            )
            output.state["geojson"] = existing_geojson
            return output

        # Build GeoJSON from dataviz table coordinate columns if present
        _raw_injection = ""
        if existing_dataviz and existing_dataviz.get("tables"):
            first_table = existing_dataviz["tables"][0]
            cols = first_table.get("columns", [])
            all_rows = [dict(zip(cols, r)) for r in first_table.get("rows", [])]
            if all_rows:
                fc = rows_to_geojson(all_rows, cols)
                if fc:
                    output = AgentOutput(
                        agent_name=self.name,
                        answer=f"{len(fc['features'])} features extraits ({len(all_rows)} enregistrements).",
                        confidence=1.0,
                    )
                    output.state["geojson"] = fc
                    return output
                sample = all_rows[:30]
                _raw_injection = (
                    f"[DONNÉES COMPLÈTES – {len(all_rows)} enregistrements, "
                    f"colonnes: {', '.join(cols)}]\n"
                    f"Extrait (30 premières lignes): {json.dumps(sample, ensure_ascii=False, default=str)}\n\n"
                )

        # Extract embedded GeoJSON from structured sub-result payloads
        direct_features: list[dict[str, Any]] = []

        def _unwrap(val: str) -> str:
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    gj = parsed.get("geojson")
                    if isinstance(gj, dict):
                        if gj.get("type") == "FeatureCollection":
                            direct_features.extend(gj.get("features", []))
                        elif gj.get("type") == "Feature":
                            direct_features.append(gj)
                    if "text" in parsed:
                        return str(parsed["text"])
            except (json.JSONDecodeError, AttributeError):
                pass
            return val

        sub_text = _raw_injection + "\n\n".join(
            f"[{agent.upper()} RESULTS]:\n{_unwrap(result)}"
            for agent, result in sub_results.items()
            if result and result.strip()
        )

        combined_check = f"{sub_text} {user_query}"

        # Heuristic: skip LLM if no geographic signal (unless we have raw injection or direct features)
        if not _raw_injection and not _COORD_HINT_RE.search(combined_check):
            if direct_features:
                output = AgentOutput(agent_name=self.name, answer="", confidence=0.8)
                output.state["geojson"] = {"type": "FeatureCollection", "features": direct_features}
                return output
            output = AgentOutput(agent_name=self.name, answer="", confidence=0.5)
            output.state["geojson"] = None
            return output

        llm = build_llm(get_agent_model_config(self.name)).bind_tools(_MAP_TOOLS)

        map_input = (
            f"{sub_text}\n\nOriginal user question: {user_query}"
            if sub_text
            else user_query
        )
        messages = [SystemMessage(content=self._system_prompt), HumanMessage(content=map_input)]

        _call_cache: dict[tuple[str, str], str] = {}

        for _ in range(self.max_iterations):
            response: AIMessage = await llm.ainvoke(messages)
            messages.append(response)

            if not getattr(response, "tool_calls", None):
                break

            for tc in response.tool_calls:
                tool_fn = _TOOL_MAP.get(tc["name"])
                if tool_fn is None:
                    result = f"Unknown tool: {tc['name']}"
                else:
                    cache_key = (tc["name"], json.dumps(tc["args"], sort_keys=True))
                    if cache_key in _call_cache:
                        result = _call_cache[cache_key]
                    else:
                        try:
                            result = await tool_fn.ainvoke(tc["args"])
                        except Exception as exc:
                            result = f"Tool error: {exc}"
                        _call_cache[cache_key] = str(result)
                messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

        result_content = messages[-1].content if messages else ""

        geojson_data: dict[str, Any] | None = None
        summary = "Geographic data processed."

        if result_content:
            try:
                parsed = json.loads(result_content)
                if isinstance(parsed, dict):
                    geojson_data = parsed.get("geojson") or None
                    summary = parsed.get("summary", summary)
            except (json.JSONDecodeError, ValueError):
                match = re.search(r'\{[^{}]*"geojson"[^{}]*\}', result_content, re.DOTALL)
                if match:
                    try:
                        parsed = json.loads(match.group())
                        if isinstance(parsed, dict):
                            geojson_data = parsed.get("geojson") or None
                            summary = parsed.get("summary", summary)
                    except (json.JSONDecodeError, ValueError):
                        pass

        # Merge with any directly-embedded features
        if direct_features:
            existing = (geojson_data or {}).get("features", []) if geojson_data else []
            merged = existing + direct_features
            if merged:
                geojson_data = {"type": "FeatureCollection", "features": merged}

        output = AgentOutput(agent_name=self.name, answer=summary, confidence=0.85)
        output.state["geojson"] = geojson_data
        return output

    def make_node(self) -> Callable[[OrchestratorState], Coroutine[Any, Any, dict]]:
        """Return an async node function that runs this agent for GeoJSON generation."""
        agent = self

        async def mapviz_node(state: OrchestratorState) -> dict:
            sub_text: dict[str, str] = {
                k: (v.get("answer") or "") if isinstance(v, dict) else str(v)
                for k, v in (state.get("sub_results") or {}).items()
            }
            inp = AgentInput(
                query=state["query"],
                session_id=state["session_id"],
                context={
                    "sub_results": sub_text,
                    "dataviz": state.get("dataviz"),
                    "geojson": state.get("geojson"),
                },
            )
            try:
                output = await agent.run(inp)
                gj = output.state.get("geojson")
            except Exception:
                logger.exception("mapviz_node: agent raised")
                gj = None
            return {"geojson": gj} if gj is not None else {}

        return mapviz_node
