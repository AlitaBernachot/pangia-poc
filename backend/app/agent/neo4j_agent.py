"""
Neo4j Knowledge Graph sub-agent.

Specialises in Cypher queries against the Neo4j graph database.
Exposed as a single async function `run` that can be used as a
LangGraph node.
"""
import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agent.model_config import build_llm, get_agent_model_config
from app.agent.state import AgentState
from app.db.neo4j_client import run_query, run_readonly_query
from app.db.themes import get_active_theme

_BASE_SYSTEM_PROMPT = """You are the Neo4j Knowledge Graph Agent of the PangIA GeoIA platform.
Your job is to answer questions by querying a Neo4j graph database that stores
geographic entities, relationships, and facts using Cypher.

## Graph schema

{schema}

## Guidelines
- For structured questions about specific entities and their relationships, use
  `run_cypher_query` directly with a precise MATCH query.
- Use `search_knowledge_graph` only for broad exploratory searches where you do
  not know the exact entity name.
- When returning sites or geographic entities, **always include all available
  coordinates** (lat, lon, or equivalent properties) in the query results and
  in your answer.
- Always explain what you found and cite the relevant nodes/relationships.
- If the graph contains no relevant data, say so clearly.
{extra_guidelines}"""


def _build_system_prompt() -> str:
    theme = get_active_theme()
    schema = theme.neo4j_schema_prompt.strip()
    guidelines = theme.neo4j_guidelines.strip()
    extra = f"\n## Theme-specific guidelines\n{guidelines}" if guidelines else ""
    return _BASE_SYSTEM_PROMPT.format(
        schema=schema or "(no schema defined for this theme)",
        extra_guidelines=extra,
    )

_MAX_ITERATIONS = 5


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
async def search_knowledge_graph(query: str) -> str:
    """Search the Neo4j graph with a natural-language query via full-text index."""
    cypher = """
    CALL db.index.fulltext.queryNodes('entityIndex', $query)
    YIELD node, score
    WHERE score > 0.5
    OPTIONAL MATCH (node)-[r]->(related)
    RETURN labels(node) AS nodeLabels, node AS nodeProps,
           type(r) AS relType, related AS relatedProps
    LIMIT 10
    """
    try:
        records = await run_query(cypher, {"query": query})
        if not records:
            return "No relevant information found in the knowledge graph."
        return json.dumps(records, default=str)
    except Exception as exc:
        return f"Knowledge graph query failed: {exc}"


@tool
async def run_cypher_query(cypher: str) -> str:
    """Execute a read-only Cypher MATCH query against the Neo4j knowledge graph."""
    try:
        records = await run_readonly_query(cypher)
        if not records:
            return "Query returned no results."
        return json.dumps(records, default=str)
    except Exception as exc:
        return f"Cypher query failed: {exc}"


NEO4J_TOOLS = [search_knowledge_graph, run_cypher_query]
_TOOL_MAP = {t.name: t for t in NEO4J_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the Neo4j sub-agent ReAct loop."""
    llm = build_llm(get_agent_model_config("neo4j_agent"), streaming=True).bind_tools(NEO4J_TOOLS)

    # Extract the latest user query
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

        # Execute each tool call
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
        messages[-1].content if messages else "Neo4j agent returned no result."
    )
    return {"sub_results": {"neo4j": str(result_content)}}
