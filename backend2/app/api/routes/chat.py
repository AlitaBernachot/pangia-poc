# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Chat API routes."""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.pangiagent.agents.calculator_agent import CalculatorAgent
from app.pangiagent.agents.orchestrator_agent import build_graph
from app.pangiagent.agents.rag_agent import RAGAgent
from app.pangiagent.agents.summary_agent import SummaryAgent
from app.pangiagent.guardrails import check_ambiguous_intent, check_output_length, check_toxic_input
from app.pangiagent.hitl import get_hitl_manager
from app.pangiagent.sse_stream import drain_queue_to_sse, run_graph_to_queue
from app.pangiagent.state import OrchestratorState
from app.models import ChatRequest, HITLResponse

router = APIRouter()

# ── Agent registry ─────────────────────────────────────────────────────────────
# Each agent is wired with its guardrails here, then compiled into the graph.

_AGENTS = {
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

# Build the orchestrator graph at module import time.
# Also writes Mermaid diagrams to app/pangiagent/mermaid_graph/.
_ORCHESTRATOR_GRAPH = build_graph(_AGENTS)


@router.get("/api/health")
async def health():
    return {"status": "ok", "service": "pangia-v2"}


@router.post("/api/chat")
async def chat(body: ChatRequest) -> StreamingResponse:
    session_id = body.session_id or str(uuid.uuid4())

    initial_state: OrchestratorState = {
        "query": body.message,
        "session_id": session_id,
        "context": {},
        "agents_to_call": [],
        "execution_reasoning": "",
        "sub_results": {},
        "final_answer": "",
        "confidence": 0.0,
        "hitl_request_id": "",
        "hitl_questions": [],
        "hitl_status": "",
    }

    # Run the graph in an independent background Task so that the long
    # hitl_wait_node pause is NOT cancelled when the HTTP connection's anyio
    # cancel scope is torn down (e.g. client disconnect / proxy timeout).
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    asyncio.create_task(
        run_graph_to_queue(
            _ORCHESTRATOR_GRAPH,
            initial_state,
            queue,
            original_query=body.message,
            session_id=session_id,
        )
    )

    async def event_stream():
        yield f"data: {{\"type\": \"session\", \"session_id\": \"{session_id}\"}}\n\n"
        async for chunk in drain_queue_to_sse(queue):
            yield chunk

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/hitl/respond")
async def hitl_respond(body: HITLResponse):
    manager = get_hitl_manager()
    ok = await manager.respond(body.request_id, body.clarified_query)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail="HITL request not found or already resolved",
        )
    return {"status": "ok", "request_id": body.request_id}
