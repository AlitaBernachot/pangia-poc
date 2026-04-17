# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""
GeoNetwork MCP sub-agent.

Specialises in querying a GeoNetwork metadata catalogue through its
Model Context Protocol (MCP) endpoint.  The agent discovers the available
MCP tools at runtime and delegates tool calls to the remote MCP server via
the ``langchain-mcp-adapters`` library.

Use :func:`make_run` to create a node function bound to a specific MCP
endpoint URL and connector key, allowing multiple GeoNetwork instances to
be registered as independent agents.
"""
import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.agent.model_config import build_llm, get_agent_model_config, get_agent_max_iterations
from app.agent.core.state import AgentState

_SYSTEM_PROMPT = """You are the GeoNetwork Metadata Catalogue Agent of the PangIA GeoIA platform.
Your job is to answer questions by querying a GeoNetwork metadata catalogue through its MCP interface.

## Capabilities
You have access to tools provided by the GeoNetwork MCP server that let you:
- Search for geospatial datasets, maps, and metadata records by keyword, topic, or geographic area.
- Retrieve detailed metadata for specific records (title, abstract, CRS, bounding box, extent, licence…).
- Explore available categories, keywords, and organisations in the catalogue.
- Fetch OGC service links (WMS, WFS, WCS, WMTS) associated with a record.

## Mandatory workflow — ALWAYS follow these steps in order
1. **Search first**: ALWAYS call the search tool with the user's keyword/title before anything else.
   Never skip this step, even if the user provides something that looks like an identifier.
2. **Extract UUID**: From the search results, identify the matching record and extract its UUID
   (a UUID looks like `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`). Titles, filenames, codes
   (e.g. "2322814_ALL_LATEST") are NOT UUIDs — never pass them to `get_record`.
3. **Fetch details (optional)**: Only call `get_record` with the UUID you found in step 2 if you
   need extra fields not already present in the search response.

## Guidelines
- If `get_record` returns a 404 or "Resource not found" error, do NOT retry — instead report
  the information already retrieved from the search results and note that the full record is unavailable.
- The search results often contain enough information (title, abstract, bounding box, links);
  only call `get_record` when you specifically need extra details not present in the search response.
- Always cite the metadata record title, UUID, and direct link in your answer.
- Summarise the key metadata fields: title, abstract, spatial extent, coordinate reference system,
  publication date, organisation, licence, and available service links.
- Prefer records with an open licence and machine-readable service endpoints when available.
- If no relevant record is found, say so clearly and suggest alternative search terms or broader keywords.
- Answer in the same language as the user's question.
- Be concise: answer in the fewest words needed. No preambles, no repetition.

## OGC API Features integration
After retrieving a record, inspect its distribution info for online resources.
If an online resource (`cit:CI_OnlineResource`) has a `cit:protocol` field
containing "OGC API Features" (any casing or variant), extract:
- `url`: the value of `cit:linkage > gco:CharacterString > #text`
- `name`: the value of `cit:name > gco:CharacterString > #text`
- `title`: the record's human-readable title

## Output format
Your **final message** must ALWAYS be a single valid JSON object with no surrounding text:
{"text": "<concise summary of the record>", "ogc_layers": [{"url": "<url>", "name": "<layer name>", "title": "<record title>"}]}

When no OGC API Features link exists in the record, omit the `ogc_layers` key entirely.
Return `{"text": "<summary>"}` only.
"""

# ─── Factory ──────────────────────────────────────────────────────────────────

def make_run(mcp_url: str, connector_key: str):
    """Return a LangGraph node function bound to a specific GeoNetwork MCP endpoint.

    Parameters
    ----------
    mcp_url:
        Full URL of the GeoNetwork MCP endpoint
        (e.g. ``"http://geonetwork.example.com/geonetwork/srv/api/mcp"``).
    connector_key:
        Agent key used as the ``sub_results`` entry and MCP client name.
        Must match the ``connector`` field of the corresponding
        :class:`~app.agent.core.source_registry.SourceEntry`.
    """

    async def run(state: AgentState) -> dict:
        try:
            return await _run(state, mcp_url, connector_key)
        except Exception as exc:  # noqa: BLE001
            return {"sub_results": {connector_key: f"[GeoNetwork agent unavailable: {exc}]"}}

    run.__name__ = f"geonetwork_mcp_run_{connector_key}"
    return run


# ─── Core logic ───────────────────────────────────────────────────────────────

async def _run(state: AgentState, mcp_url: str, connector_key: str) -> dict:
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    mcp_client = MultiServerMCPClient(
        {
            connector_key: {
                "url": mcp_url,
                "transport": "streamable_http",
            }
        }
    )
    tools = await mcp_client.get_tools()

    llm = build_llm(get_agent_model_config("geonetwork_mcp_agent"), streaming=True).bind_tools(tools)

    tool_map = {t.name: t for t in tools}
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_query),
    ]

    for _ in range(get_agent_max_iterations("geonetwork_mcp_agent")):
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
                except Exception as exc:  # noqa: BLE001
                    err_str = str(exc)
                    if "404" in err_str or "resource_not_found" in err_str:
                        result = (
                            f"Tool '{tc['name']}' returned 404 Not Found for the given identifier. "
                            "This record does not exist in the catalogue. "
                            "Do not retry — use the information already retrieved from search results instead."
                        )
                    else:
                        result = f"Tool error ({tc['name']}): {exc}"
            messages.append(
                ToolMessage(content=str(result), tool_call_id=tc["id"])
            )

    result_content = (
        messages[-1].content if messages else "GeoNetwork agent returned no result."
    )

    # Parse structured JSON output produced by the LLM
    ogc_layers: list[dict] | None = None
    text_result = str(result_content)
    try:
        parsed = json.loads(result_content)
        if isinstance(parsed, dict):
            text_result = parsed.get("text", text_result)
            layers = parsed.get("ogc_layers")
            if isinstance(layers, list) and layers:
                ogc_layers = layers
    except (json.JSONDecodeError, ValueError):
        pass

    return {
        "sub_results": {connector_key: text_result},
        "ogc_layers": ogc_layers,
    }
