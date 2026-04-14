"""
DataViz Agent – data visualisation detection and structuring.

Specialises in:
  • detecting numerical / statistical data in sub-agent results
  • choosing the most appropriate visualisation type (chart, KPI, table)
  • producing chart structures compatible with Chart.js / D3.js (bar, line,
    pie, scatter, histogram)
  • computing KPI cards (value, unit, variation, trend, threshold)
  • generating formatted tables (column headers + row data)

The agent returns a structured JSON payload stored in state["dataviz"] that
the frontend can directly consume to render interactive visualisations.
"""
from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agent.model_config import build_llm, get_agent_model_config, get_agent_max_iterations
from app.agent.core.state import AgentState

_json_decoder = json.JSONDecoder()


def _lenient_json_loads(s: str) -> Any:
    """Parse the first complete JSON value in *s*, ignoring any trailing content.

    Unlike ``json.loads``, this does not raise ``JSONDecodeError`` for trailing
    text that the LLM may append after a valid JSON value (e.g. a prose comment
    or a closing brace from the outer tool-call object).
    """
    value, _ = _json_decoder.raw_decode(s.strip())
    return value

# ─── System prompt ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are the Data Visualisation Agent of the PangIA GeoIA platform.
Your role is to analyse the results produced by other sub-agents and the user
question, then decide whether the data can be meaningfully visualised.

## Output types you can produce

1. **charts** – structured data for Chart.js / D3.js renders:
   - Types: "bar", "line", "pie", "scatter", "histogram"
   - Each chart has: title (string), chart_type (string), labels (array of
     strings), datasets (array of objects with "label" string and "data"
     array of numbers).
   - For "scatter": datasets contain objects with "x" and "y" number fields
     instead of plain numbers.

2. **kpis** – key performance indicator cards:
   - Each KPI has: label (string), value (string|number), unit (string,
     optional), variation (string, optional, e.g. "+12%"), trend ("up" |
     "down" | "stable"), threshold (string, optional, e.g. "< 100").

3. **tables** – formatted tabular data:
   - Each table has: title (string), columns (array of strings),
     rows (array of arrays matching the column order).

## Workflow
1. Read the **[AGENT RESULTS]** section: it contains outputs from other
   sub-agents (Neo4j, PostGIS, RDF, Vector).
2. Identify numerical or categorical data that can be visualised.
3. Use the appropriate tools to extract and format the data.
4. **Your final message must be a single valid JSON object** with exactly
   this structure (omit empty arrays):
   {{
     "charts": [...],
     "kpis": [...],
     "tables": [...]
   }}

## Rules
- Only include visualisations that are genuinely useful given the data.
- If there is no visualisable data, return:
  {{"charts": [], "kpis": [], "tables": []}}
- **Display-only rule**: when the user only asks to *show*, *display*, *list*
  or *afficher*, *montrer*, *lister* data WITHOUT requesting charts, analysis,
  statistics, or comparisons, call ONLY `build_table`. Do NOT call `build_chart`
  or `build_kpi`.
- Use "bar" charts for comparisons, "line" for time-series / trends, "pie"
  for proportions (≤ 8 slices), "scatter" for correlations, "histogram"
  for distributions.
- **Comparison rule**: when the user query contains a comparison notion
  (keywords: compare, comparer, versus, vs, between, entre, différence,
  difference, contrast, comparez, comparer), you MUST produce **both** a
  "bar" chart AND a "pie" chart for the same data, sharing the same labels
  and datasets. Both must be built with `build_chart` (two separate calls).
- Keep KPI values as numbers when possible; include the unit separately.
- Table columns should be short, clear header strings.
- Keep all labels concise (≤ 40 characters).
- Be concise: answer in the fewest words needed. No preambles, no repetition.
"""


# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
def extract_numbers_from_text(text: str) -> str:
    """Extract numeric values with optional labels from free text.

    Returns a JSON array of objects with "label" and "value" keys.
    """
    # Match patterns like "X: 42", "X = 42", "42 X", "42 (X)"
    patterns = [
        r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 _/\-]{1,40})\s*[=:]\s*(-?\d[\d\s,\.]*)",
        r"(-?\d[\d\s,\.]*)\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 _/\-]{1,40})",
    ]
    results: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for pat in patterns:
        for m in re.finditer(pat, text):
            raw_label = m.group(1).strip()
            raw_value = m.group(2).strip().replace(",", ".").replace(" ", "")
            # Try to parse as float
            try:
                value = float(raw_value)
            except ValueError:
                continue
            label = raw_label.strip()[:50]
            if label.lower() in seen_labels:
                continue
            seen_labels.add(label.lower())
            results.append({"label": label, "value": value})

    if not results:
        return "No numeric values found in the provided text."
    return json.dumps(results)


@tool
def build_chart(
    chart_type: str,
    title: str,
    labels_json: str,
    datasets_json: str,
) -> str:
    """Build a chart data structure for Chart.js / D3.js.

    Args:
        chart_type: One of "bar", "line", "pie", "scatter", "histogram".
        title: Human-readable chart title.
        labels_json: JSON array of label strings (x-axis categories or slice names).
        datasets_json: JSON array of dataset objects.
                       For bar/line/pie/histogram: [{"label": "...", "data": [1,2,3]}]
                       For scatter: [{"label": "...", "data": [{"x":1,"y":2}, ...]}]
    """
    valid_types = {"bar", "line", "pie", "scatter", "histogram"}
    if chart_type not in valid_types:
        return f"Invalid chart_type '{chart_type}'. Must be one of: {', '.join(sorted(valid_types))}."

    try:
        labels = _lenient_json_loads(labels_json)
    except (json.JSONDecodeError, ValueError) as exc:
        return f"Invalid labels_json: {exc}"

    try:
        datasets = _lenient_json_loads(datasets_json)
    except (json.JSONDecodeError, ValueError):
        # Common LLM mistake: extra closing brace at end, e.g. [{...}}  or  [{...}}]
        repaired = re.sub(r"\}\}(\s*\]?\s*)$", r"}\1", datasets_json.strip())
        if not repaired.rstrip().endswith("]"):
            repaired = repaired.rstrip() + "]"
        try:
            datasets = _lenient_json_loads(repaired)
        except (json.JSONDecodeError, ValueError) as exc:
            return f"Invalid datasets_json: {exc}"

    if not isinstance(labels, list):
        return "labels_json must be a JSON array."
    if not isinstance(datasets, list):
        return "datasets_json must be a JSON array."

    chart: dict[str, Any] = {
        "chart_type": chart_type,
        "title": title,
        "labels": labels,
        "datasets": datasets,
    }
    return json.dumps(chart)


@tool
def build_kpi(
    label: str,
    value: str,
    unit: str = "",
    variation: str = "",
    trend: str = "stable",
    threshold: str = "",
) -> str:
    """Build a KPI card data structure.

    Args:
        label: Short descriptive label (e.g. "Total cases").
        value: The KPI value as a string or number (e.g. "1 234" or "42.5").
        unit: Optional unit of measurement (e.g. "%" or "km²").
        variation: Optional variation string (e.g. "+12%" or "-3 pts").
        trend: Direction of change: "up", "down", or "stable".
        threshold: Optional threshold description (e.g. "< 100" or "target: 500").
    """
    valid_trends = {"up", "down", "stable"}
    if trend not in valid_trends:
        trend = "stable"

    kpi: dict[str, str] = {"label": label, "value": value}
    if unit:
        kpi["unit"] = unit
    if variation:
        kpi["variation"] = variation
    kpi["trend"] = trend
    if threshold:
        kpi["threshold"] = threshold

    return json.dumps(kpi)


@tool
def build_table(title: str, columns_json: str, rows_json: str) -> str:
    """Build a table data structure.

    Args:
        title: Human-readable table title.
        columns_json: JSON array of column header strings.
        rows_json: JSON array of arrays, each inner array being a row of values
                   matching the column order.
    """
    try:
        columns = _lenient_json_loads(columns_json)
    except (json.JSONDecodeError, ValueError) as exc:
        return f"Invalid columns_json: {exc}"

    try:
        rows = _lenient_json_loads(rows_json)
    except (json.JSONDecodeError, ValueError) as exc:
        return f"Invalid rows_json: {exc}"

    if not isinstance(columns, list):
        return "columns_json must be a JSON array of strings."
    if not isinstance(rows, list):
        return "rows_json must be a JSON array of arrays."

    table: dict[str, Any] = {
        "title": title,
        "columns": columns,
        "rows": rows,
    }
    return json.dumps(table)


DATAVIZ_TOOLS = [extract_numbers_from_text, build_chart, build_kpi, build_table]
_TOOL_MAP = {t.name: t for t in DATAVIZ_TOOLS}


# ─── Heuristic detection ──────────────────────────────────────────────────────

# Quick check: does the combined text contain numeric patterns worth visualising?
_NUMERIC_HINT_RE = re.compile(
    r"(?:\b\d+[\.,]\d+|\b\d{2,}\b)"            # numbers with decimal or ≥2 digits
    r"|(?:count|total|average|mean|sum|max|min|"  # aggregation keywords
    r"nombre|total|moyenne|somme|maximum|minimum|"  # French equivalents
    r"taux|ratio|percent|pourcentage|proportion|"
    r"trend|évolution|variation|distribution)",
    re.IGNORECASE,
)

# User intent is purely "show me the data" (no analysis/chart request)
_DISPLAY_ONLY_RE = re.compile(
    r"\b(?:affich[e|er]r?|montr[er]r?|list[e|er]r?|donn[e|er]r?|voir|vois|show|display|donne[- ]moi|affiche[- ]moi|montre[- ]moi)\b",
    re.IGNORECASE,
)

# Explicit chart / analysis / statistics request
_ANALYSIS_INTENT_RE = re.compile(
    r"\b(?:graphi?(?:que)?|chart|graph|courbe|histogramme|histogram|camembert|pie|bar(?:re)?|"
    r"statistiques?|statistics?|analys[e|er]|comparer?|comparaison|évolution|tendance|trend|"
    r"visualis[e|er]|kpi|dashboard)",
    re.IGNORECASE,
)


# ─── Node function ────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the DataViz Agent after parallel sub-agents complete.

    Reads sub_results produced by other agents, detects numerical / statistical
    data, and produces structured chart / KPI / table payloads for the frontend.
    Skips the LLM entirely when no visualisable content is detected.
    """
    try:
        return await _run(state)
    except Exception as exc:  # noqa: BLE001
        return {"sub_results": {"dataviz": f"[DataViz agent unavailable: {exc}]"}, "dataviz": None}


async def _run(state: AgentState) -> dict:
    sub_results: dict[str, str] = state.get("sub_results", {})
    existing_dataviz: dict[str, Any] | None = state.get("dataviz")
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    # Detect table-only mode: user just wants to see the data, no charts
    _uq = str(user_query)
    table_only_mode = (
        bool(_DISPLAY_ONLY_RE.search(_uq))
        and not bool(_ANALYSIS_INTENT_RE.search(_uq))
    )

    # Build enriched context from all sub-agent results
    sub_text = "\n\n".join(
        f"[{agent.upper()} RESULTS]:\n{result}"
        for agent, result in sub_results.items()
        if result and result.strip()
    )

    # ── Pre-seed collected results with dataviz tables already built ───────────
    # When dataviz is pre-populated (e.g. by data_gouv_agent), reuse its tables
    # and only ask the LLM to add charts/KPIs if the data is numeric.
    preseeded_tables: list[dict[str, Any]] = []
    if existing_dataviz and existing_dataviz.get("tables"):
        preseeded_tables = list(existing_dataviz["tables"])
        first_table = preseeded_tables[0]
        cols = first_table.get("columns", [])
        all_rows = first_table.get("rows", [])
        total = len(all_rows)
        # Reconstruct list-of-dicts for LLM sample context
        sample_rows = [dict(zip(cols, r)) for r in all_rows[:50]]
        sub_text = (
            f"[DONNÉES COMPLÈTES – {total} lignes, colonnes: {', '.join(cols)}]\n"
            f"Exemple (premières {len(sample_rows)} lignes): {json.dumps(sample_rows, ensure_ascii=False, default=str)}\n\n"
            f"NOTE: Un tableau avec TOUTES les {total} lignes a déjà été construit. "
            f"N'appelle PAS build_table. Appelle uniquement build_chart ou build_kpi si pertinent."
        )

    # Quick heuristic: skip entirely if there is no numeric / statistical signal
    combined_check = f"{sub_text} {user_query}"
    if not preseeded_tables and not _NUMERIC_HINT_RE.search(combined_check):
        return {"sub_results": {"dataviz": ""}, "dataviz": None}

    # ── Short-circuit: table-only mode or non-numeric preseeded data ──────────
    # When the user only asks to display data (no analysis/chart request),
    # or when there is no numeric signal, return tables only — skip the LLM.
    if preseeded_tables and (table_only_mode or not _NUMERIC_HINT_RE.search(combined_check)):
        dataviz_data = {"charts": [], "kpis": [], "tables": preseeded_tables}
        return {
            "sub_results": {"dataviz": "Visualisations generated: 1 table(s)."},
            "dataviz": dataviz_data,
        }

    llm = build_llm(get_agent_model_config("dataviz_agent"), streaming=True).bind_tools(
        DATAVIZ_TOOLS if not table_only_mode else [build_table]
    )

    table_only_note = (
        "\n\nIMPORTANT: The user only wants to see the data displayed. "
        "Call ONLY build_table. Do NOT call build_chart or build_kpi."
        if table_only_mode
        else ""
    )

    dataviz_input = (
        f"{sub_text}\n\nOriginal user question: {user_query}{table_only_note}"
        if sub_text
        else f"{user_query}{table_only_note}"
    )

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=dataviz_input)]

    # Accumulate structured results from tool calls directly, so we don't
    # depend on the LLM reproducing them in its final message.
    # Pre-seed tables with raw file data (takes priority over LLM-built tables).
    collected_charts: list[dict[str, Any]] = []
    collected_kpis: list[dict[str, Any]] = []
    collected_tables: list[dict[str, Any]] = list(preseeded_tables)

    for _ in range(get_agent_max_iterations("dataviz_agent")):
        response: AIMessage = await llm.ainvoke(messages)
        messages.append(response)

        if not getattr(response, "tool_calls", None):
            break

        all_errors = True
        for tc in response.tool_calls:
            tool_fn = _TOOL_MAP.get(tc["name"])
            if tool_fn is None:
                result = f"Unknown tool: {tc['name']}"
            else:
                try:
                    result = await tool_fn.ainvoke(tc["args"])
                except Exception as exc:
                    result = f"Tool error: {exc}"

            is_error = isinstance(result, str) and result.startswith(("Unknown tool", "Tool error", "Invalid"))
            if not is_error:
                all_errors = False

            # Collect structured output from each tool call
            if not is_error:
                try:
                    item = json.loads(result)
                    if isinstance(item, dict):
                        if tc["name"] == "build_chart" and "chart_type" in item:
                            collected_charts.append(item)
                        elif tc["name"] == "build_kpi" and "label" in item:
                            collected_kpis.append(item)
                        elif tc["name"] == "build_table" and "columns" in item and not preseeded_tables:
                            # Only add LLM-built tables when no preseeded table exists
                            collected_tables.append(item)
                except (json.JSONDecodeError, ValueError):
                    pass

            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

        # All tool calls failed: no point sending the same args again
        if all_errors:
            break

    # Build dataviz_data from collected tool results first (most reliable).
    # Fall back to parsing the LLM's final message if no tools were called.
    dataviz_data: dict[str, Any] | None = None
    summary = "Data visualisation processed."

    if collected_charts or collected_kpis or collected_tables:
        dataviz_data = {
            "charts": collected_charts,
            "kpis": collected_kpis,
            "tables": collected_tables,
        }
    else:
        # No tool calls – try to parse the final LLM message as JSON
        result_content = messages[-1].content if messages else ""
        if result_content:
            # Strip markdown code fences if present
            stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", result_content.strip(), flags=re.MULTILINE)
            for candidate in (stripped, result_content):
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict) and (
                        "charts" in parsed or "kpis" in parsed or "tables" in parsed
                    ):
                        has_content = (
                            (parsed.get("charts") or [])
                            or (parsed.get("kpis") or [])
                            or (parsed.get("tables") or [])
                        )
                        if has_content:
                            dataviz_data = parsed
                            break
                except (json.JSONDecodeError, ValueError):
                    continue

    if dataviz_data:
        parts = []
        if dataviz_data.get("charts"):
            parts.append(f"{len(dataviz_data['charts'])} chart(s)")
        if dataviz_data.get("kpis"):
            parts.append(f"{len(dataviz_data['kpis'])} KPI(s)")
        if dataviz_data.get("tables"):
            parts.append(f"{len(dataviz_data['tables'])} table(s)")
        summary = "Visualisations generated: " + ", ".join(parts) + "."

    return {
        "sub_results": {"dataviz": summary},
        "dataviz": dataviz_data,
    }
