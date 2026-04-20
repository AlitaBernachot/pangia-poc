# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""SmartDispatcherAgent — deterministic + semantic router.

This agent selects which connector agents to invoke for a given query
**without making any LLM call**.  It combines:

1. **Keyword scoring** (+2 per topic/entity_type match, case-insensitive
   substring search in the query).
2. **Semantic scoring** (cosine similarity via ChromaDB, score in [0, 1]).

Any source with composite score ≥ ``DISPATCH_THRESHOLD`` is selected.
When nothing reaches the threshold, the highest-scoring source is used as
a safe fallback.

The agent reads the list of currently active agents from
``inp.context["active_agents"]`` (injected by ``router_node`` at call time)
so it only considers agents that are actually registered in the graph.

Usage (internal — called directly by ``router_node``, not via subgraph)
----------------------------------------------------------------------
::

    dispatcher = SmartDispatcherAgent()
    output = await dispatcher._run(inp)
    agents_to_call = output.state["agents_to_call"]   # list[str]
"""
from __future__ import annotations

import json
import logging

from app.models import AgentInput, AgentOutput
from app.pangiagent.agents.base_agents.base_agent import BaseAgent
from app.pangiagent.source_registry import semantic_search_sources, get_registry

logger = logging.getLogger(__name__)

# Sources whose composite score is at or above this threshold are selected.
DISPATCH_THRESHOLD: float = 2.0

# Score added per keyword (topic or entity_type) matched in the query.
_KEYWORD_MATCH_SCORE: float = 2.0


class SmartDispatcherAgent(BaseAgent):
    """Deterministic + semantic agent dispatcher (no LLM calls).

    Inherits from :class:`BaseAgent` to satisfy the interface contract and
    to benefit from pre/post guardrails and timing via :meth:`run`.  However,
    ``SmartDispatcherAgent`` is typically called via ``_run()`` directly
    inside ``router_node`` as an internal utility — not fanned out as a
    subgraph — so its guardrails are left empty by default.

    Class attributes
    ----------------
    name:
        ``"smart_dispatcher_agent"``
    _DEFAULT_PROMPT:
        Fallback description (not used for LLM calls — only for
        ``get_capabilities()`` and the YAML prompt lookup).
    """

    name = "smart_dispatcher_agent"
    _DEFAULT_PROMPT = (
        "You are a smart dispatcher agent. You select which data-source agents "
        "to invoke for a given query using keyword matching and semantic similarity, "
        "without making any LLM calls."
    )

    def __init__(self, **kwargs) -> None:
        super().__init__(name="smart_dispatcher_agent", **kwargs)

    # ------------------------------------------------------------------
    # BaseAgent contract
    # ------------------------------------------------------------------

    def get_capabilities(self) -> str:
        return (
            "Deterministic + semantic routing: scores registered data-source agents "
            "using keyword matching (topics, entity types) and ChromaDB cosine "
            "similarity, then selects those above a configurable threshold — "
            "no LLM calls required."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        """Select agents to call for *inp.query*.

        Parameters
        ----------
        inp:
            ``inp.context["active_agents"]`` must be a ``list[str]`` of the
            agent keys currently registered in the orchestrator graph.

        Returns
        -------
        AgentOutput
            ``answer`` is the JSON-serialised list of selected connectors.
            ``state["agents_to_call"]`` holds the same list for direct
            consumption by ``router_node``.
        """
        active_agents: list[str] = inp.context.get("active_agents", [])

        # Filter registry to active agents only
        registry = get_registry()
        eligible = [e for e in registry if e.connector in active_agents]

        if not eligible:
            logger.warning(
                "SmartDispatcherAgent: no registry entries match active agents %s",
                active_agents,
            )
            selected = active_agents[:1] if active_agents else []
            return AgentOutput(
                agent_name=self.name,
                answer=json.dumps(selected),
                confidence=1.0,
                state={"agents_to_call": selected},
            )

        # Semantic scores from ChromaDB
        semantic_scores: dict[str, float] = await semantic_search_sources(inp.query)

        # Composite scoring
        query_lower = inp.query.lower()

        def _score(entry) -> float:
            score = 0.0
            # +_KEYWORD_MATCH_SCORE for each topic that appears as a substring in the query
            for topic in entry.topics:
                if topic.lower() in query_lower:
                    score += _KEYWORD_MATCH_SCORE
            # +_KEYWORD_MATCH_SCORE for each entity_type that appears as a substring in the query
            for entity_type in entry.entity_types:
                if entity_type.lower() in query_lower:
                    score += _KEYWORD_MATCH_SCORE
            # +semantic score (in [0, 1])
            score += semantic_scores.get(entry.id, 0.0)
            return score

        scored = [(entry, _score(entry)) for entry in eligible]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Select entries above threshold
        selected_entries = [e for e, s in scored if s >= DISPATCH_THRESHOLD]

        if not selected_entries:
            # Fallback: use the highest-scoring entry
            logger.debug(
                "SmartDispatcherAgent: no entry reached threshold %.1f — using top scorer '%s' (%.2f)",
                DISPATCH_THRESHOLD,
                scored[0][0].connector,
                scored[0][1],
            )
            selected_entries = [scored[0][0]]

        selected = [e.connector for e in selected_entries]

        logger.info(
            "SmartDispatcherAgent: query=%r → selected=%s",
            inp.query[:80],
            selected,
        )

        return AgentOutput(
            agent_name=self.name,
            answer=json.dumps(selected),
            confidence=1.0,
            state={"agents_to_call": selected},
        )
