"""
PostGIS sub-agent.

Specialises in spatial SQL queries against a PostgreSQL/PostGIS database.
Exposed as a single async function `run` usable as a LangGraph node.
"""
import json
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agent.model_config import build_llm, get_agent_model_config, get_agent_max_iterations
from app.agent.state import AgentState
from app.db.postgis_client import run_spatial_query
from app.db.themes import get_active_theme

_BASE_SYSTEM_PROMPT = """You are the PostGIS Spatial SQL Agent of the PangIA GeoIA platform.
Your job is to answer geographic and spatial questions by querying a PostGIS-enabled
PostgreSQL database using spatial SQL functions (ST_Contains, ST_Distance,
ST_Intersects, ST_Within, ST_Area, etc.).

## Database schema

{schema}

## Guidelines
- Write standard PostGIS SQL; always use parameterised queries where possible.
- Only issue SELECT queries; mutations (INSERT/UPDATE/DELETE) are blocked.
- Explain the spatial reasoning behind your query.
- Format numeric results with appropriate units (metres, km², etc.).
- If the query returns no rows, say so clearly.
- **Geometry columns**: when a query returns a geometry column (PostGIS type),
  always cast it to readable text in the SELECT list using one of:
    • `ST_AsGeoJSON(geom) AS geom`  – preferred, returns GeoJSON geometry
    • `ST_AsText(geom) AS geom`     – returns WKT (e.g. POINT(lon lat))
  This allows downstream agents to display the geometry on a map without
  extra geocoding.
{extra_guidelines}"""


def _build_system_prompt() -> str:
    theme = get_active_theme()
    schema = theme.postgis_schema_prompt.strip()
    guidelines = theme.postgis_guidelines.strip()
    extra = f"\n## Theme-specific guidelines\n{guidelines}" if guidelines else ""
    return _BASE_SYSTEM_PROMPT.format(
        schema=schema or "(no schema defined for this theme)",
        extra_guidelines=extra,
    )


# ─── Geometry helpers ──────────────────────────────────────────────────────────

# Matches WKT geometry type prefix (POINT, LINESTRING, POLYGON, MULTI*)
_WKT_GEOM_RE = re.compile(
    r"^(POINT|LINESTRING|POLYGON|MULTIPOINT|MULTILINESTRING|MULTIPOLYGON)"
    r"(?:\s*Z\s*|\s*M\s*|\s*ZM\s*)?\s*\((.+)\)$",
    re.IGNORECASE | re.DOTALL,
)
# Column names that typically hold geometry/geography values
_GEOM_COL_RE = re.compile(
    r"^(?:geom(?:etry)?|the_geom|geom_wkt|geom_json|wkt|shape|geo)$",
    re.IGNORECASE,
)
# Column names for latitude / longitude
_LAT_COL_RE = re.compile(r"^lat(?:itude)?$", re.IGNORECASE)
_LON_COL_RE = re.compile(r"^lo?n(?:g(?:itude)?)?$", re.IGNORECASE)

# GeoJSON geometry types
_GEOJSON_GEOM_TYPES = frozenset(
    ["Point", "LineString", "Polygon", "MultiPoint", "MultiLineString", "MultiPolygon", "GeometryCollection"]
)


def _parse_wkt_coords_flat(s: str) -> list[list[float]]:
    """Parse a flat WKT coordinate string ('1.0 2.0, 3.0 4.0') into [[lon, lat], ...].

    Pairs that cannot be parsed as floats are silently skipped so that a single
    malformed coordinate does not discard the entire geometry.
    """
    result: list[list[float]] = []
    for pair in s.split(","):
        parts = pair.strip().split()
        if len(parts) >= 2:
            try:
                result.append([float(parts[0]), float(parts[1])])
            except ValueError:
                pass
    return result


def _extract_paren_groups(s: str) -> list[str]:
    """Return the contents of each top-level parenthesised group in *s*.

    e.g. '((0 0, 1 0),(2 2, 3 2))' → ['(0 0, 1 0)', '(2 2, 3 2)']
    Handles arbitrary nesting depth correctly.
    """
    groups: list[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(s):
        if ch == "(":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and start >= 0:
                groups.append(s[start : i + 1])
    return groups


def _wkt_to_geojson_geometry(wkt: str) -> dict[str, Any] | None:
    """Convert a WKT string to a GeoJSON geometry dict. Returns None if parsing fails."""
    m = _WKT_GEOM_RE.match(wkt.strip())
    if not m:
        return None
    geom_type = m.group(1).upper()
    inner = m.group(2).strip()
    try:
        if geom_type == "POINT":
            parts = inner.split()
            if len(parts) >= 2:
                return {"type": "Point", "coordinates": [float(parts[0]), float(parts[1])]}

        elif geom_type == "LINESTRING":
            coords = _parse_wkt_coords_flat(inner)
            if coords:
                return {"type": "LineString", "coordinates": coords}

        elif geom_type == "POLYGON":
            rings = re.findall(r"\(([^()]+)\)", inner)
            if rings:
                return {"type": "Polygon", "coordinates": [_parse_wkt_coords_flat(r) for r in rings]}

        elif geom_type == "MULTIPOINT":
            ring_matches = re.findall(r"\(([^()]+)\)", inner)
            if ring_matches:
                pts = [_parse_wkt_coords_flat(p) for p in ring_matches]
                flat = [c[0] for c in pts if c]
            else:
                flat = _parse_wkt_coords_flat(inner)
            if flat:
                return {"type": "MultiPoint", "coordinates": flat}

        elif geom_type == "MULTILINESTRING":
            lines = re.findall(r"\(([^()]+)\)", inner)
            if lines:
                return {"type": "MultiLineString", "coordinates": [_parse_wkt_coords_flat(ln) for ln in lines]}

        elif geom_type == "MULTIPOLYGON":
            # Each polygon group is wrapped in an extra pair of parens, e.g.:
            # ((ring1),(ring2)),((ring3))
            # Use a depth-aware extractor to handle arbitrary nesting.
            polys = []
            for poly_group in _extract_paren_groups(inner):
                # poly_group is e.g. "((0 0,1 0,1 1,0 0),(0.1 0.1,0.2 0.1,0.2 0.2,0.1 0.1))"
                rings_raw = re.findall(r"\(([^()]+)\)", poly_group)
                if rings_raw:
                    polys.append([_parse_wkt_coords_flat(r) for r in rings_raw])
            if polys:
                return {"type": "MultiPolygon", "coordinates": polys}

    except (ValueError, IndexError):
        pass
    return None


def _build_geojson_from_result(result_json: str) -> dict[str, Any] | None:
    """Attempt to build a GeoJSON FeatureCollection from a PostGIS query JSON result.

    Handles:
    - Columns with WKT geometry values (POINT, LINESTRING, etc.)
    - Columns with GeoJSON geometry string values
    - lat/lon column pairs
    """
    try:
        records = json.loads(result_json)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(records, list) or not records:
        return None
    first = records[0]
    if not isinstance(first, dict):
        return None

    cols = list(first.keys())

    # Identify geometry, lat, and lon columns by name
    geom_col: str | None = next((c for c in cols if _GEOM_COL_RE.match(c)), None)
    lat_col: str | None = next((c for c in cols if _LAT_COL_RE.match(c)), None)
    lon_col: str | None = next((c for c in cols if _LON_COL_RE.match(c)), None)

    # If no named geometry column, try detecting by value pattern in the first row
    if geom_col is None:
        for col in cols:
            val = first.get(col)
            if isinstance(val, str) and _WKT_GEOM_RE.match(val.strip()):
                geom_col = col
                break
        if geom_col is None:
            for col in cols:
                val = first.get(col)
                if isinstance(val, str):
                    try:
                        geo = json.loads(val)
                        if isinstance(geo, dict) and geo.get("type") in _GEOJSON_GEOM_TYPES:
                            geom_col = col
                            break
                    except (json.JSONDecodeError, ValueError):
                        pass

    if geom_col is None and not (lat_col and lon_col):
        return None

    features: list[dict[str, Any]] = []
    for row in records:
        if not isinstance(row, dict):
            continue

        geometry: dict[str, Any] | None = None

        if geom_col:
            val = row.get(geom_col)
            if isinstance(val, str):
                val = val.strip()
                # Try WKT first
                geometry = _wkt_to_geojson_geometry(val)
                if geometry is None:
                    # Try GeoJSON geometry string
                    try:
                        geo = json.loads(val)
                        if isinstance(geo, dict) and geo.get("type") in _GEOJSON_GEOM_TYPES:
                            geometry = geo
                    except (json.JSONDecodeError, ValueError):
                        pass

        if geometry is None and lat_col and lon_col:
            try:
                lat = float(row[lat_col])
                lon = float(row[lon_col])
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    geometry = {"type": "Point", "coordinates": [lon, lat]}
            except (TypeError, ValueError):
                pass

        if geometry is None:
            continue

        skip_keys = {k for k in (geom_col, lat_col, lon_col) if k}
        properties = {k: v for k, v in row.items() if k not in skip_keys and v is not None}
        features.append({"type": "Feature", "geometry": geometry, "properties": properties})

    if not features:
        return None
    return {"type": "FeatureCollection", "features": features}


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
async def run_postgis_query(sql: str) -> str:
    """Execute a read-only spatial SQL query against the PostGIS database.
    Only SELECT statements are permitted; mutations are blocked at the driver level."""
    try:
        return await run_spatial_query(sql)
    except Exception as exc:
        return f"PostGIS query failed: {exc}"


POSTGIS_TOOLS = [run_postgis_query]
_TOOL_MAP = {t.name: t for t in POSTGIS_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the PostGIS sub-agent ReAct loop."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"postgis": f"[PostGIS agent unavailable: {exc}]"}, "postgis_geojson": None}


async def _run(state: AgentState) -> dict:
    llm = build_llm(get_agent_model_config("postgis_agent"), streaming=True).bind_tools(POSTGIS_TOOLS)

    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    messages = [SystemMessage(content=_build_system_prompt()), HumanMessage(content=user_query)]

    for _ in range(get_agent_max_iterations("postgis_agent")):
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
            messages.append(
                ToolMessage(content=str(result), tool_call_id=tc["id"])
            )

    result_content = (
        messages[-1].content if messages else "PostGIS agent returned no result."
    )

    # Extract geometry from all tool results and build a GeoJSON FeatureCollection
    postgis_geojson: dict[str, Any] | None = None
    for msg in messages:
        if isinstance(msg, ToolMessage):
            geojson = _build_geojson_from_result(msg.content)
            if geojson and geojson.get("features"):
                if postgis_geojson is None:
                    postgis_geojson = geojson
                else:
                    # Merge features from multiple tool calls
                    postgis_geojson["features"].extend(geojson["features"])

    return {
        "sub_results": {"postgis": str(result_content)},
        "postgis_geojson": postgis_geojson,
    }
