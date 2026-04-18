# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""
SSE streaming layer for the V2 orchestrator graph.

``run_graph_to_queue`` drives the compiled LangGraph graph via
``astream_events(version="v2")`` inside a **background asyncio Task**
that is *not* bound to the HTTP connection's cancel scope.  SSE chunks
are pushed into an ``asyncio.Queue`` so that the HTTP handler can drain
them independently.  This decoupling is essential for ``hitl_wait_node``,
which needs to survive for minutes while waiting for human input even if
the original SSE connection is interrupted.

``drain_queue_to_sse`` is the async generator used by the HTTP handler to
pull chunks from the queue and yield them as SSE.

SSE event types emitted:
    status          – "Processing your request…"
    memory_access   – LTM facts / STM data loaded
    hitl_request    – ambiguous query; frontend should show HITL modal
    hitl_resolved   – human responded; continuing with clarified query
    hitl_timeout    – no human response within timeout
    routing_plan    – LLM selected these agents (+ reasoning)
    agent_start     – a sub-agent subgraph began
    agent_end       – a sub-agent subgraph completed (answer, confidence, …)
    final_answer    – merged answer from all agents
    done            – stream complete
    error           – unhandled exception
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from app.pangiagent.audit import get_audit
from app.pangiagent.agents.orchestrator_agent import _AGENT_NODE_NAMES
from app.pangiagent.state import OrchestratorState

logger = logging.getLogger(__name__)

_MAX_AGENT_ANSWER_PREVIEW = 500  # chars sent in agent_end SSE event
_QUEUE_SENTINEL = None  # signals end-of-stream to drain_queue_to_sse


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _node_name(event: dict) -> str:
    return event.get("metadata", {}).get("langgraph_node", "")


def _output(event: dict) -> dict:
    data = event.get("data", {})
    out = data.get("output", {})
    return out if isinstance(out, dict) else {}


async def run_graph_to_queue(
    graph,
    initial_state: OrchestratorState,
    queue: asyncio.Queue,
    original_query: str,
    session_id: str,
) -> None:
    """Run the orchestrator graph and push SSE chunks into *queue*.

    Intended to be launched as an independent ``asyncio.Task`` so that the
    graph execution (including the long ``hitl_wait_node`` pause) is *not*
    cancelled when the HTTP connection's cancel scope is torn down.

    A ``None`` sentinel is always pushed last to signal completion.
    """
    audit = get_audit()
    await audit.log(session_id, "request_start", {"query": original_query})

    await queue.put(_sse({"type": "status", "message": "Processing your request…"}))

    try:
        async for event in graph.astream_events(initial_state, version="v2"):
            kind: str = event.get("event", "")
            node: str = _node_name(event)

            # ── memory_node end ──────────────────────────────────────────────
            if kind == "on_chain_end" and node == "memory_node":
                out = _output(event)
                ctx: dict[str, Any] = out.get("context", {})
                facts = ctx.get("long_term_facts", [])
                stm = ctx.get("short_term", {})
                if facts or stm:
                    await queue.put(_sse({
                        "type": "memory_access",
                        "long_term_facts": facts,
                        "short_term": stm,
                    }))

            # ── ambiguity_node end → emit hitl_request before wait starts ───
            elif kind == "on_chain_end" and node == "ambiguity_node":
                out = _output(event)
                if out.get("hitl_status") == "pending":
                    await queue.put(_sse({
                        "type": "hitl_request",
                        "request_id": out.get("hitl_request_id", ""),
                        "questions": out.get("hitl_questions", []),
                        "original_query": original_query,
                    }))

            # ── hitl_wait_node end → resolved or timeout ─────────────────────
            elif kind == "on_chain_end" and node == "hitl_wait_node":
                out = _output(event)
                status = out.get("hitl_status", "")
                if status == "resolved":
                    await queue.put(_sse({
                        "type": "hitl_resolved",
                        "clarified_query": out.get("query", ""),
                    }))
                elif status == "timeout":
                    await queue.put(_sse({
                        "type": "hitl_timeout",
                        "message": out.get("final_answer", ""),
                    }))

            # ── router_node end → routing_plan ───────────────────────────────
            elif kind == "on_chain_end" and node == "router_node":
                out = _output(event)
                agents = out.get("agents_to_call", [])
                if agents:
                    await queue.put(_sse({
                        "type": "routing_plan",
                        "agents": agents,
                        "reasoning": out.get("execution_reasoning", ""),
                    }))

            # ── sub-agent subgraph start ──────────────────────────────────────
            elif kind == "on_chain_start" and node in _AGENT_NODE_NAMES:
                await queue.put(_sse({"type": "agent_start", "agent": node}))

            # ── sub-agent subgraph end ────────────────────────────────────────
            elif kind == "on_chain_end" and node in _AGENT_NODE_NAMES:
                out = _output(event)
                sub_results: dict[str, Any] = out.get("sub_results", {})
                for agent_name, result in sub_results.items():
                    await queue.put(_sse({
                        "type": "agent_end",
                        "agent": agent_name,
                        "answer": (result.get("answer") or "")[:_MAX_AGENT_ANSWER_PREVIEW],
                        "confidence": result.get("confidence", 0.0),
                        "duration_ms": result.get("duration_ms", 0),
                        "violations": result.get("violations", []),
                        "error": result.get("error"),
                    }))
                    # ── Rich-data extras forwarded from AgentOutput.state ──────
                    if "dataviz" in result:
                        await queue.put(_sse({"type": "dataviz", "data": result["dataviz"]}))
                    if "geojson" in result:
                        await queue.put(_sse({"type": "geojson", "data": result["geojson"]}))
                    if "pending_dataset_choice" in result and result["pending_dataset_choice"]:
                        await queue.put(_sse({
                            "type": "dataset_choice",
                            "candidates": result["pending_dataset_choice"],
                            "total": result.get("pending_dataset_choice_total"),
                        }))

            # ── merge_node end → final_answer ─────────────────────────────────
            elif kind == "on_chain_end" and node == "merge_node":
                out = _output(event)
                await queue.put(_sse({
                    "type": "final_answer",
                    "answer": out.get("final_answer", ""),
                    "confidence": out.get("confidence", 0.0),
                }))

    except Exception as exc:
        logger.exception("Unhandled error in run_graph_to_queue")
        await audit.log(session_id, "stream_error", {"error": str(exc)})
        await queue.put(_sse({"type": "error", "message": "An internal error occurred. Please try again."}))

    await queue.put(_sse({"type": "done"}))
    await queue.put(_QUEUE_SENTINEL)


async def drain_queue_to_sse(queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    """Yield SSE chunks from *queue* until the sentinel is received."""
    while True:
        chunk = await queue.get()
        if chunk is _QUEUE_SENTINEL:
            break
        yield chunk
