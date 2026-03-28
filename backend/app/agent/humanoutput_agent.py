"""Human Output Agent – decides whether map and/or dataviz visualisations are
needed for the current response.

This agent sits **above** :mod:`map_agent` and :mod:`dataviz_agent` in the
pipeline.  It inspects the combined ``sub_results`` text and the current user
query, then produces an :class:`~app.agent.state.AgentState` fragment with an
``output_decision`` key:

.. code-block:: python

    {
        "needs_map": bool,      # True → invoke map_agent downstream
        "needs_dataviz": bool,  # True → invoke dataviz_agent downstream
    }

Decision strategy
-----------------
1. **Fast-path – no content**: if there is nothing to work with, skip both.
2. **Clear heuristic signals**: when strong keywords (geo or dataviz vocabulary)
   unambiguously answer both sides, the LLM is skipped entirely.
3. **Ambiguous cases**: an LLM call with a minimal classification prompt
   receives the sub-results + user query and returns a two-key JSON object.
4. **Error fallback**: if anything raises, default to ``{needs_map: True,
   needs_dataviz: True}`` so downstream agents always have a chance to run.

When the agent is **disabled** (``HUMANOUTPUT_AGENT_ENABLED=false``) it is
never added to the graph and the pipeline falls back to the legacy behaviour
(both map and dataviz called unconditionally if their individual flags are on).
"""
from __future__ import annotations

import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.model_config import build_llm, get_agent_model_config
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

# ── Heuristic patterns ────────────────────────────────────────────────────────

# Coordinate-level signals (same as map_agent)
_COORD_HINT_RE = re.compile(
    r"lat(?:itude)?|lon(?:gitude)?|°[NS]|°[EW]|\b\d{1,3}\.\d+\b",
    re.IGNORECASE,
)

# Broader geographic vocabulary → strong geo signal
_GEO_KEYWORD_RE = re.compile(
    r"\b(?:map|carte|geojson|geometry|géométrie|coordinates?|coordonnées?|"
    r"polygon|point|linestring|feature|layer|couche|"
    r"address|adresse|lieu|place|location|localisation|"
    r"zone|region|région|territoire|boundary|frontière)\b",
    re.IGNORECASE,
)

# Numeric / statistical signals (same as dataviz_agent)
_NUMERIC_HINT_RE = re.compile(
    r"(?:\b\d+[\.,]\d+|\b\d{2,}\b)"
    r"|(?:count|total|average|mean|sum|max|min|"
    r"nombre|total|moyenne|somme|maximum|minimum|"
    r"taux|ratio|percent|pourcentage|proportion|"
    r"trend|évolution|variation|distribution)",
    re.IGNORECASE,
)

# Broader chart / table vocabulary → strong dataviz signal
_DATAVIZ_KEYWORD_RE = re.compile(
    r"\b(?:chart|graph|graphe|graphique|plot|table|tableau|kpi|dashboard|"
    r"histogram|bar|pie|line|scatter|visuali[sz]|statistics?|statistiques?|"
    r"compare|comparaison|analyse|analysis)\b",
    re.IGNORECASE,
)

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are the Human Output Agent for PangIA, a geospatial intelligence platform.
Your sole job is to decide which visual components should be rendered for the user
based on the data retrieved by the other agents.

Rules:
- Reply with a JSON object containing exactly two boolean keys:
  • "needs_map": true if the data contains geographic coordinates, GeoJSON
    features, addresses, or spatially-distributed information worth mapping.
  • "needs_dataviz": true if the data contains numeric values, statistics,
    counts, rankings, time-series, or tabular comparisons worth visualising.
- Both can be true when the data is spatial AND quantitative.
- Both can be false when the data is purely textual (plain factual answer).
- Do NOT include any explanation, markdown, or extra keys – only raw JSON.

Example: {"needs_map": true, "needs_dataviz": false}
"""

# ── Node function ─────────────────────────────────────────────────────────────


async def run(state: AgentState) -> dict:
    """LangGraph node: decide which visualisation agents to invoke.

    Returns a state fragment with ``output_decision`` set.  Falls back to
    ``{needs_map: True, needs_dataviz: True}`` on any error so that downstream
    agents always have the opportunity to run.
    """
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        logger.warning("HumanOutput agent error (defaulting to both): %s", exc)
        return {"output_decision": {"needs_map": True, "needs_dataviz": True}}


async def _run(state: AgentState) -> dict:
    sub_results: dict[str, str] = state.get("sub_results", {})
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    sub_text = "\n\n".join(
        f"[{agent.upper()} RESULTS]:\n{result}"
        for agent, result in sub_results.items()
        if result and result.strip()
    )
    combined = f"{sub_text} {user_query}"

    # Fast-path: nothing to work with
    if not combined.strip():
        return {"output_decision": {"needs_map": False, "needs_dataviz": False}}

    # Heuristic screening ─────────────────────────────────────────────────────
    has_geo_signal = bool(
        _COORD_HINT_RE.search(combined) or _GEO_KEYWORD_RE.search(combined)
    )
    has_dataviz_signal = bool(
        _NUMERIC_HINT_RE.search(combined) or _DATAVIZ_KEYWORD_RE.search(combined)
    )

    # "Strong" = at least one keyword match (not just an incidental decimal)
    geo_strong = bool(_GEO_KEYWORD_RE.search(combined))
    dataviz_strong = bool(_DATAVIZ_KEYWORD_RE.search(combined))

    # Both sides have a definitive heuristic answer → skip the LLM
    if (geo_strong or not has_geo_signal) and (dataviz_strong or not has_dataviz_signal):
        return {
            "output_decision": {
                "needs_map": has_geo_signal,
                "needs_dataviz": has_dataviz_signal,
            }
        }

    # Ambiguous → ask the LLM ─────────────────────────────────────────────────
    llm = build_llm(get_agent_model_config("humanoutput_agent"), streaming=False)

    context = (
        f"{sub_text}\n\nOriginal user question: {user_query}"
        if sub_text
        else f"User question: {user_query}"
    )

    response = await llm.ainvoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=context),
        ]
    )

    raw = response.content.strip()
    # Strip possible markdown code fences
    if raw.startswith("```"):
        raw = re.sub(r"^```[^\n]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw.strip())

    try:
        decision = json.loads(raw)
        needs_map = bool(decision.get("needs_map", has_geo_signal))
        needs_dataviz = bool(decision.get("needs_dataviz", has_dataviz_signal))
    except (json.JSONDecodeError, AttributeError):
        # LLM returned an unparseable response → fall back to heuristics
        logger.warning("HumanOutput agent: could not parse LLM response %r", raw)
        needs_map = has_geo_signal
        needs_dataviz = has_dataviz_signal

    return {"output_decision": {"needs_map": needs_map, "needs_dataviz": needs_dataviz}}
