"""
Intent Parser – query understanding and structured intent extraction.

This agent is the **first node** in the PangIA pipeline.  It receives the raw
user message and produces a :class:`~app.agent.core.state.ParsedIntent` object
stored in ``state["parsed_intent"]``.

What it extracts
----------------
- **intent_type** – the dominant action category (locate, analyze_proximity,
  analyze_area, compare, route, visualize, statistics, explain, search).
- **entities** – named entities mentioned in the query (places, species, events,
  organisations, people, administrative divisions, …).
- **geo_zone** – spatial extent: named place, bounding box, or circular buffer
  radius implied by the query.
- **temporal_range** – explicit or relative time window (year, period, season, …).
- **intention** – a plain-language 1-to-2-sentence restatement of the goal,
  normalised and free of ambiguity, for downstream agents to use as context.
- **language** – detected ISO-639-1 language code of the query.
- **confidence** – overall parsing confidence in [0.0 – 1.0].

Decision strategy
-----------------
1. **Fast-path – empty query**: return a default ParsedIntent with low confidence.
2. **Heuristic pre-filter**: regex patterns tag obvious spatial / temporal /
   dataviz signals before the LLM call, used to steer the prompt.
3. **LLM structured output**: a lightweight LLM call with a strict JSON schema
   (via Pydantic structured output) extracts the full intent object.
4. **Error fallback**: any exception returns a minimal intent with
   ``intent_type="search"`` and ``confidence=0.0`` so the pipeline can continue.

When the agent is **disabled** (``INTENT_PARSER_ENABLED=false``) it is never
added to the graph and ``state["parsed_intent"]`` remains ``None``.
"""
from __future__ import annotations

import logging
import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.model_config import build_llm, get_agent_model_config
from app.agent.core.state import AgentState, GeoZone, ParsedIntent, TemporalRange

logger = logging.getLogger(__name__)

# ── Heuristic pre-filter patterns ────────────────────────────────────────────

_GEO_SIGNAL_RE = re.compile(
    r"\b(?:où|where|localise|localiz|geocod|carte|map|coordonnées?|coordinates?"
    r"|adresse|address|near|près de|autour de|dans un rayon|buffer|zone|région"
    r"|frontière|boundary|polygon|bbox|buffer|isochrone|itinéraire|route|chemin)\b",
    re.IGNORECASE,
)

_TEMPORAL_SIGNAL_RE = re.compile(
    r"\b(?:en \d{4}|depuis|from|between|entre|avant|before|après|after"
    r"|last|dernier|cette année|this year|période|period|date|année|month|mois"
    r"|siècle|century|récent|recent|evolution|tendance|trend|historique|historic"
    r"|\d{4}[-/]\d{2}[-/]\d{2}|\d{1,2}[/-]\d{4})\b",
    re.IGNORECASE,
)

_STATS_SIGNAL_RE = re.compile(
    r"\b(?:combien|how many|count|nombre|total|moyenne|average|mean|max|min"
    r"|distribution|statistique|statistics|proportion|taux|ratio|percent"
    r"|top|ranking|classement|densité|density|fréquence|frequency)\b",
    re.IGNORECASE,
)

_COMPARE_SIGNAL_RE = re.compile(
    r"\b(?:compare|comparer|comparaison|versus|vs\.?|différence|difference"
    r"|entre .+ et |between .+ and |plus que|less than|more than)\b",
    re.IGNORECASE,
)

# ── System prompt ─────────────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    current_year = date.today().year
    return _SYSTEM_PROMPT_TEMPLATE.replace("{{CURRENT_YEAR}}", str(current_year))

_SYSTEM_PROMPT_TEMPLATE = """\
You are the Intent Parser for PangIA, a geospatial intelligence platform.
Your sole responsibility is to analyse the user's question and return a
structured JSON object describing their intent.

## Output schema (all fields required)
{
  "intent_type": one of [
    "locate",             // find where something is, geocoding
    "analyze_proximity",  // what is near X? entities within N km
    "analyze_area",       // analyse a zone: stats, coverage, density
    "compare",            // compare entities, zones, or time periods
    "route",              // shortest path, itinerary, travel time
    "visualize",          // explicit map or chart request
    "statistics",         // counts, averages, rankings, trends
    "explain",            // explain a concept, entity, or relationship
    "search"              // open/keyword search, no dominant spatial intent
  ],
  "entities": [           // list of named entities (strings); empty list if none
    "entity_1", "entity_2"
  ],
  "geo_zone": null OR {   // null if no spatial extent implied
    "place_name": "Paris" OR null,
    "bbox": [minLon, minLat, maxLon, maxLat] OR null,
    "radius_km": number OR null,
    "raw": "within 5 km of Lyon"
  },
  "temporal_range": null OR {  // null if no temporal constraint
    "start": "2020-01-01" OR "last year" OR null,
    "end": "2023-12-31" OR null,
    "raw": "between 2020 and 2023"
  },
  "intention": "1-to-2 sentence plain-language restatement of the goal",
  "language": "fr",       // ISO-639-1 detected language
  "confidence": 0.95      // your confidence in this parsing [0.0–1.0]
}

## Rules
- Always return valid JSON conforming to the schema above.
- Extract ALL entities explicitly named (places, organisations, species, events…).
- For geo_zone, prefer named places over coordinates when both are present.
- For temporal_range, prefer ISO-8601 when the date is explicit; use the raw
  string verbatim when it is relative (e.g. "last 5 years").
- If no temporal constraint is mentioned at all, set temporal_range to
  {"start": "{{CURRENT_YEAR}}-01-01", "end": null, "raw": "current year"} as a
  soft hint only — downstream agents should prioritise recent data but must not
  exclude older results.
- The intention field must be in the same language as the user's query.
- Never add keys outside the schema.
- Never refuse to parse — always return a best-effort result with a low confidence.
- Be concise: return only the JSON object. No explanation, no preamble.
"""


# ── Node ─────────────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """Parse the latest user message and write a ParsedIntent into state."""
    query: str = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    # Fast-path: empty query
    if not query.strip():
        return {
            "parsed_intent": ParsedIntent(
                intent_type="search",
                intention="Empty query.",
                confidence=0.0,
            )
        }

    # Heuristic pre-filter: build a short context hint for the LLM
    hints: list[str] = []
    if _GEO_SIGNAL_RE.search(query):
        hints.append("spatial signals detected")
    if _TEMPORAL_SIGNAL_RE.search(query):
        hints.append("temporal signals detected")
    if _STATS_SIGNAL_RE.search(query):
        hints.append("statistical signals detected")
    if _COMPARE_SIGNAL_RE.search(query):
        hints.append("comparison signals detected")
    hint_line = f"\n[Pre-filter hints: {', '.join(hints)}]" if hints else ""

    try:
        llm = build_llm(get_agent_model_config("intent_parser_agent"))
        structured_llm = llm.with_structured_output(ParsedIntent)

        result: ParsedIntent = await structured_llm.ainvoke(
            [
                SystemMessage(content=_build_system_prompt()),
                HumanMessage(content=f"{query}{hint_line}"),
            ]
        )
        logger.debug(
            "IntentParser → type=%s entities=%s confidence=%.2f",
            result.intent_type,
            result.entities,
            result.confidence,
        )
        return {"parsed_intent": result}

    except Exception as exc:  # noqa: BLE001
        logger.warning("IntentParser failed (%s), using fallback.", exc)
        return {
            "parsed_intent": ParsedIntent(
                intent_type="search",
                intention=query[:200],
                confidence=0.0,
            )
        }
