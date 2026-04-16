# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

import operator
from typing import Annotated, Any, Literal, Sequence, TypedDict

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


# ─── Parsed Intent ───────────────────────────────────────────────────────────


class GeoZone(BaseModel):
    """Spatial extent extracted from the user query."""

    place_name: str | None = None
    """Named place (city, country, region, address, …)."""

    bbox: list[float] | None = None
    """Bounding box as [minLon, minLat, maxLon, maxLat] when coordinates are known."""

    radius_km: float | None = None
    """Radius in km around the reference point when a buffer is implied."""

    raw: str | None = None
    """Raw spatial string as written by the user (kept for display / fallback)."""


class TemporalRange(BaseModel):
    """Temporal extent extracted from the user query."""

    start: str | None = None
    """ISO-8601 date/datetime or relative expression (e.g. 'last month')."""

    end: str | None = None
    """ISO-8601 date/datetime or relative expression."""

    raw: str | None = None
    """Raw temporal string as written by the user."""


class ParsedIntent(BaseModel):
    """Structured representation of the user's intent produced by IntentParser."""

    intent_type: Literal[
        "locate",             # Find where something is / geocode
        "analyze_proximity",  # What is near X?
        "analyze_area",       # Analyse a zone (stats, coverage, density…)
        "compare",            # Compare entities, zones, or time periods
        "route",              # Compute a path / itinerary
        "visualize",          # Explicit request for a map or chart
        "statistics",         # Aggregated counts, averages, trends
        "explain",            # Explain a concept, entity, or relationship
        "search",             # Open/keyword search without strong spatial component
    ] = "search"

    entities: list[str] = Field(default_factory=list)
    """Named entities extracted from the query (places, species, events, people…)."""

    geo_zone: GeoZone | None = None
    """Spatial extent of the request, if any."""

    temporal_range: TemporalRange | None = None
    """Time window of the request, if any."""

    intention: str = ""
    """Plain-language restatement of the user's goal (1–2 sentences)."""

    language: str = "fr"
    """Detected language of the query (ISO-639-1, e.g. 'fr', 'en')."""

    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    """Parsing confidence score in [0.0 – 1.0]."""


def _merge_dicts(a: dict, b: dict) -> dict:
    """Reducer that merges two dicts – used to accumulate sub-agent results."""
    return {**a, **b}


class AgentState(TypedDict):
    """Shared state threaded through the entire multi-agent graph."""

    # Full conversation history; new messages are *appended* (not replaced)
    messages: Annotated[Sequence[BaseMessage], operator.add]
    session_id: str

    # Agents explicitly requested by the user.  An empty list means
    # "no preference – let the router decide among all active agents".
    selected_agents: list[str]

    # Set by the router node: which sub-agents should be invoked
    agents_to_call: list[str]

    # Keyed by agent name ("neo4j" | "rdf" | "vector" | "postgis" | "map").
    # Results from parallel sub-agent branches are merged via _merge_dicts.
    sub_results: Annotated[dict[str, str], _merge_dicts]

    # GeoJSON FeatureCollection produced by the map agent (None if not invoked).
    geojson: dict[str, Any] | None

    # Structured visualisation data produced by the dataviz agent (None if not invoked).
    # Contains charts, KPI cards, and/or tables ready for the frontend to render.
    dataviz: dict[str, Any] | None

    # Decision produced by the humanoutput_agent about which visualisation
    # components to render.  Keys: "needs_map" (bool), "needs_dataviz" (bool).
    # None when the humanoutput_agent is disabled or has not run yet.
    output_decision: dict[str, Any] | None

    # Structured intent produced by the intent_parser (None when disabled or not yet run).
    parsed_intent: ParsedIntent | None

    # Dataset candidates returned by the datagouv_mcp_agent when multiple datasets match
    # the user's query and human disambiguation is required before fetching data.
    # Each entry is a dict with keys: id, title, description, url, organization.
    # None when no disambiguation is needed or when the agent has not run yet.
    pending_dataset_choice: list[dict] | None

    # Total number of datasets found by the search (may exceed the page shown).
    # None when no disambiguation is needed.
    pending_dataset_choice_total: int | None
