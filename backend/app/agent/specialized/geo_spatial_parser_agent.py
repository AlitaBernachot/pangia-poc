"""
Geo Spatial Parser Agent – natural language spatial understanding.

Specialises in:
  • Parsing spatial relationships from natural language (e.g. "north of", "within 10 km")
  • Extracting geographic entities (place names, regions, coordinates) from free text
  • Identifying spatial predicates (contains, intersects, within, near, etc.)
  • Structuring unstructured geographic queries into formal spatial expressions

Exposed as a single async function `run` usable as a LangGraph node or called
directly by the geo_agent orchestrator.
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agent.model_config import build_llm, get_agent_model_config, get_agent_max_iterations
from app.agent.state import AgentState

_SYSTEM_PROMPT = """You are the Spatial Language Parser Agent of the PangIA GeoIA platform.
Your role is to analyse natural language text and extract structured spatial information.

## Capabilities
- `extract_spatial_entities`: Extract place names, regions, and geographic references from text.
- `parse_spatial_relationship`: Identify and formalise spatial relationships (near, within, north of, etc.).
- `extract_coordinates_from_text`: Find and parse coordinate expressions in various formats.

## Guidelines
- Extract ALL geographic entities mentioned, even implicit ones.
- Identify the spatial predicate (near, within, contains, intersects, north/south/east/west of, etc.).
- Return structured JSON so downstream agents can act on the results.
- Distinguish between named places (Paris), administrative regions (Île-de-France), and
  geometric expressions (within a 5 km radius).
- Answer in the same language as the user's question.
"""


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
def extract_spatial_entities(text: str) -> str:
    """Extract geographic place names, regions, and spatial references from free text.

    Uses pattern matching and heuristics to identify location mentions.
    Returns a JSON object with lists of found entities by category.
    """
    # Coordinate patterns
    coord_patterns = [
        r"(-?\d{1,3}\.\d+)\s*[,;]\s*(-?\d{1,3}\.\d+)",
        r"(\d{1,3})°\s*(\d{1,2})['′]\s*(\d{1,2}(?:\.\d+)?)[\"″]?\s*([NS])\s+"
        r"(\d{1,3})°\s*(\d{1,2})['′]\s*(\d{1,2}(?:\.\d+)?)[\"″]?\s*([EW])",
        r"lat(?:itude)?\s*[=:]\s*(-?\d+\.?\d*)",
        r"lon(?:gitude)?\s*[=:]\s*(-?\d+\.?\d*)",
    ]

    # Spatial relationship keywords
    spatial_keywords = [
        r"\bnear\b", r"\bwithin\b", r"\binside\b", r"\boutside\b",
        r"\bnorth\s+of\b", r"\bsouth\s+of\b", r"\beast\s+of\b", r"\bwest\s+of\b",
        r"\bcontains\b", r"\bintersects\b", r"\badjacent\s+to\b",
        r"\bbetween\b", r"\balong\b", r"\bacross\b",
        r"\bprès\s+de\b", r"\bdans\b", r"\bau\s+nord\s+de\b", r"\bau\s+sud\s+de\b",
        r"\bà\s+l[''']est\s+de\b", r"\bà\s+l[''']ouest\s+de\b",
    ]

    # Distance patterns
    distance_patterns = [
        r"(\d+(?:\.\d+)?)\s*(km|kilomet(?:re|er)s?|miles?|m\b|meters?|metres?)",
        r"within\s+(\d+(?:\.\d+)?)\s*(km|miles?|meters?|metres?)",
    ]

    found_coords = []
    for pat in coord_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            found_coords.append(m.group(0))

    found_spatial_rels = []
    for kw in spatial_keywords:
        for m in re.finditer(kw, text, re.IGNORECASE):
            context_start = max(0, m.start() - 30)
            context_end = min(len(text), m.end() + 50)
            found_spatial_rels.append(
                {
                    "keyword": m.group(0).strip(),
                    "context": text[context_start:context_end].strip(),
                }
            )

    found_distances = []
    for pat in distance_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            found_distances.append({"expression": m.group(0), "value": m.group(1), "unit": m.group(2)})

    return json.dumps(
        {
            "coordinates_found": found_coords,
            "spatial_relationships": found_spatial_rels,
            "distance_expressions": found_distances,
            "original_text": text[:500],
        }
    )


@tool
def parse_spatial_relationship(text: str) -> str:
    """Identify and formalise a spatial relationship expressed in natural language.

    Parses expressions like "within 5 km of Paris" or "north of the river"
    into a structured spatial predicate with its arguments.
    Returns a JSON object describing the spatial predicate.
    """
    predicates = {
        "within": ["within", "inside", "in", "dans", "à l'intérieur de"],
        "near": ["near", "close to", "around", "nearby", "près de", "autour de"],
        "north_of": ["north of", "au nord de"],
        "south_of": ["south of", "au sud de"],
        "east_of": ["east of", "à l'est de"],
        "west_of": ["west of", "à l'ouest de"],
        "contains": ["contains", "includes", "covering", "contient"],
        "intersects": ["intersects", "crosses", "intersecte"],
        "adjacent": ["adjacent to", "next to", "bordering", "adjacent à"],
        "between": ["between", "entre"],
        "along": ["along", "le long de"],
    }

    text_lower = text.lower()
    matched = []
    for predicate_type, keywords in predicates.items():
        for kw in keywords:
            if kw in text_lower:
                matched.append({"predicate": predicate_type, "matched_keyword": kw})

    # Extract distance if present
    dist_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(km|kilomet(?:re|er)s?|miles?|m\b|meters?|metres?)",
        text,
        re.IGNORECASE,
    )
    distance = None
    if dist_match:
        unit = dist_match.group(2).lower()
        value = float(dist_match.group(1))
        # Normalise to metres
        if unit.startswith("km") or unit.startswith("kilo"):
            value_m = value * 1000
        elif unit.startswith("mile"):
            value_m = value * 1609.344
        else:
            value_m = value
        distance = {"value": float(dist_match.group(1)), "unit": dist_match.group(2), "value_metres": value_m}

    return json.dumps(
        {
            "input_text": text,
            "predicates_found": matched,
            "distance": distance,
            "structured": {
                "type": matched[0]["predicate"] if matched else "unknown",
                "distance_metres": distance["value_metres"] if distance else None,
            },
        }
    )


@tool
def extract_coordinates_from_text(text: str) -> str:
    """Find and parse coordinate expressions in various formats from text.

    Supports decimal degrees (48.8566, 2.3522), DMS notation (48°51'N 2°21'E),
    and labelled coordinates (lat: 48.8566, lon: 2.3522).
    Returns a JSON array of extracted coordinate pairs.
    """
    results = []
    seen: set[tuple[float, float]] = set()

    # Decimal degrees: 48.8566, 2.3522 or lat=48.8566, lon=2.3522
    patterns = [
        (r"lat(?:itude)?\s*[=:]\s*(-?\d+\.?\d*)[,\s]+lon(?:gitude)?\s*[=:]\s*(-?\d+\.?\d*)", "labelled"),
        (r"\(\s*(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)\s*\)", "parenthesised"),
        (r"(-?\d{1,3}\.\d{3,})\s*,\s*(-?\d{1,3}\.\d{3,})", "decimal"),
    ]

    for pat, fmt in patterns:
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
            results.append({"latitude": lat, "longitude": lon, "format": fmt, "raw": m.group(0)})

    # DMS notation: 48°51'23"N 2°21'08"E
    dms_pattern = re.compile(
        r"(\d{1,3})°\s*(\d{1,2})['′]\s*(\d{1,2}(?:\.\d+)?)[\"″]?\s*([NS])\s+"
        r"(\d{1,3})°\s*(\d{1,2})['′]\s*(\d{1,2}(?:\.\d+)?)[\"″]?\s*([EW])",
        re.IGNORECASE,
    )
    for m in dms_pattern.finditer(text):
        lat = float(m.group(1)) + float(m.group(2)) / 60 + float(m.group(3)) / 3600
        if m.group(4).upper() == "S":
            lat = -lat
        lon = float(m.group(5)) + float(m.group(6)) / 60 + float(m.group(7)) / 3600
        if m.group(8).upper() == "W":
            lon = -lon
        key = (round(lat, 5), round(lon, 5))
        if key in seen:
            continue
        seen.add(key)
        results.append({"latitude": lat, "longitude": lon, "format": "DMS", "raw": m.group(0)})

    return json.dumps({"coordinates": results, "count": len(results)})


GEO_SPATIAL_PARSER_TOOLS = [
    extract_spatial_entities,
    parse_spatial_relationship,
    extract_coordinates_from_text,
]
_TOOL_MAP = {t.name: t for t in GEO_SPATIAL_PARSER_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the Geo Spatial Parser sub-agent."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"geo_spatial_parser": f"[geo_spatial_parser agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    llm = build_llm(
        get_agent_model_config("geo_spatial_parser_agent"), streaming=True
    ).bind_tools(GEO_SPATIAL_PARSER_TOOLS)

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]

    for _ in range(get_agent_max_iterations("geo_spatial_parser_agent")):
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
        messages[-1].content if messages else "geo_spatial_parser agent returned no result."
    )
    return {"sub_results": {"geo_spatial_parser": str(result_content)}}
