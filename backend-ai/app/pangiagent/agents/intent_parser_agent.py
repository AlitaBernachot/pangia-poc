# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Intent parser agent — extracts structured intent from a user query.

``IntentParserAgent`` is a **utility agent**: it is called directly inside
``intent_node`` in the orchestrator graph and is NOT fanned out as a sub-agent.
It overrides :meth:`make_node` to return an ``OrchestratorState``-compatible
node function, exactly like ``HumanOutputAgent``, ``DataVizAgent`` and
``MapVizAgent``.

The parsed intent is merged into ``state["context"]["intent"]`` so that every
downstream agent (notably ``DataGouvMCPAgent``) can read it from
``inp.context.get("intent")``.

Parsed intent schema
--------------------
::

    {
        "action":          "display" | "filter" | "search" | "preview" | "compare",
        "entity_concept": str,   # canonical dataset concept to search for
        "filters":         list[{"column": str, "value": str, "op": str}],
        "geo_scope":       str    # geographic scope, or "" if none
    }

Configurability
---------------
Like all ``BaseAgent`` subclasses, the model, provider, and temperature can
be overridden per-agent via environment variables:

* ``INTENT_PARSER_AGENT_MODEL_PROVIDER``
* ``INTENT_PARSER_AGENT_MODEL_NAME``
* ``INTENT_PARSER_AGENT_TEMPERATURE``

The system prompt can be overridden via
``backend-ai/config/prompts/intent_parser_agent.yaml`` (``prompt:`` key).
"""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.models import AgentInput, AgentOutput
from app.pangiagent.agents.base_agents.base_agent import BaseAgent
from app.pangiagent.model_config import build_llm, get_agent_model_config

if TYPE_CHECKING:
    from app.pangiagent.state import OrchestratorState

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = """\
You are an intent parser for a geospatial open-data assistant (PangIA).
Your sole job is to read a user query and return a single JSON object describing the intent.

## Output format (strict JSON, no markdown, no explanation)
{
  "action":          "<action>",
  "entity_concept": "<concept>",
  "filters":         [{"column": "<col>", "value": "<val>", "op": "<op>"}],
  "geo_scope":       "<scope>",
  "needs_map":       <true|false>
}

## Field definitions

### action  (required — choose exactly one)
| Value     | When to use                                                              |
|-----------|--------------------------------------------------------------------------|
| display   | User wants to see / visualise / show / afficher all data                 |
| filter    | User wants records matching a condition (open, closed, status …)         |
| preview   | User wants a sample / overview / aperçu / quelques exemples              |
| search    | User wants to discover / list / find what datasets exist on a topic      |
| compare   | User wants to compare two or more datasets or values                     |

IMPORTANT: queries that ask WHERE something IS ("où se trouve/sont/trouvent",
"localisation de", "position de", "carte des", "sur la carte", "show on map",
"where is/are") are ALWAYS `display`, never `search`.

### entity_concept  (required)
The canonical name of the dataset or data topic to look for, stripped of action verbs
and conversational preambles.  Keep geographic scope words if they are part of the
dataset name (e.g. "qualité de l'air" not "affiche la qualité de l'air en France").

### filters  (default: [])
List of column-level filters inferred from the query.
- op: "equals" only if the user quoted the exact cell value; otherwise "contains".
- Leave the list empty when no condition is expressed.

### geo_scope  (default: "")
The geographic scope of the query (country, region, city, etc.).
Use the name as expressed by the user.  Leave empty if the query is not geographically
restricted.

### needs_map  (default: false)
Set to `true` when the query explicitly or implicitly asks for geographic locations:
- "où se trouve/sont/trouvent", "localisation", "position", "carte", "map"
- "show on a map", "where is/are", "sur la carte"
- datasets whose concept implies point/polygon data (cameras, stations, parcelles, …)
  AND the user wants to see their locations.
Set to `false` for purely tabular or statistical queries.

## Examples

Query: "Affiche les prix des carburants en France"
→ {"action": "display", "entity_concept": "prix des carburants", "filters": [], "geo_scope": "France", "needs_map": false}

Query: "Montre les stations ouvertes en Bretagne"
→ {"action": "filter", "entity_concept": "stations-service", "filters": [{"column": "statut", "value": "ouvert", "op": "contains"}], "geo_scope": "Bretagne", "needs_map": true}

Query: "Donne-moi un aperçu des données sur la qualité de l'air"
→ {"action": "preview", "entity_concept": "qualité de l'air", "filters": [], "geo_scope": "", "needs_map": false}

Query: "Quels datasets existent sur les risques d'inondation en Nouvelle-Aquitaine ?"
→ {"action": "search", "entity_concept": "risques inondation", "filters": [], "geo_scope": "Nouvelle-Aquitaine", "needs_map": false}

Query: "Où se trouvent les webcams dans Orléans ?"
→ {"action": "display", "entity_concept": "webcams", "filters": [], "geo_scope": "Orléans", "needs_map": true}

Query: "Compare les accidents de la route en 2022 et 2023"
→ {"action": "compare", "entity_concept": "accidents de la route", "filters": [], "geo_scope": "", "needs_map": false}

Query: "Show all bike-sharing stations in Lyon"
→ {"action": "display", "entity_concept": "vélos en libre-service", "filters": [], "geo_scope": "Lyon", "needs_map": true}

## Rules
- Return ONLY the raw JSON object — no markdown fences, no explanation.
- Never invent filters not mentioned in the query.
- Use the same language as the user for string values (keep French words as-is).
"""

# Regex to extract a JSON object from an LLM response that may contain prose
_JSON_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)

_VALID_ACTIONS = {"display", "filter", "search", "preview", "compare"}


def _parse_response(raw: str) -> dict[str, Any]:
    """Extract and validate the JSON intent object from the LLM response."""
    text = (raw or "").strip()
    # Try direct parse first
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # Fallback: extract first {...} block
        match = _JSON_RE.search(text)
        if not match:
            raise ValueError(f"No JSON object found in LLM response: {text!r}")
        obj = json.loads(match.group())

    # Normalise and validate
    action = str(obj.get("action", "display")).lower().strip()
    if action not in _VALID_ACTIONS:
        logger.warning("IntentParserAgent: unknown action %r — falling back to 'display'", action)
        action = "display"

    filters = obj.get("filters") or []
    if not isinstance(filters, list):
        filters = []
    # Ensure each filter has the expected keys
    clean_filters = []
    for f in filters:
        if isinstance(f, dict) and "column" in f and "value" in f:
            clean_filters.append({
                "column": str(f["column"]),
                "value": str(f["value"]),
                "op": str(f.get("op", "contains")),
            })

    return {
        "action": action,
        "entity_concept": str(obj.get("entity_concept", "")).strip(),
        "filters": clean_filters,
        "geo_scope": str(obj.get("geo_scope", "")).strip(),
        "needs_map": bool(obj.get("needs_map", False)),
        "is_followup": bool(obj.get("is_followup", False)),
    }


class IntentParserAgent(BaseAgent):
    """Utility agent: parses a user query into structured intent.

    Called directly inside ``intent_node`` — NOT fanned out as a sub-agent.
    Overrides :meth:`make_node` to return an ``OrchestratorState``-compatible
    node function that merges the parsed intent into ``state["context"]["intent"]``.
    """

    name = "intent_parser_agent"
    _DEFAULT_PROMPT = _DEFAULT_PROMPT

    def __init__(self, **kwargs) -> None:
        super().__init__(name=self.name, **kwargs)
        self._system_prompt = self.get_prompt(self._DEFAULT_PROMPT)

    def get_capabilities(self) -> str:
        return (
            "Parses user queries into structured intent: action, dataset concept, "
            "column filters, and geographic scope."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        """Implement the abstract method; delegates to :meth:`parse`."""
        parsed = await self.parse(inp.query)
        return AgentOutput(
            agent_name=self.name,
            answer=json.dumps(parsed, ensure_ascii=False),
            confidence=0.9,
            state={"intent": parsed},
        )

    async def parse(self, query: str, previous_turns: list[dict] | None = None) -> dict[str, Any]:
        """Parse *query* and return a structured intent dict.

        When *previous_turns* is provided (list of ``{query, answer}`` dicts,
        newest last), they are injected as conversation history so the LLM can
        resolve referential expressions like "ces données", "parmi ces résultats",
        "filtre les", etc.

        Returns a best-effort dict even on LLM or parsing errors (fallback to
        ``action=display``, ``entity_concept=query``).
        """
        try:
            llm = build_llm(get_agent_model_config(self.name))
            messages = [SystemMessage(content=self._system_prompt)]
            # Inject the last 3 turns as alternating Human/AI messages so the
            # LLM can resolve back-references ("ces données", "parmi eux", …).
            for turn in (previous_turns or [])[-3:]:
                messages.append(HumanMessage(content=turn.get("query", "")))
                messages.append(AIMessage(content=turn.get("answer", "")))
            messages.append(HumanMessage(content=query))
            response = await llm.ainvoke(messages)
            raw = (response.content or "").strip()
            parsed = _parse_response(raw)
            logger.info(
                "IntentParserAgent: action=%r concept=%r filters=%s geo=%r followup=%r",
                parsed["action"],
                parsed["entity_concept"],
                parsed["filters"],
                parsed["geo_scope"],
                parsed["is_followup"],
            )
            return parsed
        except Exception:
            logger.exception("IntentParserAgent: failed to parse intent for query %r", query)
            return {
                "action": "display",
                "entity_concept": query,
                "filters": [],
                "geo_scope": "",
                "needs_map": False,
                "is_followup": False,
            }

    def make_node(self):
        """Return an ``OrchestratorState`` node that injects parsed intent into context.

        The intent dict is merged into ``state["context"]["intent"]`` so that
        downstream agents (e.g. ``DataGouvMCPAgent``) can read it via
        ``inp.context.get("intent")``.
        """
        agent = self

        async def _intent_node(state: "OrchestratorState") -> dict:
            ctx: dict[str, Any] = dict(state.get("context") or {})
            previous_turns: list[dict] = ctx.get("previous_turns") or []
            parsed = await agent.parse(state["query"], previous_turns=previous_turns)
            ctx["intent"] = parsed
            return {"context": ctx, "intent": parsed}

        return _intent_node
