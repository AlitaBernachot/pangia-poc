# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openinference.instrumentation.langchain import LangChainInstrumentor
from phoenix.otel import register

from app.agents.calculator_agent import CalculatorAgent
from app.agents.rag_agent import RAGAgent
from app.config import get_settings
from app.db import close_engine
from app.agents.orchestrator_agent import build_graph
from app.guardrails import check_ambiguous_intent, check_output_length, check_toxic_input
from app.hitl import get_hitl_manager
from app.memory import close_redis
from app.models import ChatRequest, HITLResponse
from app.sse_stream import stream_graph_events
from app.state import OrchestratorState

logger = logging.getLogger(__name__)


def _setup_phoenix(settings) -> None:
    """Initialise Arize Phoenix tracing for LangChain agents."""
    tracer_provider = register(
        project_name=settings.phoenix_project_name,
        endpoint=settings.phoenix_collector_endpoint,
    )
    LangChainInstrumentor().instrument(tracer_provider=tracer_provider)


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
}

# Build the orchestrator graph at module import time (same pattern as the
# legacy backend).  This also writes Mermaid diagrams to app/mermaid_graph/.
_ORCHESTRATOR_GRAPH = build_graph(_AGENTS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _setup_phoenix(settings)
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

    async def event_stream():
        yield f"data: {{\"type\": \"session\", \"session_id\": \"{session_id}\"}}\n\n"
        async for chunk in stream_graph_events(
            _ORCHESTRATOR_GRAPH,
            initial_state,
            original_query=body.message,
            session_id=session_id,
        ):
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
        raise HTTPException(
            status_code=404,
            detail="HITL request not found or already resolved",
        )
    return {"status": "ok", "request_id": body.request_id}
