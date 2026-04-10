"""
Smart Dispatcher – metadata-registry-based agent routing.

This agent sits **after** :mod:`intent_parser` and **before** the data-source
connectors in the pipeline.  It replaces the generic LLM-based ``router_node``
when enabled (``SMART_DISPATCHER_ENABLED=true``).

Architecture
------------
Instead of asking an LLM "which agents should I call?", the Smart Dispatcher
applies a transparent, deterministic scoring algorithm against a
:mod:`source_registry` — a catalogue where every data-source connector
declares its capabilities, topics, entity types, and geographic scope.

Scoring formula (per source entry)
-----------------------------------
+3   for each *required capability* present in the source
+2   for each *intent entity* that matches a source topic or entity_type
+2   if the source's geo_scope covers the intent's geo_zone
+1   semantic similarity score (cosine similarity against embedded description)

Sources with a total score >= ``DISPATCH_THRESHOLD`` (default 3) are selected.
If no source reaches the threshold, the highest-scoring source is kept as a
fallback so the pipeline never returns an empty agent list.

Intent-type -> required capabilities mapping
--------------------------------------------
intent_type           required capabilities
─────────────────     ─────────────────────────────────────────────────
locate                geocoding, coordinates
analyze_proximity     proximity, buffer, spatial_query
analyze_area          area, intersection, spatial_query
compare               relationship, semantic_search
route                 routing, distance
visualize             (no hard requirement — all sources eligible)
statistics            spatial_query, semantic_search, open_data
explain               relationship, ontology, semantic_search
search                semantic_search, entity_search, open_data

When ``parsed_intent`` is absent from state (e.g. intent_parser disabled),
the dispatcher falls back to activating all enabled connectors.

How to enable
-------------
Set ``SMART_DISPATCHER_ENABLED=true`` in ``.env`` (enabled by default).
When disabled, the LLM-based ``router_node`` is used instead.
"""
from __future__ import annotations

import logging

from app.agent.core.source_registry import (
    SourceEntry,
    get_registry,
    semantic_search_sources,
)
from app.agent.core.state import AgentState, ParsedIntent

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

DISPATCH_THRESHOLD = 3
"""Minimum score for a source to be selected."""

# ── Intent-type → required capabilities ───────────────────────────────────────

_INTENT_CAPABILITIES: dict[str, list[str]] = {
    "locate":            ["geocoding", "coordinates"],
    "analyze_proximity": ["proximity", "buffer", "spatial_query"],
    "analyze_area":      ["area", "intersection", "spatial_query"],
    "compare":           ["relationship", "semantic_search"],
    "route":             ["routing", "distance"],
    "visualize":         [],   # no hard requirement — all sources eligible
    "statistics":        ["spatial_query", "semantic_search", "open_data"],
    "explain":           ["relationship", "ontology", "semantic_search"],
    "search":            ["semantic_search", "entity_search", "open_data"],
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _covers_geo_scope(source: SourceEntry, geo_zone_raw: str | None) -> bool:
    """Return True if *source* is applicable to the geographic zone in the intent.

    Logic:
    - A source with geo_scope=None is universally applicable.
    - If the intent carries no geo_zone, all sources are eligible.
    - Otherwise check for a case-insensitive substring match between the
      source's declared scope and the intent's raw geo_zone string.
    """
    if source.geo_scope is None:
        return True
    if not geo_zone_raw:
        return True
    return source.geo_scope.lower() in geo_zone_raw.lower() or geo_zone_raw.lower() in source.geo_scope.lower()


def _score_source(
    source: SourceEntry,
    intent: ParsedIntent,
    semantic_scores: dict[str, float],
) -> float:
    """Compute the dispatch score for *source* against *intent*."""
    score: float = 0.0

    # +3 per required capability present in source
    required_caps = _INTENT_CAPABILITIES.get(intent.intent_type, [])
    for cap in required_caps:
        if cap in source.capabilities:
            score += 3.0

    # +2 per entity that fuzzy-matches a topic or entity_type
    all_tags = {t.lower() for t in source.topics + source.entity_types}
    for entity in intent.entities:
        entity_lower = entity.lower()
        if any(entity_lower in tag or tag in entity_lower for tag in all_tags):
            score += 2.0

    # +2 if geo_scope covers the intent's geo_zone
    geo_raw = intent.geo_zone.raw if intent.geo_zone else None
    if _covers_geo_scope(source, geo_raw):
        score += 2.0

    # +1 semantic similarity score (already in [0.0, 1.0])
    score += semantic_scores.get(source.id, 0.0)

    return score


# ── Core dispatch logic ────────────────────────────────────────────────────────

async def dispatch(
    intent: ParsedIntent,
    active_agents: list[str],
) -> list[str]:
    """Compute the ordered list of connector keys to invoke for *intent*.

    Parameters
    ----------
    intent:
        Structured intent produced by the Intent Parser.
    active_agents:
        Agent keys enabled in the current configuration.

    Returns
    -------
    list[str]
        Ordered list of unique connector keys (subset of *active_agents*).
        Never empty.
    """
    # Restrict registry to sources whose connector is currently active
    eligible = [s for s in get_registry() if s.connector in active_agents]
    if not eligible:
        logger.warning("SmartDispatcher: no registry entries match active agents %s.", active_agents)
        return active_agents[:1]

    # Semantic query: use intent.intention or entities as fallback
    semantic_query = intent.intention or " ".join(intent.entities) or "geographic query"
    semantic_scores = await semantic_search_sources(semantic_query)

    # Score every eligible source
    scored: dict[str, float] = {
        source.id: _score_source(source, intent, semantic_scores)
        for source in eligible
    }
    logger.debug("SmartDispatcher scores: %s", {k: round(v, 2) for k, v in scored.items()})

    # Select sources above threshold
    selected_ids = [sid for sid, s in scored.items() if s >= DISPATCH_THRESHOLD]

    # Fallback: always keep at least the highest-scoring source
    if not selected_ids:
        best = max(scored, key=scored.get)
        selected_ids = [best]
        logger.debug("SmartDispatcher: below threshold, falling back to '%s'.", best)

    # Sort by score descending, resolve ids → connector keys (deduped)
    selected_sorted = sorted(set(selected_ids), key=lambda sid: scored[sid], reverse=True)
    seen: set[str] = set()
    connector_keys: list[str] = []
    for sid in selected_sorted:
        entry = next((s for s in eligible if s.id == sid), None)
        if entry and entry.connector not in seen:
            connector_keys.append(entry.connector)
            seen.add(entry.connector)

    # Final intersection with active_agents to avoid routing to a disabled agent
    result = [k for k in connector_keys if k in active_agents]
    return result if result else active_agents[:1]


# ── Node ──────────────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """Smart dispatch node — compute agents_to_call from parsed_intent."""
    # Deferred import to avoid circular dependency at module level
    from app.agent.core.orchestrator import get_active_agents, _AGENT_NODES  # noqa: PLC0415

    active = get_active_agents()

    # Honour explicit user selection when provided
    user_selected: list[str] = state.get("selected_agents") or []
    if user_selected:
        active = [a for a in active if a in user_selected and a in _AGENT_NODES] or active

    parsed_intent: ParsedIntent | None = state.get("parsed_intent")

    if parsed_intent is None:
        # Intent parser disabled or upstream failure — use all connectors
        logger.debug("SmartDispatcher: no parsed_intent, activating all connectors.")
        agents_to_call = active
    else:
        agents_to_call = await dispatch(parsed_intent, active)

    logger.info(
        "SmartDispatcher → agents_to_call=%s (intent_type=%s)",
        agents_to_call,
        parsed_intent.intent_type if parsed_intent else "n/a",
    )

    return {
        "agents_to_call": agents_to_call,
        "sub_results": {},
        "geojson": None,
        "dataviz": None,
        "output_decision": None,
    }
