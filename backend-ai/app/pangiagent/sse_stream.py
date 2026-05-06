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
    output_decision – humanoutput decision: {needs_map, needs_dataviz}
    dataviz         – chart / KPI / table payload from dataviz_node
    geojson         – GeoJSON FeatureCollection from mapviz_node
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
from app.pangiagent.hitl import get_hitl_manager
from app.pangiagent.state import OrchestratorState

logger = logging.getLogger(__name__)

_MAX_AGENT_ANSWER_PREVIEW = 500  # chars sent in agent_end SSE event
_QUEUE_SENTINEL = None  # signals end-of-stream to drain_queue_to_sse


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _node_name(event: dict) -> str:
    return event.get("metadata", {}).get("langgraph_node", "")


def _parent_agent(event: dict) -> str:
    """Return the sub-agent name for events emitted *inside* a compiled subgraph.

    When a sub-agent is compiled as a nested subgraph, LangGraph events carry
    ``checkpoint_ns`` of the form ``"datagouv_mcp_agent:execute_node:…"``.
    The first segment is the sub-agent node name in the orchestrator graph.
    Returns "" when the event does not originate from a registered sub-agent.
    """
    ns: str = event.get("metadata", {}).get("checkpoint_ns", "")
    if not ns:
        return ""
    root = ns.split(":")[0]
    return root if root in _AGENT_NODE_NAMES else ""


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

    # Subscribe to choice_request notifications fired from inside sub-agents
    hitl_manager = get_hitl_manager()
    notif_queue: asyncio.Queue = asyncio.Queue()
    hitl_manager.subscribe(session_id, notif_queue)

    async def _forward_notifications() -> None:
        """Drain the notification queue and push choice_request SSE events."""
        while True:
            item = await notif_queue.get()
            if item is None:
                break
            event_type, payload = item
            if event_type == "choice_request":
                from app.models import ChoiceRequest
                if isinstance(payload, ChoiceRequest):
                    await queue.put(_sse({
                        "type": "choice_request",
                        "request_id": payload.request_id,
                        "agent": payload.agent_name,
                        "items": [i.model_dump() for i in payload.items],
                        "total": payload.total,
                        "original_query": payload.original_query,
                    }))

    notif_task = asyncio.create_task(_forward_notifications())

    try:
        async for event in graph.astream_events(
            initial_state,
            version="v2",
            config={"configurable": {"thread_id": session_id}},
        ):
            kind: str = event.get("event", "")
            node: str = _node_name(event)

            # ── title_node end → session_title ──────────────────────────────
            if kind == "on_chain_end" and node == "title_node":
                out = _output(event)
                title = out.get("session_title", "")
                if title:
                    await queue.put(_sse({"type": "session_title", "title": title}))

            # ── memory_node end ──────────────────────────────────────────────
            if kind == "on_chain_end" and node == "memory_node":
                out = _output(event)
                ctx: dict[str, Any] = out.get("context", {})
                facts = ctx.get("long_term_facts", [])
                previous_turns = ctx.get("previous_turns", [])
                if facts or previous_turns:
                    await queue.put(_sse({
                        "type": "memory_access",
                        "long_term_facts": facts,
                        "previous_turns": len(previous_turns),
                    }))

            # ── intent_node end → emit parsed intent for frontend debug/display ──
            elif kind == "on_chain_end" and node == "intent_node":
                out = _output(event)
                intent = out.get("intent") or (out.get("context") or {}).get("intent")
                if intent:
                    await queue.put(_sse({"type": "intent_parsed", "intent": intent}))

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

            # ── post-processing nodes start ───────────────────────────────────
            # FIXME: this is a bit hacky — we want to emit agent_start for these nodes so they show up in the UI as separate panels, but they aren't really agents.  We should refactor the graph to make this cleaner (e.g. have a single "post_processing_node" with an output field that specifies the type).
            elif kind == "on_chain_start" and node in (
                "synthesis_node",
                "humanoutput_node", "dataviz_node", "mapviz_node",
                "followup_filter_agent",
            ):
                await queue.put(_sse({"type": "agent_start", "agent": node}))

            # ── tool lifecycle inside sub-agents ──────────────────────────────
            elif kind == "on_tool_start":
                agent_name = node if node in _AGENT_NODE_NAMES else _parent_agent(event)
                if agent_name:
                    await queue.put(_sse({
                        "type": "tool_start",
                        "agent": agent_name,
                        "tool": event.get("name", ""),
                    }))

            elif kind == "on_tool_end":
                agent_name = node if node in _AGENT_NODE_NAMES else _parent_agent(event)
                if agent_name:
                    await queue.put(_sse({
                        "type": "tool_end",
                        "agent": agent_name,
                        "tool": event.get("name", ""),
                    }))

            # ── LLM token streaming inside a sub-agent ────────────────────────
            elif kind == "on_chat_model_stream" and node in _AGENT_NODE_NAMES:
                chunk = event.get("data", {}).get("chunk")
                if chunk is not None:
                    token: str = ""
                    if hasattr(chunk, "content"):
                        c = chunk.content
                        if isinstance(c, str):
                            token = c
                        elif isinstance(c, list):
                            # Anthropic-style: list of content blocks
                            for block in c:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    token += block.get("text", "")
                    if token:
                        await queue.put(_sse({"type": "agent_token", "agent": node, "content": token}))
            elif kind == "on_chat_model_stream":
                # Events from inside a compiled subgraph have execute_node as node name —
                # use checkpoint_ns to find the parent sub-agent.
                agent_from_ns = _parent_agent(event)
                if agent_from_ns:
                    chunk = event.get("data", {}).get("chunk")
                    if chunk is not None:
                        token = ""
                        if hasattr(chunk, "content"):
                            c = chunk.content
                            if isinstance(c, str):
                                token = c
                            elif isinstance(c, list):
                                for block in c:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        token += block.get("text", "")
                        if token:
                            await queue.put(_sse({"type": "agent_token", "agent": agent_from_ns, "content": token}))

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
                # ── Rich-data extras: only emit for the agent that just ran ────
                # sub_results may contain accumulated results from previous turns
                # (due to _merge_dicts reducer). Using `node` (the subgraph name)
                # ensures we only emit fresh data, never stale previous-turn data.
                current_result = sub_results.get(node, {})
                if "dataviz" in current_result:
                    await queue.put(_sse({"type": "dataviz", "data": current_result["dataviz"]}))
                if "geojson" in current_result:
                    await queue.put(_sse({"type": "geojson", "data": current_result["geojson"]}))
                if "ogc_layers" in current_result:
                    await queue.put(_sse({"type": "ogc_layer", "layers": current_result["ogc_layers"]}))

            # ── merge_node end → final_answer (fallback when no synthesis node) ──
            # When a synthesis_node is wired, it will emit the real final_answer
            # later.  We still emit here so single-agent / no-output-agents setups
            # work without a synthesis step (synthesis_node will overwrite it).
            elif kind == "on_chain_end" and node == "merge_node":
                out = _output(event)
                answer = out.get("final_answer", "")
                if answer:
                    await queue.put(_sse({
                        "type": "final_answer",
                        "answer": answer,
                        "confidence": out.get("confidence", 0.0),
                    }))
                # No agent_end for merge_node — it's internal and not shown in the UI

            # ── synthesis_node end → final_answer (replaces merge_node answer) ─
            elif kind == "on_chain_end" and node == "synthesis_node":
                out = _output(event)
                answer = out.get("final_answer", "")
                if answer:
                    await queue.put(_sse({
                        "type": "final_answer",
                        "answer": answer,
                        "confidence": 0.9,
                    }))
                await queue.put(_sse({"type": "agent_end", "agent": "synthesis_node", "answer": ""}))

            # ── humanoutput_node end → output_decision ────────────────────────
            elif kind == "on_chain_end" and node == "humanoutput_node":
                out = _output(event)
                decision = out.get("output_decision")
                if decision:
                    await queue.put(_sse({"type": "output_decision", "data": decision}))
                # Forward OGC layers if humanoutput collected them from sub_results
                layers = out.get("ogc_layers")
                if layers:
                    await queue.put(_sse({"type": "ogc_layer", "layers": layers}))
                await queue.put(_sse({"type": "agent_end", "agent": "humanoutput_node", "answer": ""}))

            # ── dataviz_node end → dataviz ────────────────────────────────────
            elif kind == "on_chain_end" and node == "dataviz_node":
                out = _output(event)
                dv = out.get("dataviz")
                if dv is not None:
                    await queue.put(_sse({"type": "dataviz", "data": dv}))
                await queue.put(_sse({"type": "agent_end", "agent": "dataviz_node", "answer": ""}))

            # ── mapviz_node end → geojson + ogc_layers ────────────────────────
            elif kind == "on_chain_end" and node == "mapviz_node":
                out = _output(event)
                gj = out.get("geojson")
                if gj is not None:
                    await queue.put(_sse({"type": "geojson", "data": gj}))
                layers = out.get("ogc_layers")
                if layers:
                    await queue.put(_sse({"type": "ogc_layer", "layers": layers}))
                await queue.put(_sse({"type": "agent_end", "agent": "mapviz_node", "answer": ""}))

    except Exception as exc:
        logger.exception("Unhandled error in run_graph_to_queue")
        await audit.log(session_id, "stream_error", {"error": str(exc)})
        await queue.put(_sse({"type": "error", "message": "An internal error occurred. Please try again."}))

    finally:
        hitl_manager.unsubscribe(session_id, notif_queue)
        await notif_queue.put(None)  # signal the forwarder to stop
        await notif_task

    await queue.put(_sse({"type": "done"}))
    await queue.put(_QUEUE_SENTINEL)


async def drain_queue_to_sse(queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    """Yield SSE chunks from *queue* until the sentinel is received."""
    while True:
        chunk = await queue.get()
        if chunk is _QUEUE_SENTINEL:
            break
        yield chunk
