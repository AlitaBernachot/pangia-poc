"""
RDF / SPARQL sub-agent.

Specialises in querying a GraphDB (Ontotext) RDF triplestore via SPARQL.
Exposed as a single async function `run` usable as a LangGraph node.
"""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from app.agent.state import AgentState
from app.config import get_settings
from app.db.graphdb_client import (
    run_sparql_select as _db_sparql_select,
    run_sparql_construct as _db_sparql_construct,
)
from app.db.themes import get_active_theme

_BASE_SYSTEM_PROMPT = """You are the RDF/SPARQL Agent of the PangIA GeoIA platform.
Your job is to answer questions by querying a GraphDB RDF triplestore that stores
geospatial ontologies and linked data using SPARQL.

## Ontology schema

{schema}

## Guidelines
- Use `run_sparql_select` for SELECT queries returning tabular data.
- Use `run_sparql_construct` for CONSTRUCT queries returning RDF triples.
- Write valid SPARQL 1.1 queries; use PREFIX declarations as needed.
- Always summarise the results in plain language.
- If no relevant data exists, say so clearly.
"""


def _build_system_prompt() -> str:
    schema = get_active_theme().rdf_schema_prompt.strip()
    return _BASE_SYSTEM_PROMPT.format(schema=schema or "(no schema defined for this theme)")

_MAX_ITERATIONS = 5


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
async def run_sparql_select(sparql: str) -> str:
    """Execute a SPARQL SELECT query against the GraphDB RDF store.
    Returns JSON-formatted results."""
    try:
        return await _db_sparql_select(sparql)
    except Exception as exc:
        return f"SPARQL SELECT failed: {exc}"


@tool
async def run_sparql_construct(sparql: str) -> str:
    """Execute a SPARQL CONSTRUCT query against the GraphDB RDF store.
    Returns Turtle-formatted RDF triples."""
    try:
        return await _db_sparql_construct(sparql)
    except Exception as exc:
        return f"SPARQL CONSTRUCT failed: {exc}"


RDF_TOOLS = [run_sparql_select, run_sparql_construct]
_TOOL_MAP = {t.name: t for t in RDF_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the RDF/SPARQL sub-agent ReAct loop."""
    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.openai_model,
        temperature=settings.openai_temperature,
        api_key=settings.openai_api_key,
        streaming=True,
    ).bind_tools(RDF_TOOLS)

    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    messages = [SystemMessage(content=_build_system_prompt()), HumanMessage(content=user_query)]

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
        messages[-1].content if messages else "RDF agent returned no result."
    )
    return {"sub_results": {"rdf": str(result_content)}}
