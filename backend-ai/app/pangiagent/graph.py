"""Agent registry and compiled orchestrator graph.

This module is the single place where:
- each ``BaseAgent`` subclass is instantiated with its guardrails, and
- ``build_graph()`` compiles the LangGraph orchestrator (also writing
  Mermaid diagrams to ``app/pangiagent/mermaid_graph/``).

Call ``await init_graph()`` once at application startup (in the FastAPI
lifespan handler) before serving any requests.  Use ``get_graph()`` (sync)
everywhere else to retrieve the compiled graph.
"""
from __future__ import annotations

import logging

from app.pangiagent.agents.calculator_agent import CalculatorAgent
from app.pangiagent.agents.datagouv_mcp_agent import DataGouvMCPAgent
from app.pangiagent.agents.dataviz_agent import DataVizAgent
from app.pangiagent.agents.followup_filter_agent import FollowupFilterAgent
from app.pangiagent.agents.geonetwork_mcp_agent import GeoNetworkMCPAgent
from app.pangiagent.agents.humanoutput_agent import HumanOutputAgent
from app.pangiagent.agents.intent_parser_agent import IntentParserAgent
from app.pangiagent.agents.mapviz_agent import MapVizAgent
from app.pangiagent.agents.neo4j_agent import Neo4jAgent
from app.pangiagent.agents.orchestrator_agent import build_graph
from app.pangiagent.agents.postgis_agent import PostGISAgent
from app.pangiagent.agents.rag_agent import RAGAgent
from app.pangiagent.agents.rdf_agent import RDFAgent
from app.pangiagent.agents.summary_agent import SummaryAgent
from app.pangiagent.agents.synthesis_agent import SynthesisAgent
from app.pangiagent.agents.vector_chroma_agent import VectorChromaAgent
from app.pangiagent.guardrails import check_ambiguous_intent, check_output_length, check_toxic_input

logger = logging.getLogger(__name__)

# ── Agent registry ─────────────────────────────────────────────────────────────
# Each agent is instantiated once with its guardrails wired in.

AGENTS = {
    "rag_agent": RAGAgent(
        pre_guardrails=[check_toxic_input, check_ambiguous_intent],
        post_guardrails=[check_output_length],
    ),
    "calculator_agent": CalculatorAgent(
        pre_guardrails=[check_toxic_input],
    ),
    "summary_agent": SummaryAgent(
        pre_guardrails=[check_toxic_input, check_ambiguous_intent],
        post_guardrails=[check_output_length],
    ),
    "neo4j_agent": Neo4jAgent(
        pre_guardrails=[check_toxic_input, check_ambiguous_intent],
        post_guardrails=[check_output_length],
    ),
    "postgis_agent": PostGISAgent(
        pre_guardrails=[check_toxic_input, check_ambiguous_intent],
        post_guardrails=[check_output_length],
    ),
    "rdf_agent": RDFAgent(
        pre_guardrails=[check_toxic_input, check_ambiguous_intent],
        post_guardrails=[check_output_length],
    ),
    "vector_chroma_agent": VectorChromaAgent(
        pre_guardrails=[check_toxic_input, check_ambiguous_intent],
        post_guardrails=[check_output_length],
    ),
    "datagouv_mcp_agent": DataGouvMCPAgent(
        pre_guardrails=[check_toxic_input],
        post_guardrails=[check_output_length],
    ),
    "geonetwork_mcp_agent": GeoNetworkMCPAgent(
        pre_guardrails=[check_toxic_input],
        post_guardrails=[check_output_length],
    ),
    "followup_filter_agent": FollowupFilterAgent(),
}

# ── Output agent registry ──────────────────────────────────────────────────────
# Post-processing agents run **after** the fan-out merge, in sequential order:
#   humanoutput_agent → dataviz_agent (conditional) → mapviz_agent (conditional)
# They are NOT dispatched by the router and are NOT in AGENTS.

OUTPUT_AGENTS = {
    "humanoutput_agent": HumanOutputAgent(),
    "dataviz_agent": DataVizAgent(),
    "mapviz_agent": MapVizAgent(),
}

SYNTHESIS_AGENT = SynthesisAgent()

INTENT_AGENT = IntentParserAgent()

# ── Compiled orchestrator graph ────────────────────────────────────────────────
# Initialised lazily at startup via ``init_graph()`` so that the async
# PostgreSQL checkpointer can be created before graph compilation.

_ORCHESTRATOR_GRAPH = None


def get_graph():
    """Return the compiled orchestrator graph.

    Raises ``RuntimeError`` when called before ``init_graph()``.
    """
    if _ORCHESTRATOR_GRAPH is None:
        raise RuntimeError(
            "Orchestrator graph not initialised — call await init_graph() at startup."
        )
    return _ORCHESTRATOR_GRAPH


async def init_graph() -> None:
    """Initialise the PostgreSQL checkpointer then compile the orchestrator graph.

    Must be called once during application startup (FastAPI lifespan).
    """
    global _ORCHESTRATOR_GRAPH
    if _ORCHESTRATOR_GRAPH is not None:
        return  # already initialised

    from app.pangiagent.checkpointer import init_checkpointer, get_checkpointer

    await init_checkpointer()
    checkpointer = get_checkpointer()

    _ORCHESTRATOR_GRAPH = build_graph(
        AGENTS,
        output_agents=OUTPUT_AGENTS,
        synthesis_agent=SYNTHESIS_AGENT,
        intent_agent=INTENT_AGENT,
        checkpointer=checkpointer,
    )
    logger.info("Orchestrator graph initialised with PostgreSQL checkpointer")

