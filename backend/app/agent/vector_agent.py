"""
Vector / Chroma sub-agent.

Specialises in semantic similarity search using ChromaDB embeddings.
Exposed as a single async function `run` usable as a LangGraph node.
"""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agent.model_config import build_llm, get_agent_model_config, get_agent_max_iterations
from app.agent.state import AgentState
from app.db.chroma_client import similarity_search, add_documents
from app.db.themes import get_active_theme

_BASE_SYSTEM_PROMPT = """You are the Vector Search Agent of the PangIA GeoIA platform.
Your job is to answer questions using semantic similarity search over a ChromaDB
vector store that contains embedded geographic documents, descriptions, and facts.

## Guidelines
- Use `vector_similarity_search` to find semantically similar content to a query.
- Use `vector_add_documents` only when explicitly asked to store new information.
- Summarise the most relevant results and explain why they match the query.
- If no relevant results are found, say so clearly.
{extra_guidelines}"""


def _build_system_prompt() -> str:
    guidelines = get_active_theme().vector_guidelines.strip()
    extra = f"\n## Theme-specific guidelines\n{guidelines}" if guidelines else ""
    return _BASE_SYSTEM_PROMPT.format(extra_guidelines=extra)


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
async def vector_similarity_search(query: str, n_results: int = 5) -> str:
    """Search ChromaDB for documents semantically similar to the query.
    Returns the top-n matching documents with their distances."""
    try:
        return await similarity_search(query, n_results=n_results)
    except Exception as exc:
        return f"Vector search failed: {exc}"


@tool
async def vector_add_documents(texts: list[str], metadatas: list[dict] | None = None) -> str:
    """Add new text documents to the ChromaDB vector store."""
    try:
        return await add_documents(texts, metadatas=metadatas)
    except Exception as exc:
        return f"Failed to add documents: {exc}"


VECTOR_TOOLS = [vector_similarity_search, vector_add_documents]
_TOOL_MAP = {t.name: t for t in VECTOR_TOOLS}


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the Vector sub-agent ReAct loop."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"vector": f"[Vector agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    llm = build_llm(get_agent_model_config("vector_agent"), streaming=True).bind_tools(VECTOR_TOOLS)

    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    messages = [SystemMessage(content=_build_system_prompt()), HumanMessage(content=user_query)]

    for _ in range(get_agent_max_iterations("vector_agent")):
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
        messages[-1].content if messages else "Vector agent returned no result."
    )
    return {"sub_results": {"vector": str(result_content)}}
