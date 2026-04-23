# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Agent registry and compiled orchestrator graph.

This module re-exports ``ORCHESTRATOR_GRAPH`` built by
:func:`~app.pangiagent.deep_graph.build_deep_graph`, which is the single
deepagents-based orchestrator that replaces the previous home-made
LangGraph fan-out/merge graph.

Import ``ORCHESTRATOR_GRAPH`` from here whenever you need to interact with
the agent layer (e.g. in API route handlers).
"""
from __future__ import annotations

from app.pangiagent.deep_graph import build_deep_graph

# ── Compiled orchestrator graph ────────────────────────────────────────────────
# Built at module import time using langchain deepagents.

ORCHESTRATOR_GRAPH = build_deep_graph()
