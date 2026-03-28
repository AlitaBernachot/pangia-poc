import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from pydantic import BaseModel

from app.agent.master import agent_graph, get_active_agents
from app.agent.state import AgentState
from app.config import get_settings
from app.db.redis_client import load_session, save_session
from app.db.themes import get_active_theme
from app.security.auth import check_auth
from app.security.rate_limiter import check_rate_limit

router = APIRouter(prefix="/api", tags=["chat"])

# Labels shown in the UI for each sub-agent
_AGENT_LABELS: dict[str, str] = {
    "neo4j_agent": "Neo4j",
    "rdf_agent": "RDF/SPARQL",
    "vector_agent": "Vector",
    "postgis_agent": "PostGIS",
    "mapviz_agent": "Map",
    "data_gouv_agent": "Data.gouv.fr",
    "dataviz_agent": "DataViz",
    "merge": "Synthesiser",
    "router": "Router",
}

# Human-readable labels indexed by the short agent key
_AGENT_UI_LABELS: dict[str, str] = {
    "neo4j": "Neo4j",
    "rdf": "RDF/SPARQL",
    "vector": "Vector",
    "postgis": "PostGIS",
    "map": "Map",
    "data_gouv": "Data.gouv.fr",
    "dataviz": "DataViz",
}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    # Agents the user explicitly wants to query.
    # An empty list (or omitting the field) means "use all active agents".
    selected_agents: list[str] | None = None


class SessionResponse(BaseModel):
    session_id: str


# ─── helpers ──────────────────────────────────────────────────────────────────

def _serialize_message(msg) -> dict:
    return {"role": msg.__class__.__name__, "content": str(msg.content)}


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _node_from_event(event: dict) -> str:
    return event.get("metadata", {}).get("langgraph_node", "")


# ─── Suggestions endpoint ─────────────────────────────────────────────────────

@router.get("/suggestions")
async def suggestions() -> dict:
    theme = get_active_theme()
    return {"suggestions": theme.suggestions}


# ─── SSE streaming endpoint ───────────────────────────────────────────────────

@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> StreamingResponse:
    settings = get_settings()
    session_id = body.session_id or str(uuid.uuid4())

    # ── Authentication (HTTP layer) ────────────────────────────────────────────
    if settings.guardrail_enabled and settings.guardrail_auth_enabled:
        auth_result = check_auth(x_api_key, settings.guardrail_api_key)
        if auth_result.blocked:
            return JSONResponse(
                status_code=401,
                content={"detail": auth_result.reason},
            )

    # ── Rate limiting (HTTP layer) ─────────────────────────────────────────────
    if settings.guardrail_enabled and settings.guardrail_rate_limit_enabled:
        # Use session_id as the rate-limit key; fall back to client IP.
        # Log a warning when neither is available so operators notice the gap.
        if session_id:
            rate_key = session_id
        elif request.client and request.client.host:
            rate_key = request.client.host
        else:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "Rate limiter: no session_id or client IP available; "
                "request will not be rate-limited."
            )
            rate_key = None

        if rate_key:
            rate_result = await check_rate_limit(
                rate_key,
                max_requests=settings.guardrail_rate_limit_max_requests,
                window_seconds=settings.guardrail_rate_limit_window_seconds,
            )
            if rate_result.blocked:
                return JSONResponse(
                    status_code=429,
                    content={"detail": rate_result.reason},
                )

    # Restore history from Redis
    stored = await load_session(session_id)
    _cls_map: dict[str, type] = {"HumanMessage": HumanMessage, "AIMessage": AIMessage}

    history = []
    for m in stored:
        cls = _cls_map.get(m["role"])
        if cls:
            history.append(cls(content=m["content"]))

    history.append(HumanMessage(content=body.message))

    initial_state: AgentState = {
        "messages": history,
        "session_id": session_id,
        "selected_agents": body.selected_agents or [],
        "agents_to_call": [],
        "sub_results": {},
        "geojson": None,
        "dataviz": None,
        "output_decision": None,
        "guardrail_blocked": False,
        "guardrail_message": None,
    }

    async def event_stream() -> AsyncGenerator[str, None]:
        yield _sse({"type": "session", "session_id": session_id})

        full_ai_content = ""
        final_messages = list(history)

        try:
            async for event in agent_graph.astream_events(
                initial_state, version="v2"
            ):
                kind = event.get("event", "")
                node = _node_from_event(event)

                # ── Routing decision ──────────────────────────────────────
                # router_node guarantees at least one agent, but guard anyway.
                # astream_events(version="v2") also fires on_chain_end for
                # inner chains (e.g. the structured-output LLM chain inside
                # router_node). In that case output is a RoutingDecision
                # Pydantic model, not a dict – skip those events.
                if kind == "on_chain_end" and node == "router":
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict):
                        agents = output.get("agents_to_call", [])
                        if agents:
                            yield _sse({"type": "routing", "agents": agents})

                # ── Map agent GeoJSON output ───────────────────────────────
                elif kind == "on_chain_end" and node == "mapviz_agent":
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict):
                        geojson = output.get("geojson")
                        if geojson and isinstance(geojson, dict):
                            yield _sse({"type": "geojson", "data": geojson})

                # ── DataViz agent output ───────────────────────────────────
                elif kind == "on_chain_end" and node == "dataviz_agent":
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict):
                        dataviz = output.get("dataviz")
                        if dataviz and isinstance(dataviz, dict):
                            yield _sse({"type": "dataviz", "data": dataviz})

                # ── Token streaming ───────────────────────────────────────
                elif kind == "on_chat_model_stream":
                    chunk: AIMessageChunk = event["data"]["chunk"]
                    token = chunk.content
                    if not token:
                        continue
                    if node == "merge":
                        # Final synthesis tokens → primary stream
                        full_ai_content += token
                        yield _sse({"type": "token", "content": token})
                    else:
                        # Sub-agent intermediate reasoning
                        label = _AGENT_LABELS.get(node, node)
                        yield _sse(
                            {"type": "agent_token", "agent": label, "content": token}
                        )

                # ── Tool lifecycle ────────────────────────────────────────
                elif kind == "on_tool_start":
                    label = _AGENT_LABELS.get(node, node)
                    yield _sse(
                        {
                            "type": "tool_start",
                            "agent": label,
                            "tool": event.get("name", ""),
                            "input": str(event["data"].get("input", "")),
                        }
                    )

                elif kind == "on_tool_end":
                    label = _AGENT_LABELS.get(node, node)
                    yield _sse(
                        {
                            "type": "tool_end",
                            "agent": label,
                            "tool": event.get("name", ""),
                            "output": str(event["data"].get("output", ""))[:300],
                        }
                    )

        except Exception as exc:
            yield _sse({"type": "error", "content": str(exc)})

        # Persist updated session
        if full_ai_content:
            final_messages.append(AIMessage(content=full_ai_content))

        await save_session(session_id, [_serialize_message(m) for m in final_messages])
        yield _sse({"type": "done", "session_id": session_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/agents")
async def list_agents() -> dict:
    """Return the list of sub-agents currently enabled in the backend configuration.

    The frontend uses this to render the agent-selector toggle UI and to know
    which agents it can include in ``selected_agents`` when calling ``/api/chat``.
    """
    active = get_active_agents()
    return {
        "agents": [
            {"key": k, "label": _AGENT_UI_LABELS.get(k, k)}
            for k in active
        ]
    }
