"""
data.gouv.fr MCP sub-agent.

Specialises in querying the French government open-data platform (data.gouv.fr)
through its Model Context Protocol (MCP) endpoint.  The agent discovers the
available MCP tools at runtime and delegates tool calls to the remote MCP
server via the ``langchain-mcp-adapters`` library.

Exposed as a single async function `run` usable as a LangGraph node.
"""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.agent.state import AgentState
from app.config import get_settings

_SYSTEM_PROMPT = """You are the data.gouv.fr Open-Data Agent of the PangIA GeoIA platform.
Your job is to answer questions by querying the French government's open-data catalogue
(data.gouv.fr) through its MCP interface.

## Capabilities
You have access to tools provided by the data.gouv.fr MCP server that let you:
- Search for datasets by keyword, topic, or organisation.
- Retrieve metadata for specific datasets and their resources.
- Explore available themes, tags, and organisations in the catalogue.
- Fetch resource-level details (file format, URL, description, licence, etc.).

## Guidelines
- Use the search tools first to identify relevant datasets before fetching details.
- Always cite the dataset title, identifier, and URL in your answer.
- Prefer official government sources when multiple datasets match.
- If no relevant dataset is found, say so clearly and suggest alternative search terms.
- Summarise the key fields: title, description, organisation, publication date, licence,
  and direct download links when available.
- Answer in the same language as the user's question.
"""

_MAX_ITERATIONS = 5


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the data.gouv.fr MCP sub-agent ReAct loop."""
    settings = get_settings()

    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    async with MultiServerMCPClient(
        {
            "data_gouv": {
                "url": settings.data_gouv_mcp_url,
                "transport": "streamable_http",
            }
        }
    ) as mcp_client:
        tools = mcp_client.get_tools()

        llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=settings.openai_temperature,
            api_key=settings.openai_api_key,
            streaming=True,
        ).bind_tools(tools)

        tool_map = {t.name: t for t in tools}
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_query),
        ]

        for _ in range(_MAX_ITERATIONS):
            response: AIMessage = await llm.ainvoke(messages)
            messages.append(response)

            if not getattr(response, "tool_calls", None):
                break

            for tc in response.tool_calls:
                tool_fn = tool_map.get(tc["name"])
                if tool_fn is None:
                    result = (
                        f"Unknown tool: {tc['name']}. "
                        f"Available tools: {list(tool_map.keys())}"
                    )
                else:
                    try:
                        result = await tool_fn.ainvoke(tc["args"])
                    except Exception as exc:
                        result = f"Tool error: {exc}"
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=tc["id"])
                )

    result_content = (
        messages[-1].content if messages else "data.gouv.fr agent returned no result."
    )
    return {"sub_results": {"data_gouv": str(result_content)}}
