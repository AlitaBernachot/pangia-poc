# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

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
import ast
import json
import re

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

## Three modes — choose based on the user's intent

### 0. Disambiguation (PRIORITY RULE — check FIRST before doing anything else)
When a search returns **2 or more datasets with different titles**, apply the following
decision logic **in order**:

**Step A — Auto-select ONLY if one of these two conditions is strictly true:**
1. The user's message contains a dataset UUID (`6229416f1440a9f8fb3e0c47` or `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`) that matches a result, OR
2. The user's message contains a string delimited by quotes (e.g. `"Titre exact"`) whose
   content is **character-for-character identical** (same casing, same spaces) to one of the
   result titles.

If condition 1 or 2 is true, silently select that dataset and proceed.

**In all other cases — including unquoted titles, partial names, or keywords —
go to Step B and ask.** A search query is not a dataset identifier.

**Step B — Ask the user when no strict match was found.**

**Step B — Ask the user only if no match was found in Step A.**
If the user's message gives no hint about which dataset to use, stop and ask:

"J'ai trouvé **N datasets** correspondant à votre recherche. Lequel souhaitez-vous utiliser ?

1. **[Titre 1]** — [description courte, max 1 phrase] *(Organisation: [org])*
2. **[Titre 2]** — [description courte, max 1 phrase] *(Organisation: [org])*
...

Veuillez me préciser le numéro ou le titre exact du dataset souhaité."

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

#### Strategy C — Filtered retrieval (user asks for records matching a condition)
*"Montre les capteurs qui ne sont pas en maintenance", "liste les stations actives", "records where status = X"*

**IMPORTANT: `query_resource_data` is NEVER used to return data to the user.** It is only
used for schema discovery (Step 1 below) when you cannot guess the column name.

Step 1 — Discover the exact column name (skip if you can guess it):
Common column names for status/state fields: `statut`, `etat`, `état`, `status`, `state`.
If the filter condition maps naturally to one of these, go directly to Step 2.
Otherwise, call `query_resource_data` with `page_size=1` **only to read the column headers**
— do NOT use its output as the answer to the user.

Step 2 — Mandatory: fetch the file with filter applied:
- Call `get_resource_info` to obtain the direct download URL.
- Call `fetch_resource_file` with the filter parameters:
  - `filter_column`: column name from Step 1 (e.g. `statut`).
  - `filter_value`: the **bare keyword** — strip any leading article or preposition
    ("en", "hors", "de", "au"…) **before passing**. E.g. user says "en maintenance" →
    pass `"maintenance"`, not `"en maintenance"`.
  - `filter_op`: choose based on these rules:
    - Default to `"contains"` / `"not_contains"`.
    - Use `"equals"` / `"not_equals"` ONLY if the user explicitly quoted the exact cell
      value (e.g. the user typed `"MAINTENANCE"` with surrounding quotes).
- **If the dataset also has a GeoJSON resource**, call `fetch_resource_file` a second time
  on the GeoJSON URL with the same filter parameters so the map only shows matching features.
- **Only the matching rows** are returned and displayed in the table.
- In your text response, state: dataset title, how many records match out of the total,
  the filter applied, source URL and licence.

Examples:
- "capteurs PAS en maintenance" → filter_op="not_contains", filter_value="maintenance"
- "capteurs actifs" → filter_op="contains", filter_value="actif"
- user typed `"MAINTENANCE"` (quoted) → filter_op="equals", filter_value="MAINTENANCE"

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

# ─── Dataset candidate extraction helper ──────────────────────────────────────

_MAX_DESCRIPTION_LENGTH = 250
_NUMBERED_ENTRY_RE = re.compile(r'^\s*\d+\.\s+(.+)')


def _parse_text_search_results(text: str) -> list[dict]:
    """Parse the plain-text MCP search result format into candidate dicts.

    Handles blocks like::

        1. Dataset Title
           ID: <uuid>
           Organization: Org Name
           Tags: tag1, tag2
           URL: https://...
    """
    results: list[dict] = []
    current: dict | None = None

    for line in text.splitlines():
        m = _NUMBERED_ENTRY_RE.match(line)
        if m:
            if current is not None:
                results.append(current)
            current = {"title": m.group(1).strip(), "id": "", "organization": "", "description": "", "url": ""}
            continue

        if current is None:
            continue

        s = line.strip()
        if not s:
            continue
        if s.startswith("ID:"):
            current["id"] = s[3:].strip()
        elif s.startswith("Organization:"):
            current["organization"] = s[13:].strip()
        elif s.startswith("URL:"):
            current["url"] = s[4:].strip()
        elif s.startswith("Tags:") and not current["description"]:
            current["description"] = s[5:].strip()

    if current is not None:
        results.append(current)
    return results


_UUID_RE = re.compile(
    r'\b[0-9a-f]{24}\b'                           # 24-char hex (data.gouv format)
    r'|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',  # RFC 4122
    re.IGNORECASE,
)
_QUOTED_TITLE_RE = re.compile(r'["\u00ab\u201c\u2018](.*?)["\u00bb\u201d\u2019]')


def _user_identifies_dataset(user_query: str, candidates: list[dict]) -> bool:
    """Return True only if *user_query* unambiguously identifies one candidate.

    Accepted signals (both must strictly match a candidate):
    - A UUID present in the query that equals the ``id`` of a candidate.
    - A quoted string whose content is character-for-character identical to the
      ``title`` of a candidate.
    """
    candidate_ids = {c.get("id", "").lower() for c in candidates if c.get("id")}
    for uuid in _UUID_RE.findall(user_query):
        if uuid.lower() in candidate_ids:
            return True

    candidate_titles = {c.get("title", "") for c in candidates if c.get("title")}
    for quoted in _QUOTED_TITLE_RE.findall(user_query):
        if quoted in candidate_titles:
            return True

    return False


def _extract_dataset_candidates(messages, search_tool_call_ids: set[str]) -> list[dict]:
    """Parse search tool results from the ReAct loop and return dataset candidates.

    Only inspects ToolMessages whose ``tool_call_id`` is in *search_tool_call_ids*,
    i.e. responses to ``search_datasets`` calls.  This prevents resource lists
    (from ``get_resource_info``, ``list_resources``, etc.) from being mistaken
    for dataset candidates.

    Handles three response formats:
    - MCP wrapped text: ``[{"type": "text", "text": "Found N ...", "id": "lc_..."}]``
    - data.gouv.fr JSON API: ``{"data": [...], "total": N}`` or bare list
    - Plain text (fallback)

    Returns a deduplicated list of dicts with keys:
    ``id``, ``title``, ``description``, ``url``, ``organization``.
    """
    candidates: list[dict] = []
    seen_ids: set[str] = set()

    def _add(ds_id: str, title: str, description: str, url: str, org: str) -> None:
        """Deduplicate and append a candidate."""
        if not ds_id and not title:
            return
        if ds_id and ds_id in seen_ids:
            return
        if ds_id:
            seen_ids.add(ds_id)
        candidates.append({
            "id": ds_id,
            "title": title or "Untitled Dataset",
            "description": " ".join(description.split())[:_MAX_DESCRIPTION_LENGTH],
            "url": url,
            "organization": org,
        })

    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        raw = msg.content
        # Only process responses to search_datasets calls
        if msg.tool_call_id not in search_tool_call_ids:
            continue
        # LangChain may store MCP tool content as a list of content blocks
        # (not a string) when the MCP server returns structured output.
        if isinstance(raw, list):
            data = raw
        elif not isinstance(raw, str) or not raw.strip():
            continue
        else:
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                # Try Python repr (e.g. str() of a list/dict from MCP adapter)
                try:
                    data = ast.literal_eval(raw)
                except Exception:
                    # Plain text response — parse directly
                    for ds in _parse_text_search_results(raw):
                        _add(ds["id"], ds["title"], ds["description"], ds["url"], ds["organization"])
                    continue

        # ── MCP text wrapper: [{"type": "text", "text": "...", "id": "lc_..."}] ──
        # The MCP adapter wraps tool output as a list of typed content blocks.
        # The langchain message ID ("lc_...") must NOT be treated as a dataset ID.
        if (
            isinstance(data, list)
            and data
            and isinstance(data[0], dict)
            and data[0].get("type") == "text"
        ):
            for block in data:
                text_content = block.get("text", "") if isinstance(block, dict) else ""
                for ds in _parse_text_search_results(text_content):
                    _add(ds["id"], ds["title"], ds["description"], ds["url"], ds["organization"])
            continue

        # ── Standard data.gouv.fr JSON: {"data": [...], "total": N} or plain list ──
        dataset_list: list | None = None
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            dataset_list = data["data"]
        elif isinstance(data, list):
            dataset_list = data

        if not dataset_list:
            continue

        for ds in dataset_list:
            if not isinstance(ds, dict):
                continue
            org = ds.get("organization") or {}
            org_name = org.get("name", "") if isinstance(org, dict) else str(org)
            _add(
                str(ds.get("id", "")),
                str(ds.get("title", "")),
                ds.get("description") or "",
                ds.get("page", ds.get("url", "")),
                org_name,
            )

    return candidates


# ─── Local tool ───────────────────────────────────────────────────────────────

# Common French/English prepositions that prefix status phrases in natural language
# (e.g. "en maintenance" → "maintenance", "en service" → "service").
# These are stripped before comparison so the filter can match raw data values.
_FILTER_PREP_RE = re.compile(
    r'^(?:en |de |du |le |la |les |l\u2019|en cours de |hors |sous |avec |dans |au |aux )\s*',
    re.IGNORECASE,
)


def _normalize_filter_value(value: str) -> str:
    """Strip leading prepositions from *value* to get the bare keyword.

    E.g. "en maintenance" → "maintenance", "hors service" → "service".
    Applied only for ``contains`` / ``not_contains`` matching so that the data
    value "MAINTENANCE" is matched by "en maintenance".
    """
    return _FILTER_PREP_RE.sub("", value).strip()


def _apply_row_filter(
    rows: list[dict],
    columns: list[str],
    filter_column: str,
    filter_value: str,
    filter_op: str,
) -> list[dict]:
    """Filter *rows* by comparing *filter_column* against *filter_value*.

    Column name matching is case-insensitive.  Comparison is always done on
    lowercased strings so the LLM doesn't need to know the exact casing of
    the cell values.

    For ``contains`` / ``not_contains``, *filter_value* is normalised by
    stripping leading French/English prepositions so that "en maintenance"
    correctly matches a cell whose value is "MAINTENANCE".

    Supported *filter_op* values: ``equals``, ``not_equals``, ``contains``,
    ``not_contains``.
    """
    col_actual = next(
        (c for c in columns if c.lower() == filter_column.lower()),
        filter_column,
    )
    fv = filter_value.lower()
    fv_normalized = _normalize_filter_value(fv)

    def _match(row: dict) -> bool:
        cell = str(row.get(col_actual, row.get(filter_column, ""))).lower()
        if filter_op == "equals":
            return cell == fv
        if filter_op == "not_equals":
            return cell != fv
        if filter_op == "contains":
            return fv_normalized in cell or fv in cell
        if filter_op == "not_contains":
            return fv_normalized not in cell and fv not in cell
        return True

    return [r for r in rows if _match(r)]


@tool
async def fetch_resource_file(
    url: str,
    filter_column: str | None = None,
    filter_value: str | None = None,
    filter_op: str = "contains",
) -> str:
    """
    Download and parse a complete data file from a direct URL.
    Supports CSV, JSON, and GeoJSON formats.
    Returns all rows as a JSON string. Use this for full data retrieval
    instead of paginating through query_resource_data.

    Optional filter parameters (applied after download, before returning):
    - filter_column: column name to filter on (case-insensitive).
    - filter_value: the bare keyword to match (case-insensitive). Strip any leading
      article or preposition ("en", "hors", "de", "au"…) before passing —
      e.g. pass "maintenance" not "en maintenance".
    - filter_op: one of "contains", "not_contains", "equals", "not_equals"
      (default: "contains").
      Use "equals" / "not_equals" ONLY when the user quoted the exact cell value.

    Example: fetch_resource_file(
        url="https://…/data.csv",
        filter_column="statut",
        filter_value="maintenance",
        filter_op="not_contains"
    )
    """
    parsed = await fetch_and_parse(url)
    if parsed.error:
        return f"Error fetching file: {parsed.error}"

    rows = parsed.rows
    raw = parsed.raw

    if filter_column and filter_value is not None:
        rows = _apply_row_filter(rows, parsed.columns, filter_column, filter_value, filter_op)
        # For GeoJSON, filter the features array in `raw` as well so the map
        # only shows matching features.
        if parsed.format == "geojson" and isinstance(raw, dict):
            col_actual = next(
                (c for c in parsed.columns if c.lower() == filter_column.lower()),
                filter_column,
            )
            fv = filter_value.lower()
            fv_normalized = _normalize_filter_value(fv)
            filtered_features = []
            for feat in raw.get("features", []):
                props = feat.get("properties") or {}
                cell = str(props.get(col_actual, props.get(filter_column, ""))).lower()
                if filter_op == "equals" and cell == fv:
                    filtered_features.append(feat)
                elif filter_op == "not_equals" and cell != fv:
                    filtered_features.append(feat)
                elif filter_op == "contains" and (fv_normalized in cell or fv in cell):
                    filtered_features.append(feat)
                elif filter_op == "not_contains" and fv_normalized not in cell and fv not in cell:
                    filtered_features.append(feat)
            raw = {**raw, "features": filtered_features}

    payload: dict = {
        "format": parsed.format,
        "total_rows": len(rows),
        "columns": parsed.columns,
        "rows": rows,
    }
    if parsed.format == "geojson" and raw is not None:
        payload["raw"] = raw
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

    _raw_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )
    user_query: str = (
        _raw_query if isinstance(_raw_query, str)
        else " ".join(
            p.get("text", "") if isinstance(p, dict) else str(p)
            for p in _raw_query
        )
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

    llm = build_llm(get_agent_model_config("datagouv_mcp_agent"), streaming=True).bind_tools(all_tools)

    tool_map = {t.name: t for t in all_tools}
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_query),
    ]

    # Raw fetch_resource_file payloads, stored separately so the LLM only sees
    # a compact acknowledgement while post-processing has full access to the data.
    fetch_payloads: list[dict] = []
    # Track tool_call_ids of search_datasets calls so _extract_dataset_candidates
    # only inspects responses from those calls, not resource or metadata responses.
    search_call_ids: set[str] = set()

    for _ in range(get_agent_max_iterations("datagouv_mcp_agent")):
        response: AIMessage = await llm.ainvoke(messages)
        messages.append(response)

        if not getattr(response, "tool_calls", None):
            break

        for tc in response.tool_calls:
            if tc["name"] == "search_datasets":
                search_call_ids.add(tc["id"])
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

            # Normalize tool result to a valid JSON string so that
            # _extract_dataset_candidates can reliably parse it.
            # MCP tools may return Python objects (list/dict) whose str() repr
            # uses single quotes and is not valid JSON.
            if isinstance(result, str):
                tool_content = result
            else:
                try:
                    tool_content = json.dumps(result, ensure_ascii=False, default=str)
                except Exception:
                    tool_content = str(result)

            if tc["name"] == "fetch_resource_file":
                try:
                    parsed_tool = json.loads(tool_content)
                    if isinstance(parsed_tool, dict) and "rows" in parsed_tool:
                        fetch_payloads.append(parsed_tool)
                        fmt = parsed_tool.get("format", "data")
                        total = parsed_tool.get("total_rows", len(parsed_tool["rows"]))
                        cols = parsed_tool.get("columns", [])
                        tool_content = (
                            f"[fetch_resource_file OK] format={fmt}, "
                            f"total_rows={total}, columns={cols}"
                        )
                except (json.JSONDecodeError, ValueError):
                    pass

            messages.append(
                ToolMessage(content=tool_content, tool_call_id=tc["id"])
            )

    result_content = (
        messages[-1].content if messages else "data.gouv.fr agent returned no result."
    )

    # Collect ALL successful fetch_resource_file results from fetch_payloads.
    # Separate tabular files (csv/json) from geojson files so both pipelines
    # can be fed independently.
    tabular_data: dict | None = None   # first csv/json result found
    geojson_data: dict | None = None   # first geojson result found

    for payload in fetch_payloads:
        fmt = payload.get("format", "")
        if fmt == "geojson":
            if geojson_data is None:
                geojson_data = payload
        else:
            if tabular_data is None:
                tabular_data = payload

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

    # ── Human-in-the-loop: dataset disambiguation ─────────────────────────────
    # Enforce disambiguation in Python — never rely solely on the LLM following
    # prompt rules.  If the search returned multiple candidates AND the user has
    # not unambiguously identified one (UUID or exact quoted title), we surface
    # the choice panel and discard any data the LLM may have fetched anyway.
    candidates = _extract_dataset_candidates(messages, search_call_ids)
    if len(candidates) > 1 and not _user_identifies_dataset(user_query, candidates):
        state_update["pending_dataset_choice"] = candidates
        # Discard any data the LLM wrongly fetched — user must choose first.
        return state_update
    else:
        state_update["pending_dataset_choice"] = None

    # ── Populate state["geojson"] from the GeoJSON fetch ──────────────────────
    if geojson_data is not None:
        raw_gj = geojson_data.get("raw")
        if (
            isinstance(raw_gj, dict)
            and raw_gj.get("type") in ("FeatureCollection", "Feature")
            and raw_gj.get("features")  # skip empty FeatureCollection
        ):
            state_update["geojson"] = raw_gj

    # ── Populate state["dataviz"] from the tabular fetch ──────────────────────
    if tabular_data is not None:
        fmt = tabular_data.get("format", "data")
        columns = tabular_data["columns"]
        all_rows = tabular_data["rows"]
        total = tabular_data.get("total_rows", len(all_rows))
        if total > 0 and columns and all_rows:
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
        else:
            # File was fetched but contains no rows — surface this in the summary
            if not result_content or result_content == "data.gouv.fr agent returned no result.":
                result_content = (
                    "Le fichier a été récupéré depuis data.gouv.fr mais ne contient "
                    "aucune donnée (0 enregistrement)."
                )
                state_update["sub_results"] = {"data_gouv": result_content}

    return state_update
