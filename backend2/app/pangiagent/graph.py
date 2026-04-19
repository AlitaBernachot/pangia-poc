# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Agent registry and compiled orchestrator graph.

This module is the single place where:
- each ``BaseAgent`` subclass is instantiated with its guardrails, and
- ``build_graph()`` compiles the LangGraph orchestrator (also writing
  Mermaid diagrams to ``app/pangiagent/mermaid_graph/``).

Import ``AGENTS`` or ``ORCHESTRATOR_GRAPH`` from here whenever you need
to interact with the agent layer (e.g. in API route handlers).
"""
from __future__ import annotations

from app.pangiagent.agents.calculator_agent import CalculatorAgent
from app.pangiagent.agents.datagouv_mcp_agent import DataGouvMCPAgent
from app.pangiagent.agents.dataviz_agent import DataVizAgent
from app.pangiagent.agents.geonetwork_mcp_agent import GeoNetworkMCPAgent
from app.pangiagent.agents.humanoutput_agent import HumanOutputAgent
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

# ── Compiled orchestrator graph ────────────────────────────────────────────────
# Built at module import time; also writes Mermaid diagrams to
# app/pangiagent/mermaid_graph/.

ORCHESTRATOR_GRAPH = build_graph(AGENTS, output_agents=OUTPUT_AGENTS, synthesis_agent=SYNTHESIS_AGENT)
