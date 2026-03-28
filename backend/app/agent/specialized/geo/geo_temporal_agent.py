"""
Geo Temporal Agent – spatio-temporal evolution analysis.

Specialises in:
  • Detecting trends and changes in geographic data over time
  • Computing movement velocity and direction from timestamped positions
  • Identifying temporal patterns (seasonality, acceleration, clustering in time)
  • Generating temporal summaries and change statistics

Exposed as a single async function `run` usable as a LangGraph node or called
directly by the geo_agent orchestrator.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agent.model_config import build_llm, get_agent_model_config, get_agent_max_iterations
from app.agent.state import AgentState
from libs.geo.geodesy import bearing, haversine
from libs.geo.temporal import parse_ts

_SYSTEM_PROMPT = """You are the Temporal Analysis Agent of the PangIA GeoIA platform.
Your role is to analyse how geographic phenomena evolve over time.

## Capabilities
- `analyse_movement`: Compute velocity and direction from a sequence of timestamped positions.
- `detect_temporal_pattern`: Identify trends and patterns in a time-series of geographic measurements.
- `compute_displacement`: Calculate the net displacement between first and last positions.
- `summarise_time_series`: Generate summary statistics for a temporal dataset.

## Guidelines
- Always include timestamps in your analysis output.
- Express velocities in km/h or m/s and directions in degrees (0°=North, 90°=East).
- Identify periods of acceleration, deceleration, or stasis.
- Detect seasonal or periodic patterns when temporal data spans multiple periods.
- Answer in the same language as the user's question.
- **Never** include map embed code, Mapbox snippets, Leaflet HTML, access tokens, or
  rendering instructions in your answer – maps are rendered by the frontend.
"""


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
def analyse_movement(positions_json: str) -> str:
    """Compute velocity and bearing from a sequence of timestamped geographic positions.

    Args:
        positions_json: JSON array of position objects with 'timestamp' (ISO 8601 string),
            'latitude', 'longitude', and optionally 'name'.
            Example: '[{"timestamp":"2024-01-01T00:00:00Z","latitude":48.85,"longitude":2.35}]'
    Returns a JSON object with per-segment and overall movement statistics.
    """
    try:
        positions: list[dict[str, Any]] = json.loads(positions_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if not isinstance(positions, list) or len(positions) < 2:
        return json.dumps({"error": "Provide at least 2 timestamped positions."})

    parsed = []
    for i, p in enumerate(positions):
        try:
            ts = parse_ts(str(p.get("timestamp", "")))
            if ts is None:
                return json.dumps({"error": f"Cannot parse timestamp at index {i}: {p.get('timestamp')!r}"})
            parsed.append({
                "ts": ts,
                "lat": float(p["latitude"]),
                "lon": float(p["longitude"]),
                "name": p.get("name", f"pos_{i}"),
                "timestamp": p["timestamp"],
            })
        except (KeyError, ValueError, TypeError) as exc:
            return json.dumps({"error": f"Invalid position at index {i}: {exc}"})

    parsed.sort(key=lambda x: x["ts"])
    segments = []
    total_dist = 0.0
    speeds = []

    for i in range(len(parsed) - 1):
        a, b = parsed[i], parsed[i + 1]
        dt_s = b["ts"] - a["ts"]
        if dt_s <= 0:
            continue
        dist_m = haversine(a["lat"], a["lon"], b["lat"], b["lon"])
        speed_ms = dist_m / dt_s
        speed_kmh = speed_ms * 3.6
        bear = bearing(a["lat"], a["lon"], b["lat"], b["lon"])
        total_dist += dist_m
        speeds.append(speed_kmh)
        segments.append({
            "from": a["name"],
            "to": b["name"],
            "from_timestamp": a["timestamp"],
            "to_timestamp": b["timestamp"],
            "duration_s": round(dt_s, 1),
            "distance_km": round(dist_m / 1000, 4),
            "speed_kmh": round(speed_kmh, 2),
            "bearing_degrees": round(bear, 1),
        })

    total_time_s = parsed[-1]["ts"] - parsed[0]["ts"]
    avg_speed = sum(speeds) / len(speeds) if speeds else 0.0

    return json.dumps({
        "segments": segments,
        "summary": {
            "total_distance_km": round(total_dist / 1000, 4),
            "total_duration_s": round(total_time_s, 1),
            "total_duration_h": round(total_time_s / 3600, 3),
            "average_speed_kmh": round(avg_speed, 2),
            "max_speed_kmh": round(max(speeds), 2) if speeds else 0.0,
            "min_speed_kmh": round(min(speeds), 2) if speeds else 0.0,
            "start_timestamp": parsed[0]["timestamp"],
            "end_timestamp": parsed[-1]["timestamp"],
        },
    })


@tool
def compute_displacement(positions_json: str) -> str:
    """Calculate the net displacement between the first and last positions in a sequence.

    Args:
        positions_json: JSON array of position objects with 'timestamp', 'latitude', 'longitude'.
    Returns the straight-line displacement distance, bearing, and net movement direction.
    """
    try:
        positions: list[dict[str, Any]] = json.loads(positions_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if not isinstance(positions, list) or len(positions) < 2:
        return json.dumps({"error": "Provide at least 2 positions."})

    parsed = []
    for i, p in enumerate(positions):
        try:
            ts = parse_ts(str(p.get("timestamp", "")))
            parsed.append({
                "ts": ts or 0.0,
                "lat": float(p["latitude"]),
                "lon": float(p["longitude"]),
                "name": p.get("name", f"pos_{i}"),
                "timestamp": p.get("timestamp", ""),
            })
        except (KeyError, ValueError, TypeError) as exc:
            return json.dumps({"error": f"Invalid position at index {i}: {exc}"})

    if parsed[0]["ts"] and parsed[-1]["ts"]:
        parsed.sort(key=lambda x: x["ts"])

    first, last = parsed[0], parsed[-1]
    dist_m = haversine(first["lat"], first["lon"], last["lat"], last["lon"])
    bear = bearing(first["lat"], first["lon"], last["lat"], last["lon"])

    compass = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    compass_dir = compass[round(bear / 45) % 8]

    return json.dumps({
        "start": {"name": first["name"], "latitude": first["lat"], "longitude": first["lon"], "timestamp": first["timestamp"]},
        "end": {"name": last["name"], "latitude": last["lat"], "longitude": last["lon"], "timestamp": last["timestamp"]},
        "displacement": {
            "distance_km": round(dist_m / 1000, 4),
            "bearing_degrees": round(bear, 1),
            "compass_direction": compass_dir,
        },
        "point_count": len(parsed),
    })


@tool
def detect_temporal_pattern(values_json: str) -> str:
    """Identify trends and patterns in a time-series of numeric geographic measurements.

    Args:
        values_json: JSON array of objects with 'timestamp' (ISO 8601) and 'value' (float).
            Example: '[{"timestamp":"2024-01-01","value":42.5}, ...]'
    Returns a JSON object with trend analysis and summary statistics.
    """
    try:
        data: list[dict[str, Any]] = json.loads(values_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if not isinstance(data, list) or len(data) < 2:
        return json.dumps({"error": "Provide at least 2 data points."})

    parsed = []
    for i, item in enumerate(data):
        try:
            ts = parse_ts(str(item.get("timestamp", "")))
            if ts is None:
                return json.dumps({"error": f"Cannot parse timestamp at index {i}: {item.get('timestamp')!r}"})
            parsed.append({"ts": ts, "value": float(item["value"]), "timestamp": item["timestamp"]})
        except (KeyError, ValueError, TypeError) as exc:
            return json.dumps({"error": f"Invalid item at index {i}: {exc}"})

    parsed.sort(key=lambda x: x["ts"])
    values = [p["value"] for p in parsed]

    # Linear trend: slope via least-squares
    n = len(values)
    ts_vals = [p["ts"] for p in parsed]
    ts_mean = sum(ts_vals) / n
    v_mean = sum(values) / n
    num = sum((ts_vals[i] - ts_mean) * (values[i] - v_mean) for i in range(n))
    den = sum((ts_vals[i] - ts_mean) ** 2 for i in range(n))
    slope = num / den if den != 0 else 0.0

    # Count increases and decreases
    increases = sum(1 for i in range(n - 1) if values[i + 1] > values[i])
    decreases = sum(1 for i in range(n - 1) if values[i + 1] < values[i])

    if slope > 0 and increases > decreases:
        trend = "increasing"
    elif slope < 0 and decreases > increases:
        trend = "decreasing"
    else:
        trend = "stable"

    return json.dumps({
        "point_count": n,
        "start_timestamp": parsed[0]["timestamp"],
        "end_timestamp": parsed[-1]["timestamp"],
        "values": {
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "mean": round(v_mean, 4),
            "range": round(max(values) - min(values), 4),
        },
        "trend": {
            "direction": trend,
            "slope_per_day": round(slope * 86400, 6),
            "increases": increases,
            "decreases": decreases,
            "stable_steps": n - 1 - increases - decreases,
        },
    })


@tool
def summarise_time_series(events_json: str) -> str:
    """Generate a temporal summary for a dataset of geographic events.

    Args:
        events_json: JSON array of event objects with 'timestamp' (ISO 8601) and
            optionally 'latitude', 'longitude', 'name'.
    Returns temporal statistics: span, event rate, busiest/quietest periods.
    """
    try:
        events: list[dict[str, Any]] = json.loads(events_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}"})

    if not isinstance(events, list) or not events:
        return json.dumps({"error": "Provide a non-empty JSON array of events."})

    timestamps = []
    for i, ev in enumerate(events):
        ts = parse_ts(str(ev.get("timestamp", "")))
        if ts is not None:
            timestamps.append(ts)

    if not timestamps:
        return json.dumps({"error": "No parseable timestamps found."})

    timestamps.sort()
    span_s = timestamps[-1] - timestamps[0]
    span_days = span_s / 86400

    # Group by year-month
    monthly: dict[str, int] = {}
    for ts in timestamps:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        key = dt.strftime("%Y-%m")
        monthly[key] = monthly.get(key, 0) + 1

    busiest = max(monthly, key=lambda k: monthly[k]) if monthly else None
    quietest = min(monthly, key=lambda k: monthly[k]) if monthly else None

    return json.dumps({
        "event_count": len(timestamps),
        "first_event": datetime.fromtimestamp(timestamps[0], tz=timezone.utc).isoformat(),
        "last_event": datetime.fromtimestamp(timestamps[-1], tz=timezone.utc).isoformat(),
        "span_days": round(span_days, 1),
        "events_per_day": round(len(timestamps) / span_days, 4) if span_days > 0 else None,
        "monthly_distribution": monthly,
        "busiest_month": busiest,
        "quietest_month": quietest,
    })


GEO_TEMPORAL_TOOLS = [
    analyse_movement,
    compute_displacement,
    detect_temporal_pattern,
    summarise_time_series,
]
_TOOL_MAP = {t.name: t for t in GEO_TEMPORAL_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the Geo Temporal sub-agent."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"geo_temporal": f"[geo_temporal agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    llm = build_llm(
        get_agent_model_config("geo_temporal_agent"), streaming=True
    ).bind_tools(GEO_TEMPORAL_TOOLS)

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user_query)]

    for _ in range(get_agent_max_iterations("geo_temporal_agent")):
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
        messages[-1].content if messages else "geo_temporal agent returned no result."
    )
    return {"sub_results": {"geo_temporal": str(result_content)}}
