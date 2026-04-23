# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Chat API routes."""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from app.pangiagent.graph import ORCHESTRATOR_GRAPH
from app.pangiagent.hitl import get_hitl_manager
from app.pangiagent.source_registry import get_registry
from app.pangiagent.sse_stream import drain_queue_to_sse, run_graph_to_queue
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

    # Build the message content. When the user pre-selected specific data
    # sources, append a hint so the orchestrator restricts its delegation.
    message_content = body.message
    if body.selected_sources:
        sources_hint = (
            "\n\n[Use only these data sources: "
            + ", ".join(body.selected_sources)
            + "]"
        )
        message_content += sources_hint

    # deepagents expects a messages-based initial state.
    # The session_id is threaded via additional_kwargs so that sub-agents
    # can use it for HITL choice requests (dataset disambiguation, etc.).
    initial_state = {
        "messages": [
            HumanMessage(
                content=message_content,
                additional_kwargs={"session_id": session_id},
            )
        ]
    }

    # Run the graph in an independent background Task so that long-running
    # sub-agent calls are NOT cancelled when the HTTP connection is closed.
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    asyncio.create_task(
        run_graph_to_queue(
            ORCHESTRATOR_GRAPH,
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
