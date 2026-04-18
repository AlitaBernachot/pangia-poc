# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""
Sub-agent subgraph factory.

Each ``BaseAgent`` is wrapped in a compiled LangGraph ``StateGraph`` with a
single node:

    execute_node ──► __end__

``BaseAgent.run()`` already handles pre-guardrails, timing, exception
catching, and post-guardrails, so the subgraph is a thin LangGraph wrapper
that delegates entirely to that method.

The subgraph shares ``query``, ``session_id``, ``context``, and
``sub_results`` with the parent ``OrchestratorState``.  When LangGraph
runs the subgraph as a node those keys are copied from the parent state;
on completion only ``sub_results`` (a shared key) is merged back via the
``_merge_dicts`` reducer.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langgraph.graph import END, StateGraph

from app.models import AgentInput
from app.state import SubAgentState

if TYPE_CHECKING:
    from app.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


def make_subgraph(agent: "BaseAgent"):
    """Build and compile a LangGraph StateGraph for *agent*.

    Parameters
    ----------
    agent:
        A ``BaseAgent`` instance.  All guardrail and timing logic is handled
        by ``agent.run()``.

    Returns
    -------
    CompiledStateGraph
        A compiled LangGraph graph ready to be added as a node in the
        orchestrator.
    """
    agent_name = agent.name

    # ── Node function (closure capturing `agent`) ─────────────────────────────

    async def execute_node(state: SubAgentState) -> dict:
        """Delegate entirely to ``agent.run()``.

        ``BaseAgent.run()`` handles pre-guardrails, timing, exception
        catching, and post-guardrails.  This node is a thin LangGraph wrapper
        that maps the result into ``sub_results``.
        """
        inp = AgentInput(
            query=state["query"],
            session_id=state["session_id"],
            context=state.get("context", {}),  # type: ignore[arg-type]
        )
        output = await agent.run(inp)
        return {
            # This shared key is merged back into the parent OrchestratorState
            "sub_results": {
                agent_name: {
                    "answer": output.answer,
                    "confidence": output.confidence,
                    "error": output.error,
                    "duration_ms": output.state.get("duration_ms", 0),
                    "violations": output.state.get("post_guardrail_violations", []),
                }
            }
        }

    # ── Build and compile ─────────────────────────────────────────────────────

    workflow = StateGraph(SubAgentState)
    workflow.add_node("execute_node", execute_node)

    workflow.set_entry_point("execute_node")
    workflow.add_edge("execute_node", END)

    return workflow.compile()
