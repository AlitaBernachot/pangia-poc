"""
data.gouv.fr MCP sub-agent.

Specialises in querying the French government open-data platform (data.gouv.fr)
through its Model Context Protocol (MCP) endpoint.  The agent discovers the
available MCP tools at runtime and delegates tool calls to the remote MCP
server via the ``langchain-mcp-adapters`` library.

Exposed as a single async function `run` usable as a LangGraph node.
"""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
import json

from app.agent.model_config import build_llm, get_agent_model_config, get_agent_max_iterations
from app.agent.core.state import AgentState
from app.config import get_settings
from libs.filereader import fetch_and_parse

_SYSTEM_PROMPT = """You are the data.gouv.fr Open-Data Agent of the PangIA GeoIA platform.
Your job is to answer questions by querying the French government's open-data catalogue
(data.gouv.fr) through its MCP interface.

## Capabilities
You have access to:
- MCP tools from the data.gouv.fr server: search datasets, retrieve metadata, query tabular
  data via `query_resource_data`, get resource info via `get_resource_info`.
- A local tool `fetch_resource_file` that downloads and parses the **complete raw file**
  (CSV, JSON, GeoJSON) from a direct URL and returns all rows.

## Two modes — choose based on the user's intent

### 1. Metadata / discovery questions
*"What datasets exist about X?", "Who publishes data on Y?", "Is there open data for Z?"*
→ Search, retrieve dataset metadata, cite title + URL + licence. Stop here.

### 2. Data content questions
*"List the X for year Y", "How many Z?", "Give me the records where …", "Affiche les données"*
→ You MUST fetch the actual data. Choose the right strategy:

#### Strategy A — Preview (user asks for a sample / overview / few examples)
- Use `query_resource_data` with `page_size=20` to show structure.
- **Always state explicitly** it is a preview: e.g. "Voici un aperçu des 20 premières
  lignes (N enregistrements au total)."

#### Strategy B — Full retrieval (user asks to "display", "show", "give me all the data")
- Call `get_resource_info` on the resource to obtain the direct download URL (`url` field).
- Then call `fetch_resource_file` with that URL to download and parse the complete file.
- **If the dataset exposes BOTH a tabular file (CSV/JSON) AND a GeoJSON file**, call
  `fetch_resource_file` **twice** — once for the tabular file, once for the GeoJSON.
  Both will be used: the table for the data panel, the GeoJSON for the map.
- **Do NOT call `query_resource_data` at all** — the full file supersedes any preview.
- **Do NOT list any rows or examples** in your text response — the data is displayed in
  the interactive table below your message.
- **You MUST end with a short non-empty text message** containing at minimum: dataset
  title, total record count, source URL, and licence.
  Example: "Le dataset **Capteur d'ondes électromagnétiques** contient **33 enregistrements**
  (CSV, Licence Ouverte). [Source](https://data.gouv.fr/...)"

When the intent is ambiguous, default to **Strategy B** (full retrieval).

## Guidelines
- Use the search tools first to identify relevant datasets before fetching details.
- Always cite the dataset title, identifier, and URL in your answer.
- Prefer official government sources when multiple datasets match.
- If no relevant dataset is found, say so clearly and suggest alternative search terms.
- Summarise the key metadata fields: title, description, organisation, publication date,
  licence, and direct download links when available.
- Answer in the same language as the user's question.
- Be concise: answer in the fewest words needed. No preambles, no repetition.
"""

# ─── Local tool ───────────────────────────────────────────────────────────────

@tool
async def fetch_resource_file(url: str) -> str:
    """
    Download and parse a complete data file from a direct URL.
    Supports CSV, JSON, and GeoJSON formats.
    Returns all rows as a JSON string. Use this for full data retrieval
    instead of paginating through query_resource_data.
    """
    parsed = await fetch_and_parse(url)
    if parsed.error:
        return f"Error fetching file: {parsed.error}"
    payload: dict = {
        "format": parsed.format,
        "total_rows": parsed.total_rows,
        "columns": parsed.columns,
        "rows": parsed.rows,
    }
    # Include raw parsed object for GeoJSON so mapviz_agent can use it directly.
    if parsed.format == "geojson" and parsed.raw is not None:
        payload["raw"] = parsed.raw
    return json.dumps(payload, ensure_ascii=False, default=str)


# ─── Node function ─────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the data.gouv.fr MCP sub-agent ReAct loop."""
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"data_gouv": f"[data.gouv agent unavailable: {exc}]"}}


async def _run(state: AgentState) -> dict:
    settings = get_settings()

    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    mcp_client = MultiServerMCPClient(
        {
            "data_gouv": {
                "url": settings.data_gouv_mcp_url,
                "transport": "streamable_http",
            }
        }
    )
    tools = await mcp_client.get_tools()
    all_tools = [*tools, fetch_resource_file]

    llm = build_llm(get_agent_model_config("data_gouv_agent"), streaming=True).bind_tools(all_tools)

    tool_map = {t.name: t for t in all_tools}
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_query),
    ]

    for _ in range(get_agent_max_iterations("data_gouv_agent")):
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

    # Collect ALL successful fetch_resource_file results from tool messages.
    # Separate tabular files (csv/json) from geojson files so both pipelines
    # can be fed independently.
    tabular_data: dict | None = None   # first csv/json result found
    geojson_data: dict | None = None   # first geojson result found

    for msg in messages:
        if not (isinstance(msg, ToolMessage) and isinstance(msg.content, str) and msg.content):
            continue
        try:
            parsed = json.loads(msg.content)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(parsed, dict) or "rows" not in parsed or "columns" not in parsed:
            continue

        fmt = parsed.get("format", "")
        if fmt == "geojson":
            if geojson_data is None:
                geojson_data = parsed
        else:
            if tabular_data is None:
                tabular_data = parsed

    # If only a GeoJSON was fetched (no separate CSV), fall back to using it
    # for the table as well (its rows contain feature properties).
    if tabular_data is None and geojson_data is not None:
        tabular_data = geojson_data

    # Build result_content: prefer the last non-empty AIMessage content.
    # Fall back to an auto-generated summary from fetched data so the synthesis
    # agent always receives a meaningful non-empty sub_results entry.
    result_content: str = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            c = msg.content
            text = c if isinstance(c, str) else " ".join(
                p.get("text", "") for p in c if isinstance(p, dict)
            )
            text = text.strip()
            if text:
                result_content = text
                break

    # If the LLM produced no usable text (empty final message), build a
    # minimal summary from the fetched data so the synthesis agent isn't blind.
    if not result_content and tabular_data is not None:
        total = tabular_data.get("total_rows", len(tabular_data["rows"]))
        fmt_label = tabular_data.get("format", "data").upper()
        geo_note = " + GeoJSON" if geojson_data is not None else ""
        result_content = (
            f"Données récupérées depuis data.gouv.fr : {total} enregistrements "
            f"({fmt_label}{geo_note}). Les données complètes sont affichées dans le tableau interactif."
        )
    elif not result_content:
        result_content = "data.gouv.fr agent returned no result."

    state_update: dict = {"sub_results": {"data_gouv": result_content}}

    # ── Populate state["geojson"] from the GeoJSON fetch ──────────────────────
    if geojson_data is not None:
        raw_gj = geojson_data.get("raw")
        if isinstance(raw_gj, dict) and raw_gj.get("type") in ("FeatureCollection", "Feature"):
            state_update["geojson"] = raw_gj

    # ── Populate state["dataviz"] from the tabular fetch ──────────────────────
    if tabular_data is not None:
        fmt = tabular_data.get("format", "data")
        columns = tabular_data["columns"]
        all_rows = tabular_data["rows"]
        total = tabular_data.get("total_rows", len(all_rows))
        rows_as_lists = [
            [str(row.get(col, "")) for col in columns]
            for row in all_rows
        ]
        state_update["dataviz"] = {
            "charts": [],
            "kpis": [],
            "tables": [{
                "title": f"Données complètes ({total} enregistrements) [{fmt.upper()}]",
                "columns": columns,
                "rows": rows_as_lists,
            }],
        }

    return state_update
