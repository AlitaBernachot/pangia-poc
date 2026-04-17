# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""
LangGraph state schemas for the V2 multi-agent backend.

Two state types are defined:

SubAgentState
    Used by each agent's compiled subgraph
    (pre_guardrail_node → execute_node → post_guardrail_node).
    Keys shared with OrchestratorState (``query``, ``session_id``,
    ``context``, ``sub_results``) are mapped in automatically by LangGraph
    when the subgraph is invoked as a node.  After the subgraph completes,
    only the shared keys are merged back into the parent state.  The
    ``agent_*`` keys are internal to the subgraph and are never propagated.

OrchestratorState
    Used by the main orchestrator StateGraph.
    ``sub_results`` uses a ``_merge_dicts`` reducer so that parallel
    sub-agent results are accumulated rather than overwritten.
"""
from __future__ import annotations

from typing import Annotated, Any

from typing_extensions import TypedDict


def _merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Reducer: merge two dicts (right wins on conflicts)."""
    return {**left, **right}


class SubAgentState(TypedDict):
    """State for each sub-agent subgraph.

    Shared keys (query, session_id, context, sub_results) come from the
    parent OrchestratorState.  Internal ``agent_*`` keys are not present in
    the parent and therefore are never merged back after the subgraph ends.
    """

    # ── shared with OrchestratorState (passed in by LangGraph) ───────────────
    query: str
    session_id: str
    context: dict[str, Any]
    # ── shared output key (merged back into parent via _merge_dicts) ─────────
    sub_results: Annotated[dict[str, Any], _merge_dicts]

    # ── internal subgraph fields (never merged back to parent) ───────────────
    agent_answer: str
    agent_confidence: float
    agent_error: str | None
    agent_duration_ms: int
    agent_pre_violation: str | None
    agent_post_violations: list[str]


class OrchestratorState(TypedDict):
    """Shared state threaded through the orchestrator graph.

    Topology:
        memory_node → ambiguity_node → [hitl_wait_node?] → router_node
            → [Send fan-out] → <agent subgraphs> → merge_node → END
    """

    # ── core request ──────────────────────────────────────────────────────────
    query: str
    session_id: str
    context: dict[str, Any]

    # ── routing ───────────────────────────────────────────────────────────────
    agents_to_call: list[str]
    execution_reasoning: str

    # ── sub-agent results (fan-out via Send, merged by _merge_dicts) ─────────
    sub_results: Annotated[dict[str, Any], _merge_dicts]

    # ── final output ──────────────────────────────────────────────────────────
    final_answer: str
    confidence: float

    # ── HITL ──────────────────────────────────────────────────────────────────
    hitl_request_id: str
    hitl_questions: list[str]
    hitl_status: str  # "" | "pending" | "resolved" | "timeout"
