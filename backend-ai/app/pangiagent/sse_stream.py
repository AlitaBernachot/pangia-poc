# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""
SSE streaming layer for the deepagents orchestrator graph.

``run_graph_to_queue`` drives the compiled deepagents LangGraph graph via
``astream_events(version="v2")`` inside a **background asyncio Task** that is
*not* bound to the HTTP connection's cancel scope.  SSE chunks are pushed into
an ``asyncio.Queue`` so that the HTTP handler can drain them independently.

``drain_queue_to_sse`` is the async generator used by the HTTP handler to pull
chunks from the queue and yield them as SSE.

The deepagents graph uses a messages-based state (``AgentState``).  Events are
mapped to the SSE event types that the frontend already understands:

SSE event types emitted
-----------------------
    status          – "Processing your request…"
    agent_start     – the main agent called `task` with a sub-agent
    agent_token     – LLM token streamed during sub-agent or main agent turn
    agent_end       – the `task` tool completed for a sub-agent
    final_answer    – the main agent's last non-tool AI message
    done            – stream complete
    error           – unhandled exception
    choice_request  – sub-agent needs the user to pick a dataset
                      (forwarded from HITLManager notifications)
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from langchain_core.messages import AIMessage

from app.pangiagent.audit import get_audit
from app.pangiagent.hitl import get_hitl_manager

logger = logging.getLogger(__name__)

_MAX_AGENT_ANSWER_PREVIEW = 500  # chars sent in agent_end SSE event
_QUEUE_SENTINEL = None           # signals end-of-stream to drain_queue_to_sse


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def run_graph_to_queue(
    graph,
    initial_state: dict,
    queue: asyncio.Queue,
    original_query: str,
    session_id: str,
) -> None:
    """Run the deepagents orchestrator graph and push SSE chunks into *queue*.

    Intended to be launched as an independent ``asyncio.Task`` so that graph
    execution is *not* cancelled when the HTTP connection's anyio cancel scope
    is torn down.

    A ``None`` sentinel is always pushed last to signal completion.

    Parameters
    ----------
    graph:
        The compiled deepagents graph returned by
        :func:`~app.pangiagent.deep_graph.build_deep_graph`.
    initial_state:
        ``{"messages": [HumanMessage(...)]}`` — the standard deepagents input.
    queue:
        ``asyncio.Queue`` consumed by :func:`drain_queue_to_sse`.
    original_query:
        Raw user query string used only for audit logging.
    session_id:
        Current session identifier.
    """
    audit = get_audit()
    await audit.log(session_id, "request_start", {"query": original_query})

    await queue.put(_sse({"type": "status", "message": "Processing your request…"}))

    # Subscribe to choice_request notifications fired from inside sub-agents
    # (e.g. dataset disambiguation in DataGouvMCPAgent).
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

    # Track the current sub-agent being executed via the `task` tool.
    _current_subagent: str = ""
    # Accumulate the last non-tool AI message for the final_answer event.
    _last_ai_content: str = ""

    try:
        async for event in graph.astream_events(initial_state, version="v2"):
            kind: str = event.get("event", "")
            name: str = event.get("name", "")

            # ── Sub-agent delegation start ────────────────────────────────────
            # deepagents uses a `task` tool to call sub-agents.
            if kind == "on_tool_start" and name == "task":
                inputs: dict[str, Any] = event.get("data", {}).get("input", {})
                agent_name: str = inputs.get("agent", "")
                if agent_name:
                    _current_subagent = agent_name
                    await queue.put(_sse({"type": "agent_start", "agent": agent_name}))

            # ── Sub-agent delegation end ──────────────────────────────────────
            elif kind == "on_tool_end" and name == "task":
                completed_agent = _current_subagent or "unknown"
                output: Any = event.get("data", {}).get("output", "")
                answer_preview = str(output)[:_MAX_AGENT_ANSWER_PREVIEW] if output else ""
                await queue.put(_sse({
                    "type": "agent_end",
                    "agent": completed_agent,
                    "answer": answer_preview,
                    # confidence and duration are not available from deepagents'
                    # task tool result; retained for frontend schema compatibility.
                    "confidence": None,
                    "duration_ms": None,
                    "violations": [],
                    "error": None,
                }))
                _current_subagent = ""

            # ── LLM token streaming ───────────────────────────────────────────
            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk is not None:
                    token: str = ""
                    if hasattr(chunk, "content"):
                        c = chunk.content
                        if isinstance(c, str):
                            token = c
                        elif isinstance(c, list):
                            for block in c:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    token += block.get("text", "")
                    if token:
                        agent_label = _current_subagent or "orchestrator"
                        await queue.put(_sse({
                            "type": "agent_token",
                            "agent": agent_label,
                            "content": token,
                        }))

            # ── Track the last complete AI response (for final_answer) ────────
            # We want the last non-tool-call AI message from the main agent.
            elif kind == "on_chat_model_end":
                response: Any = event.get("data", {}).get("output")
                if response and isinstance(response, AIMessage):
                    # Only capture responses that are not tool calls (i.e., final text).
                    if not getattr(response, "tool_calls", None):
                        content = response.content
                        if isinstance(content, str) and content:
                            _last_ai_content = content
                        elif isinstance(content, list):
                            text_parts = [
                                b.get("text", "")
                                for b in content
                                if isinstance(b, dict) and b.get("type") == "text"
                            ]
                            combined = "".join(text_parts)
                            if combined:
                                _last_ai_content = combined

    except Exception as exc:
        logger.exception("Unhandled error in run_graph_to_queue")
        await audit.log(session_id, "stream_error", {"error": str(exc)})
        await queue.put(_sse({
            "type": "error",
            "message": "An internal error occurred. Please try again.",
        }))

    finally:
        hitl_manager.unsubscribe(session_id, notif_queue)
        await notif_queue.put(None)  # signal the forwarder to stop
        await notif_task

    # Emit the final answer after the full graph has run.
    if _last_ai_content:
        await queue.put(_sse({
            "type": "final_answer",
            "answer": _last_ai_content,
            "confidence": 0.9,
        }))

    await queue.put(_sse({"type": "done"}))
    await queue.put(_QUEUE_SENTINEL)


async def drain_queue_to_sse(queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    """Yield SSE chunks from *queue* until the sentinel is received."""
    while True:
        chunk = await queue.get()
        if chunk is _QUEUE_SENTINEL:
            break
        yield chunk
