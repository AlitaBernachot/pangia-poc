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
from app.pangiagent.agents.orchestrator_agent import build_graph
from app.pangiagent.agents.rag_agent import RAGAgent
from app.pangiagent.agents.summary_agent import SummaryAgent
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
}

# ── Compiled orchestrator graph ────────────────────────────────────────────────
# Built at module import time; also writes Mermaid diagrams to
# app/pangiagent/mermaid_graph/.

ORCHESTRATOR_GRAPH = build_graph(AGENTS)
