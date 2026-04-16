# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from pydantic import BaseModel

from app.agent.core.orchestrator import agent_graph
from app.agent.core.state import AgentState
from app.db.redis_client import load_session, save_session

router = APIRouter()

# Labels shown in the UI for each sub-agent
_AGENT_LABELS: dict[str, str] = {
    "neo4j_agent": "Neo4j",
    "rdf_agent": "RDF/SPARQL",
    "vector_chroma_agent": "Vector/Chroma",
    "postgis_agent": "PostGIS",
    "mapviz_agent": "Map",
    "datagouv_mcp_agent": "Data.gouv.fr",
    "dataviz_agent": "DataViz",
    "merge": "Synthesiser",
    "router": "Router",
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


# ─── SSE streaming endpoint ───────────────────────────────────────────────────

@router.post("/chat")
async def chat(body: ChatRequest) -> StreamingResponse:
    session_id = body.session_id or str(uuid.uuid4())

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
        "parsed_intent": None,
        "pending_dataset_choice": None,
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

                # ── Data.gouv dataset-choice (human-in-the-loop) ──────────
                elif kind == "on_chain_end" and node == "datagouv_mcp_agent":
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict):
                        candidates = output.get("pending_dataset_choice")
                        if candidates and isinstance(candidates, list):
                            yield _sse({"type": "dataset_choice", "candidates": candidates})

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
