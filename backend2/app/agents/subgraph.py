# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""
Sub-agent subgraph factory.

Each ``BaseAgent`` is wrapped in a compiled LangGraph ``StateGraph`` with
three nodes:

    pre_guardrail_node ──[violation?]──► __end__   (sub_results carries error)
                       └──[ok]────────► execute_node ──► post_guardrail_node ──► __end__

The subgraph shares ``query``, ``session_id``, ``context``, and
``sub_results`` with the parent ``OrchestratorState``.  When LangGraph
runs the subgraph as a node those keys are copied from the parent state;
on completion only ``sub_results`` (a shared key) is merged back via the
``_merge_dicts`` reducer.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from langgraph.graph import END, StateGraph

from app.models import AgentInput, AgentOutput
from app.state import SubAgentState

if TYPE_CHECKING:
    from app.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


def make_subgraph(agent: "BaseAgent"):
    """Build and compile a LangGraph StateGraph for *agent*.

    Parameters
    ----------
    agent:
        A ``BaseAgent`` instance with ``pre_guardrails``, ``post_guardrails``,
        and an async ``_run`` coroutine.

    Returns
    -------
    CompiledStateGraph
        A compiled LangGraph graph ready to be added as a node in the
        orchestrator.
    """
    agent_name = agent.name

    # ── Node functions (closures capturing `agent`) ───────────────────────────

    def pre_guardrail_node(state: SubAgentState) -> dict:
        """Run pre-execution guardrails.

        Returns early (to END) with a sub_results error entry when any
        guardrail fires, skipping execute_node and post_guardrail_node.
        Initialises all ``agent_*`` fields so subsequent nodes can access
        them safely regardless of which branch is taken.
        """
        inp = AgentInput(
            query=state["query"],
            session_id=state["session_id"],
            context=state.get("context", {}),  # type: ignore[arg-type]
        )
        for guardrail in agent.pre_guardrails:
            violation = guardrail(inp)
            if violation:
                logger.warning("Pre-guardrail blocked [%s]: %s", agent_name, violation)
                return {
                    "agent_pre_violation": violation,
                    "agent_answer": "",
                    "agent_confidence": 0.0,
                    "agent_error": violation,
                    "agent_duration_ms": 0,
                    "agent_post_violations": [],
                    # Write sub_results so merge_node sees the blocked result
                    "sub_results": {
                        agent_name: {
                            "answer": "",
                            "confidence": 0.0,
                            "error": violation,
                            "duration_ms": 0,
                            "violations": [violation],
                        }
                    },
                }
        # No violation — initialise internal fields for downstream nodes
        return {
            "agent_pre_violation": None,
            "agent_answer": "",
            "agent_confidence": 0.0,
            "agent_error": None,
            "agent_duration_ms": 0,
            "agent_post_violations": [],
        }

    async def execute_node(state: SubAgentState) -> dict:
        """Run the agent's core logic."""
        inp = AgentInput(
            query=state["query"],
            session_id=state["session_id"],
            context=state.get("context", {}),  # type: ignore[arg-type]
        )
        t0 = time.monotonic()
        try:
            output = await agent._run(inp)
            return {
                "agent_answer": output.answer,
                "agent_confidence": output.confidence,
                "agent_error": output.error,
                "agent_duration_ms": int((time.monotonic() - t0) * 1000),
            }
        except Exception as exc:
            logger.exception("Agent [%s] raised an exception", agent_name)
            return {
                "agent_answer": "",
                "agent_confidence": 0.0,
                "agent_error": str(exc),
                "agent_duration_ms": int((time.monotonic() - t0) * 1000),
            }

    def post_guardrail_node(state: SubAgentState) -> dict:
        """Run post-execution guardrails and write sub_results."""
        confidence: float = state.get("agent_confidence", 0.0)  # type: ignore[assignment]
        violations: list[str] = []
        out = AgentOutput(
            agent_name=agent_name,
            answer=state.get("agent_answer", ""),  # type: ignore[arg-type]
            confidence=confidence,
        )
        for guardrail in agent.post_guardrails:
            v = guardrail(out)
            if v:
                logger.warning("Post-guardrail [%s]: %s", agent_name, v)
                violations.append(v)
                confidence = max(0.0, confidence - 0.2)
        return {
            "agent_post_violations": violations,
            "agent_confidence": confidence,
            # This shared key is merged back into the parent OrchestratorState
            "sub_results": {
                agent_name: {
                    "answer": state.get("agent_answer", ""),
                    "confidence": confidence,
                    "error": state.get("agent_error"),
                    "duration_ms": state.get("agent_duration_ms", 0),
                    "violations": violations,
                }
            },
        }

    def _route_after_pre(state: SubAgentState) -> str:
        return END if state.get("agent_pre_violation") else "execute_node"

    # ── Build and compile ─────────────────────────────────────────────────────

    workflow = StateGraph(SubAgentState)
    workflow.add_node("pre_guardrail_node", pre_guardrail_node)
    workflow.add_node("execute_node", execute_node)
    workflow.add_node("post_guardrail_node", post_guardrail_node)

    workflow.set_entry_point("pre_guardrail_node")
    workflow.add_conditional_edges(
        "pre_guardrail_node",
        _route_after_pre,
        {"execute_node": "execute_node", END: END},
    )
    workflow.add_edge("execute_node", "post_guardrail_node")
    workflow.add_edge("post_guardrail_node", END)

    return workflow.compile()
