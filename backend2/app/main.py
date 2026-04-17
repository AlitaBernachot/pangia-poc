# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.agents.calculator_agent import CalculatorAgent
from app.agents.rag_agent import RAGAgent
from app.config import get_settings
from app.db import close_engine
from app.guardrails import check_ambiguous_intent, check_output_length, check_toxic_input
from app.hitl import get_hitl_manager
from app.memory import close_redis
from app.models import ChatRequest, HITLResponse
from app.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

# Build the agent registry (pre-wired with guardrails)
_AGENTS = {
    "rag_agent": RAGAgent(
        pre_guardrails=[check_toxic_input, check_ambiguous_intent],
        post_guardrails=[check_output_length],
    ),
    "calculator_agent": CalculatorAgent(
        pre_guardrails=[check_toxic_input],
    ),
}

_ORCHESTRATOR = Orchestrator(_AGENTS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_engine()
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_title,
        version=settings.app_version,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return application


app = create_app()


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "pangia-v2"}


@app.post("/api/chat")
async def chat(body: ChatRequest) -> StreamingResponse:
    session_id = body.session_id or str(uuid.uuid4())

    async def event_stream():
        yield f"data: {{\"type\": \"session\", \"session_id\": \"{session_id}\"}}\n\n"
        async for chunk in _ORCHESTRATOR.run(body.message, session_id):
            yield chunk

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/hitl/respond")
async def hitl_respond(body: HITLResponse):
    manager = get_hitl_manager()
    ok = await manager.respond(body.request_id, body.clarified_query)
    if not ok:
        raise HTTPException(status_code=404, detail="HITL request not found or already resolved")
    return {"status": "ok", "request_id": body.request_id}
