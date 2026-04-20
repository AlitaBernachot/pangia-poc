# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Human Output Agent – decides whether map and/or dataviz visualisations are
needed for the current response.

This agent sits **above** :mod:`mapviz_agent` and :mod:`dataviz_agent` in the
pipeline.  It inspects the combined sub-agent results and the current user
query, then produces an ``output_decision`` key in its ``AgentOutput.state``:

.. code-block:: python

    {
        "needs_map": bool,      # True → invoke mapviz_agent downstream
        "needs_dataviz": bool,  # True → invoke dataviz_agent downstream
    }

Decision strategy
-----------------
1. **Fast-path – pre-built rich data**: when a connector (e.g. DataGouv MCP)
   has already populated ``context["dataviz"]`` or ``context["geojson"]``,
   skip the LLM and infer the decision from the data already present.
2. **Fast-path – no content**: if there is nothing to work with, skip both.
3. **Clear heuristic signals**: when strong keywords (geo or dataviz vocabulary)
   unambiguously answer both sides, the LLM is skipped entirely.
4. **Ambiguous cases**: an LLM call with a minimal classification prompt
   receives the sub-results + user query and returns a two-key JSON object.
5. **Error fallback**: if anything raises, default to
   ``{needs_map: True, needs_dataviz: True}`` so downstream agents always
   have a chance to run.

Note: this is a utility agent that is called directly inside a post-processing
orchestrator node rather than as a fanned-out sub-agent.  It therefore does
**not** need to participate in the router fan-out and is **not** registered in
the ``AGENTS`` dict.  It does, however, inherit from :class:`BaseAgent` to
benefit from LLM config resolution, system-prompt loading, timing, and
guardrails.
"""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from langchain_core.messages import HumanMessage, SystemMessage

from app.models import AgentInput, AgentOutput
from app.pangiagent.agents.base_agent import BaseAgent
from app.pangiagent.model_config import build_llm, get_agent_model_config
from libs.filereader import find_coord_columns

if TYPE_CHECKING:
    from app.pangiagent.state import OrchestratorState

logger = logging.getLogger(__name__)

# ── Heuristic patterns ────────────────────────────────────────────────────────

_COORD_HINT_RE = re.compile(
    r"lat(?:itude)?|lon(?:gitude)?|°[NS]|°[EW]|\b\d{1,3}\.\d+\b",
    re.IGNORECASE,
)
_GEO_KEYWORD_RE = re.compile(
    r"\b(?:map|carte|geojson|geometry|géométrie|coordinates?|coordonnées?|"
    r"polygon|point|linestring|feature|layer|couche|"
    r"address|adresse|lieu|place|location|localisation|"
    r"zone|region|région|territoire|boundary|frontière)\b",
    re.IGNORECASE,
)
_NUMERIC_HINT_RE = re.compile(
    r"(?:\b\d+[\.,]\d+|\b\d{2,}\b)"
    r"|(?:count|total|average|mean|sum|max|min|"
    r"nombre|total|moyenne|somme|maximum|minimum|"
    r"taux|ratio|percent|pourcentage|proportion|"
    r"trend|évolution|variation|distribution)",
    re.IGNORECASE,
)
_DATAVIZ_KEYWORD_RE = re.compile(
    r"\b(?:chart|graph|graphe|graphique|plot|table|tableau|kpi|dashboard|"
    r"histogram|bar|pie|line|scatter|visuali[sz]|statistics?|statistiques?|"
    r"compare|comparaison|analyse|analysis)\b",
    re.IGNORECASE,
)

_DEFAULT_PROMPT = """\
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


class HumanOutputAgent(BaseAgent):
    """LLM-backed agent that decides which visual components to render.

    Note: this agent is **not** registered in the orchestrator fan-out; it is
    called directly inside ``humanoutput_node`` after the parallel sub-agents
    have completed.
    """

    _DEFAULT_PROMPT = _DEFAULT_PROMPT

    def __init__(self, **kwargs) -> None:
        super().__init__(name="humanoutput_agent", **kwargs)
        self._system_prompt = self.get_prompt(self._DEFAULT_PROMPT)

    def get_capabilities(self) -> str:
        return (
            "Output decision: analyses combined sub-agent results and determines "
            "whether map and/or dataviz visualisations are needed for the response."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        """Core logic — reads sub_results, dataviz, geojson from context."""
        try:
            result = await self._decide(inp)
        except Exception as exc:  # noqa: BLE001
            logger.warning("HumanOutputAgent error (defaulting to both): %s", exc)
            result = {"needs_map": True, "needs_dataviz": True}

        output = AgentOutput(
            agent_name=self.name,
            answer=f"output_decision: {result}",
            confidence=1.0,
        )
        output.state["output_decision"] = result
        return output

    async def _decide(self, inp: AgentInput) -> dict[str, bool]:
        sub_results: dict[str, str] = inp.context.get("sub_results", {})
        existing_dataviz: dict | None = inp.context.get("dataviz")
        existing_geojson: dict | None = inp.context.get("geojson")
        user_query = inp.query

        # Fast-path: pre-built rich data overrides heuristics
        has_prebuilt_dataviz = bool(
            existing_dataviz
            and (
                existing_dataviz.get("tables")
                or existing_dataviz.get("charts")
                or existing_dataviz.get("kpis")
            )
        )
        if has_prebuilt_dataviz or existing_geojson is not None:
            tables = (existing_dataviz or {}).get("tables", [])
            columns = tables[0].get("columns", []) if tables else []
            lat_col, lon_col = find_coord_columns(columns)
            needs_map = existing_geojson is not None or (lat_col is not None and lon_col is not None)
            return {
                "needs_map": needs_map,
                "needs_dataviz": bool(has_prebuilt_dataviz),
            }

        # Fast-path: data_gouv ran but produced nothing useful
        if "data_gouv" in sub_results and not has_prebuilt_dataviz and existing_geojson is None:
            other_text = "\n".join(v for k, v in sub_results.items() if k != "data_gouv")
            combined_other = f"{other_text} {user_query}"
            needs_map = bool(
                _COORD_HINT_RE.search(combined_other) or _GEO_KEYWORD_RE.search(combined_other)
            )
            return {"needs_map": needs_map, "needs_dataviz": False}

        sub_text = "\n\n".join(
            f"[{agent.upper()} RESULTS]:\n{result}"
            for agent, result in sub_results.items()
            if result and result.strip()
        )
        combined = f"{sub_text} {user_query}"

        # Fast-path: nothing to work with
        if not combined.strip():
            return {"needs_map": False, "needs_dataviz": False}

        # Heuristic screening
        has_geo_signal = bool(
            _COORD_HINT_RE.search(combined) or _GEO_KEYWORD_RE.search(combined)
        )
        has_dataviz_signal = bool(
            _NUMERIC_HINT_RE.search(combined) or _DATAVIZ_KEYWORD_RE.search(combined)
        )
        geo_strong = bool(_GEO_KEYWORD_RE.search(combined))
        dataviz_strong = bool(_DATAVIZ_KEYWORD_RE.search(combined))

        # Both sides have a definitive heuristic answer → skip the LLM
        if (geo_strong or not has_geo_signal) and (dataviz_strong or not has_dataviz_signal):
            return {"needs_map": has_geo_signal, "needs_dataviz": has_dataviz_signal}

        # Ambiguous → ask the LLM
        llm = build_llm(get_agent_model_config(self.name))
        context = (
            f"{sub_text}\n\nOriginal user question: {user_query}"
            if sub_text
            else f"User question: {user_query}"
        )
        response = await llm.ainvoke(
            [
                SystemMessage(content=self._system_prompt),
                HumanMessage(content=context),
            ]
        )
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[^\n]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw.strip())
        try:
            decision = json.loads(raw)
            needs_map = bool(decision.get("needs_map", has_geo_signal))
            needs_dataviz = bool(decision.get("needs_dataviz", has_dataviz_signal))
        except (json.JSONDecodeError, AttributeError):
            logger.warning("HumanOutputAgent: could not parse LLM response %r", raw)
            needs_map = has_geo_signal
            needs_dataviz = has_dataviz_signal

        return {"needs_map": needs_map, "needs_dataviz": needs_dataviz}

    def make_node(self) -> Callable[[OrchestratorState], Coroutine[Any, Any, dict]]:
        """Return an async node function that runs this agent with the full sub_results context."""
        agent = self

        async def humanoutput_node(state: OrchestratorState) -> dict:
            dataviz: Any = None
            geojson: Any = None
            for result in (state.get("sub_results") or {}).values():
                if isinstance(result, dict):
                    if result.get("dataviz") and dataviz is None:
                        dataviz = result["dataviz"]
                    if result.get("geojson") and geojson is None:
                        geojson = result["geojson"]

            sub_text: dict[str, str] = {
                k: (v.get("answer") or "") if isinstance(v, dict) else str(v)
                for k, v in (state.get("sub_results") or {}).items()
            }
            inp = AgentInput(
                query=state["query"],
                session_id=state["session_id"],
                context={"sub_results": sub_text, "dataviz": dataviz, "geojson": geojson},
            )
            try:
                output = await agent.run(inp)
                decision = output.state.get("output_decision", {"needs_map": True, "needs_dataviz": True})
            except Exception:
                logger.exception("humanoutput_node: agent raised")
                decision = {"needs_map": True, "needs_dataviz": True}

            update: dict = {"output_decision": decision}
            if dataviz is not None:
                update["dataviz"] = dataviz
            if geojson is not None:
                update["geojson"] = geojson
            return update

        return humanoutput_node
