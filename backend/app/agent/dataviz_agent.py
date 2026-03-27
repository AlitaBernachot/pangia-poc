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

from app.agent.model_config import build_llm, get_agent_model_config
from app.agent.state import AgentState

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
- Use "bar" charts for comparisons, "line" for time-series / trends, "pie"
  for proportions (≤ 8 slices), "scatter" for correlations, "histogram"
  for distributions.
- Keep KPI values as numbers when possible; include the unit separately.
- Table columns should be short, clear header strings.
- Keep all labels concise (≤ 40 characters).
"""

_MAX_ITERATIONS = 5


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
        labels = json.loads(labels_json)
    except json.JSONDecodeError as exc:
        return f"Invalid labels_json: {exc}"

    try:
        datasets = json.loads(datasets_json)
    except json.JSONDecodeError as exc:
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
        columns = json.loads(columns_json)
    except json.JSONDecodeError as exc:
        return f"Invalid columns_json: {exc}"

    try:
        rows = json.loads(rows_json)
    except json.JSONDecodeError as exc:
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


# ─── Node function ────────────────────────────────────────────────────────────

async def run(state: AgentState) -> dict:
    """LangGraph node: run the DataViz Agent after parallel sub-agents complete.

    Reads sub_results produced by other agents, detects numerical / statistical
    data, and produces structured chart / KPI / table payloads for the frontend.
    Skips the LLM entirely when no visualisable content is detected.
    """
    sub_results: dict[str, str] = state.get("sub_results", {})
    user_query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    # Build enriched context from all sub-agent results
    sub_text = "\n\n".join(
        f"[{agent.upper()} RESULTS]:\n{result}"
        for agent, result in sub_results.items()
        if result and result.strip()
    )

    # Quick heuristic: skip entirely if there is no numeric / statistical signal
    combined_check = f"{sub_text} {user_query}"
    if not _NUMERIC_HINT_RE.search(combined_check):
        return {"sub_results": {"dataviz": ""}, "dataviz": None}

    llm = build_llm(get_agent_model_config("dataviz_agent"), streaming=True).bind_tools(
        DATAVIZ_TOOLS
    )

    dataviz_input = (
        f"{sub_text}\n\nOriginal user question: {user_query}"
        if sub_text
        else user_query
    )

    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=dataviz_input)]

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
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    result_content = messages[-1].content if messages else ""

    # Extract structured dataviz payload from the agent's final response
    dataviz_data: dict[str, Any] | None = None
    summary = "Data visualisation processed."

    if result_content:
        try:
            parsed = json.loads(result_content)
            if isinstance(parsed, dict) and (
                "charts" in parsed or "kpis" in parsed or "tables" in parsed
            ):
                # Only store payload if it has at least one non-empty section
                has_content = (
                    (parsed.get("charts") or [])
                    or (parsed.get("kpis") or [])
                    or (parsed.get("tables") or [])
                )
                if has_content:
                    dataviz_data = parsed
                    parts = []
                    if parsed.get("charts"):
                        parts.append(f"{len(parsed['charts'])} chart(s)")
                    if parsed.get("kpis"):
                        parts.append(f"{len(parsed['kpis'])} KPI(s)")
                    if parsed.get("tables"):
                        parts.append(f"{len(parsed['tables'])} table(s)")
                    summary = "Visualisations generated: " + ", ".join(parts) + "."
        except (json.JSONDecodeError, ValueError):
            # Fallback: search for JSON block in the text
            match = re.search(
                r'\{[^{}]*(?:"charts"|"kpis"|"tables")[^{}]*\}',
                result_content,
                re.DOTALL,
            )
            if match:
                try:
                    parsed = json.loads(match.group())
                    if isinstance(parsed, dict):
                        has_content = (
                            (parsed.get("charts") or [])
                            or (parsed.get("kpis") or [])
                            or (parsed.get("tables") or [])
                        )
                        if has_content:
                            dataviz_data = parsed
                except (json.JSONDecodeError, ValueError):
                    pass

    return {
        "sub_results": {"dataviz": summary},
        "dataviz": dataviz_data,
    }
