"""
PostGIS sub-agent.

Specialises in spatial SQL queries against a PostgreSQL/PostGIS database.
Exposed as a single async function `run` usable as a LangGraph node.
"""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from app.agent.state import AgentState
from app.config import get_settings
from app.db.postgis_client import run_spatial_query

SYSTEM_PROMPT = """You are the PostGIS Spatial SQL Agent of the Pangia GeoIA platform.
Your job is to answer geographic and spatial questions by querying a PostGIS-enabled
PostgreSQL database using spatial SQL functions (ST_Contains, ST_Distance,
ST_Intersects, ST_Within, ST_Area, etc.).

Guidelines:
- Write standard PostGIS SQL; always use parameterised queries where possible.
- Only issue SELECT queries; mutations (INSERT/UPDATE/DELETE) are blocked.
- Explain the spatial reasoning behind your query.
- Format numeric results with appropriate units (metres, km², etc.).
- If the query returns no rows, say so clearly.
"""

_MAX_ITERATIONS = 5


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
async def run_postgis_query(sql: str) -> str:
    """Execute a read-only spatial SQL query against the PostGIS database.
    Only SELECT statements are permitted; mutations are blocked at the driver level."""
    try:
        return await run_spatial_query(sql)
    except Exception as exc:
        return f"PostGIS query failed: {exc}"


POSTGIS_TOOLS = [run_postgis_query]
_TOOL_MAP = {t.name: t for t in POSTGIS_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the PostGIS sub-agent ReAct loop."""
    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.openai_model,
        temperature=settings.openai_temperature,
        api_key=settings.openai_api_key,
        streaming=True,
    ).bind_tools(POSTGIS_TOOLS)

    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_query)]

    for _ in range(_MAX_ITERATIONS):
        response: AIMessage = await llm.ainvoke(messages)
        messages.append(response)

        if not getattr(response, "tool_calls", None):
            break

        for tc in response.tool_calls:
            tool_fn = _TOOL_MAP.get(tc["name"])
            if tool_fn is None:
                result = f"Unknown tool: {tc['name']}"
            else:
                try:
                    result = await tool_fn.ainvoke(tc["args"])
                except Exception as exc:
                    result = f"Tool error: {exc}"
            messages.append(
                ToolMessage(content=str(result), tool_call_id=tc["id"])
            )

    result_content = (
        messages[-1].content if messages else "PostGIS agent returned no result."
    )
    return {"sub_results": {"postgis": str(result_content)}}
