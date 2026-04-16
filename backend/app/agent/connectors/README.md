<!--
SPDX-FileCopyrightText: 2026 AlitaBernachot

SPDX-License-Identifier: MIT
-->

# Connectors

Sub-agents that connect PangIA to external data sources.

---

## data.gouv.fr Agent

File: [`data_gouv_agent.py`](data_gouv_agent.py)

Queries the French government open-data catalogue ([data.gouv.fr](https://data.gouv.fr)) through its MCP interface.

### Capabilities

| Tool | Description |
|---|---|
| `search_datasets` *(MCP)* | Full-text search across the catalogue |
| `get_dataset_info` *(MCP)* | Metadata for a specific dataset (by ID) |
| `list_resources` *(MCP)* | List downloadable resources attached to a dataset |
| `get_resource_info` *(MCP)* | Metadata + direct download URL for a resource |
| `query_resource_data` *(MCP)* | Paginated tabular preview (CSV/JSON) |
| `fetch_resource_file` *(local)* | Full file download with optional row-level filtering |

### Operation modes

The agent picks one of four modes based on the user's intent:

#### 0 — Disambiguation
When a search returns ≥ 2 datasets, the agent asks the user which one to use **unless** the query already unambiguously identifies one:
- A dataset UUID present in the message that matches a search result, **or**
- A dataset title in quotes that is character-for-character identical to a result title.

> This rule is enforced in Python (not just in the prompt) — the agent discards any data fetched by the LLM if the disambiguation condition is triggered.

#### 1 — Metadata / discovery
Questions like *"What open data exists about X?"* → search, return metadata, stop.

#### 2 — Full retrieval (Strategy B)
Questions like *"Affiche les données"*, *"Show me the dataset"* → download the complete CSV/JSON and, if available, the companion GeoJSON. Both are surfaced: table in the data panel, features on the map.

#### 3 — Filtered retrieval (Strategy C)
Questions with an attribute/status condition, e.g. *"capteurs qui ne sont pas en maintenance"*:

1. Guess the column name from common French/English status fields (`statut`, `etat`, `status`, `state`); or call `query_resource_data(page_size=1)` to read headers.
2. Call `fetch_resource_file` with filter parameters:

| Parameter | Description |
|---|---|
| `filter_column` | Column name (case-insensitive) |
| `filter_value` | Natural-language value from the query (e.g. `"en maintenance"`) |
| `filter_op` | `"contains"` (default), `"not_contains"`, `"equals"`, `"not_equals"` |

**Filter normalisation** — leading French/English prepositions (`en `, `hors `, `de `, …) are stripped before matching. So `filter_value="en maintenance"` correctly matches a cell whose raw value is `"MAINTENANCE"` or `"maintenance"`.

Use `"equals"` / `"not_equals"` only when the user explicitly quoted an exact cell value (e.g. `"MAINTENANCE"`). In all other cases, prefer `"contains"` / `"not_contains"`.

### Configuration

```env
DATA_GOUV_MCP_URL=https://mcp.data.gouv.fr/mcp    # MCP endpoint
DATA_GOUV_AGENT_ENABLED=true
DATA_GOUV_AGENT_MODEL=                             # leave blank to inherit global model
DATA_GOUV_AGENT_MAX_ITERATIONS=10
```
