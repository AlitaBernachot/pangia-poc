import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from pydantic import BaseModel

from app.agent.graph import agent_graph
from app.agent.state import AgentState
from app.db.redis_client import load_session, save_session

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class SessionResponse(BaseModel):
    session_id: str


# ─── helpers ──────────────────────────────────────────────────────────────────

def _serialize_message(msg) -> dict:
    return {"role": msg.__class__.__name__, "content": str(msg.content)}


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


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

    # Append the new user message
    history.append(HumanMessage(content=body.message))

    initial_state: AgentState = {
        "messages": history,
        "session_id": session_id,
    }

    async def event_stream() -> AsyncGenerator[str, None]:
        # First event: emit session_id so the client can persist it
        yield _sse({"type": "session", "session_id": session_id})

        full_ai_content = ""
        final_messages = list(history)

        try:
            async for event in agent_graph.astream_events(
                initial_state, version="v2"
            ):
                kind = event.get("event", "")

                # Stream individual LLM tokens
                if kind == "on_chat_model_stream":
                    chunk: AIMessageChunk = event["data"]["chunk"]
                    token = chunk.content
                    if token:
                        full_ai_content += token
                        yield _sse({"type": "token", "content": token})

                # Tool start notification
                elif kind == "on_tool_start":
                    yield _sse(
                        {
                            "type": "tool_start",
                            "tool": event.get("name", ""),
                            "input": event["data"].get("input", ""),
                        }
                    )

                # Tool end notification
                elif kind == "on_tool_end":
                    yield _sse(
                        {
                            "type": "tool_end",
                            "tool": event.get("name", ""),
                            "output": str(event["data"].get("output", "")),
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
