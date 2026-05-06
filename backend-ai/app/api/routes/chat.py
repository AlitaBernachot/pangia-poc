# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Chat API routes."""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.pangiagent.graph import get_graph
from app.pangiagent.hitl import get_hitl_manager
from app.pangiagent.source_registry import get_registry
from app.pangiagent.sse_stream import drain_queue_to_sse, run_graph_to_queue
from app.pangiagent.state import OrchestratorState
from app.models import ChatRequest, HITLResponse, ChoiceResponse

router = APIRouter()


@router.get("/api/health")
async def health():
    return {"status": "ok", "service": "pangia-v2"}


@router.get("/api/sources")
async def list_sources():
    """Return the list of available agent sources from the source registry."""
    entries = get_registry()
    return {
        "sources": [
            {
                "id": entry.id,
                "label": entry.label,
                "description": entry.description,
            }
            for entry in entries
        ]
    }


@router.post("/api/chat")
async def chat(body: ChatRequest) -> StreamingResponse:
    session_id = body.session_id or str(uuid.uuid4())

    initial_state: OrchestratorState = {
        "query": body.message,
        "session_id": session_id,
        "context": {},
        "selected_sources": body.selected_sources or [],
        "agents_to_call": [],
        "execution_reasoning": "",
        "sub_results": {},
        "final_answer": "",
        "confidence": 0.0,
        "hitl_request_id": "",
        "hitl_questions": [],
        "hitl_status": "",
        "intent": {},
        # NOTE: "messages" intentionally absent — LangGraph checkpointer restores
        # the persisted conversation history automatically.  Passing [] here would
        # overwrite it via the _keep_last reducer and break multi-turn context.
    }

    # Run the graph in an independent background Task so that the long
    # hitl_wait_node pause is NOT cancelled when the HTTP connection's anyio
    # cancel scope is torn down (e.g. client disconnect / proxy timeout).
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    asyncio.create_task(
        run_graph_to_queue(
            get_graph(),
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


@router.post("/api/choice/respond")
async def choice_respond(body: ChoiceResponse):
    """Resolve an agent choice request (e.g. dataset disambiguation)."""
    manager = get_hitl_manager()
    ok = await manager.resolve_choice(body)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail="Choice request not found or already resolved",
        )
    return {"status": "ok", "request_id": body.request_id}
