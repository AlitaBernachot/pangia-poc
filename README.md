<!--
SPDX-FileCopyrightText: 2026 AlitaBernachot

SPDX-License-Identifier: MIT
-->

![PangIA Banner](docs/pangIA_logo.png)

# PangIA – Multi-agent system 🌍

A minimal AI agent chat application with a **multi-agent architecture**:

| Layer | Technology |
|---|---|
| **Frontend** | React 19 + Tailwind CSS v4, Vite, TypeScript (`frontend-client/`) |
| **Backend** | FastAPI, Server-Sent Events (SSE) |
| **Orchestration** | LangChain + LangGraph (2-stage routing: Intent Parser + Smart Dispatcher + parallel sub-agents) |
| **Knowledge Graph** | Neo4j (Cypher) |
| **RDF / Linked Data** | Ontotext GraphDB (SPARQL) |
| **Vector Search** | ChromaDB (embeddings) |
| **Spatial SQL** | PostgreSQL + PostGIS |
| **Sessions** | Redis |
| **Local LLM** | Ollama (Gemma 4, Llama 3, …) |
| **Observability** | Arize Phoenix (traces, spans, LLM call inspection) |
| **Infrastructure** | Docker Compose |

---

## Table of Contents

- [PangIA – Multi-agent system 🌍](#pangia--multi-agent-system-)
  - [Table of Contents](#table-of-contents)
  - [Multi-agent architecture](#multi-agent-architecture)
    - [Agent enable / disable flags](#agent-enable--disable-flags)
    - [Agent fault tolerance](#agent-fault-tolerance)
    - [Agent ReAct loop iterations](#agent-react-loop-iterations)
    - [Per-agent LLM configuration](#per-agent-llm-configuration)
    - [SSE event types](#sse-event-types)
    - [Intent Parser](#intent-parser)
    - [Smart Dispatcher](#smart-dispatcher)
    - [Source Registry](#source-registry)
    - [Human Output Agent](#human-output-agent)
    - [Data Visualisation Agent](#data-visualisation-agent)
    - [Map Agent](#map-agent)
  - [Quick Start](#quick-start)
    - [1. Configure environment](#1-configure-environment)
    - [2. Start all services](#2-start-all-services)
  - [Observability (Arize Phoenix)](#observability-arize-phoenix)
    - [Configuration](#configuration)
  - [Project structure](#project-structure)
  - [Development (without Docker)](#development-without-docker)
    - [Backend](#backend)
    - [Frontend](#frontend-1)
  - [Seed themes](#seed-themes)
    - [PostGIS schema isolation](#postgis-schema-isolation)
    - [Switching the theme](#switching-the-theme)
    - [Adding a new theme](#adding-a-new-theme)
  - [Adding a new sub-agent](#adding-a-new-sub-agent)
  - [Geo Agent – Geospatial Analysis](#geo-agent--geospatial-analysis)
    - [Sub-agent hierarchy](#sub-agent-hierarchy)
    - [Configuration](#configuration-1)
    - [Notes](#notes)
  - [Local LLM with Ollama](docs/ollama-gemma4-setup.md)

---

## Multi-agent architecture

> 📊 **Mermaid graph:** [`backend/app/agent/mermaid_graph/orchestrator_graph.mmd`](backend/app/agent/mermaid_graph/orchestrator_graph.mmd)  
> The Mermaid workflow graph is auto-generated at startup and kept in sync with the code.

```
User query  +  selected_agents? (optional)
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│                       Orchestrator Agent                         │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  intent_parser  (heuristics + LLM structured output)     │   │
│  │  → ParsedIntent (intent_type, entities, geo_zone …)      │   │
│  └─────────────────────────┬────────────────────────────────┘   │
│           [INTENT_PARSER_ENABLED – default: on]                  │
│  ┌─────────────────────────▼────────────────────────────────┐   │
│  │  smart_dispatcher  (metadata scoring vs Source Registry)  │   │
│  │  → agents_to_call  (deterministic, no LLM required)      │   │
│  └─────────────────────────┬────────────────────────────────┘   │
│        [SMART_DISPATCHER_ENABLED – default: on]                  │
│        (when off, the LLM router selects agents instead)         │
│                            │ Send fan-out                        │
│          ┌─────────────────┼──────────────────┐                 │
│  ┌───────▼──────┐  ┌───────▼────────┐  ┌──────▼───────┐        │
│  │ neo4j_agent  │  │   rdf_agent    │  │ postgis / …  │        │
│  │(Cypher/Neo4j)│  │(SPARQL/GraphDB)│  │ vector / geo │        │
│  └───────┬──────┘  └───────┬────────┘  └──────┬───────┘        │
│          └─────────────────┼──────────────────┘                 │
│                   (barrier: wait for all parallel agents)        │
│                            │                                     │
│                   post_process_router                            │
│                            │                                     │
│                   humanoutput_agent                              │
│                   (decides map / dataviz / both)                 │
│            ┌───────────────┴──────────────┐                     │
│   ┌────────▼────────┐        ┌────────────▼──────────┐          │
│   │  mapviz_agent   │        │    dataviz_agent       │          │
│   │ (GeoJSON / map) │        │ (charts / KPI / tbl)   │          │
│   └────────┬────────┘        └────────────┬──────────┘          │
│            └───────────────┬──────────────┘                     │
│                         ┌──▼──────────┐                         │
│                         │  merge node │                         │
│                         │ (synthesise)│                         │
│                         └──┬──────────┘                         │
└────────────────────────────┼─────────────────────────────────────┘
                             ▼
                      Streamed answer (SSE)
```

The query passes through up to two **preparatory stages** before being fanned
out to the data-source connectors:

1. **Intent Parser** (`intent_parser`) — extracts a structured `ParsedIntent`
   (intent type, named entities, geographic zone, temporal range, natural language
   intention, detected language, confidence) using fast heuristics followed by an
   LLM structured-output call when needed.  Enabled by `INTENT_PARSER_ENABLED`
   (default `true`).

2. **Smart Dispatcher** (`smart_dispatcher`) — uses the `ParsedIntent` to score
   every registered source against the **Source Registry** metadata (capability
   match, topic/entity overlap, geographic scope, semantic similarity via ChromaDB).
   Returns a ranked `agents_to_call` list **without any LLM call**.  When disabled,
   the legacy **LLM router** (structured output) selects agents instead.  Enabled
   by `SMART_DISPATCHER_ENABLED` (default `true`).

Both stages respect two cross-cutting constraints:

1. **Server-side config** — each agent can be individually enabled or disabled via
   environment variables (all default to `true`).  Disabled agents are excluded
   from the eligible pool entirely.
2. **User selection** — a caller can pass `"selected_agents": ["neo4j", "vector"]`
   in the `POST /api/chat` request body to restrict routing to a specific subset.
   An empty list (or omitting the field) means *"no preference"* — all active
   agents are considered.

Each selected connector runs its own ReAct loop (LLM + tools) and writes its
result into a shared `sub_results` dict.

After all data-source agents complete, a **`post_process_router`** barrier routes
to **`humanoutput_agent`**, which inspects `sub_results` and the user query to
decide whether a map, charts/tables, both, or neither are appropriate.  It then
fans out (via Send) only to the agents that are relevant — `mapviz_agent`,
`dataviz_agent`, or both — and writes its decision to `state["output_decision"]`.
The **merge** node then waits for all post-processors and synthesises the results
into a final streamed answer.

### Agent enable / disable flags

| Variable | Default | Description |
|---|---|---|
| `INTENT_PARSER_ENABLED` | `true` | Stage 1 – query analyser (produces ParsedIntent) |
| `SMART_DISPATCHER_ENABLED` | `true` | Stage 2 – metadata-based router (replaces LLM router when on) |
| `NEO4J_AGENT_ENABLED` | `true` | Knowledge Graph connector (Cypher / Neo4j) |
| `RDF_AGENT_ENABLED` | `true` | RDF/Linked Data connector (SPARQL / GraphDB) |
| `VECTOR_CHROMA_AGENT_ENABLED` | `true` | Semantic search connector (ChromaDB) |
| `POSTGIS_AGENT_ENABLED` | `true` | Spatial SQL connector (PostGIS) |
| `DATA_GOUV_AGENT_ENABLED` | `true` | French open-data connector (data.gouv.fr via MCP) |
| `GEO_AGENT_ENABLED` | `true` | Geospatial analysis orchestrator (geo sub-agents) |
| `HUMANOUTPUT_AGENT_ENABLED` | `true` | Output decision agent (routes to map/dataviz selectively) |
| `MAPVIZ_AGENT_ENABLED` | `true` | Geographic visualisation agent (GeoJSON / Leaflet map) |
| `DATAVIZ_AGENT_ENABLED` | `true` | Data visualisation agent (charts, KPIs, tables) |

Set any flag to `false` in `.env` to exclude that agent from all routing decisions.
The orchestrator always keeps at least one agent active as a fallback (defaults to `neo4j`).

### Agent fault tolerance

Every agent's `run()` function wraps its logic in a top-level `try/except`.
If an agent raises any exception (network error, 502 from an external MCP
server, database unreachable, timeout, …), it catches it and returns a
graceful fallback result — e.g. `[data.gouv agent unavailable: 502 Bad Gateway]`
— stored in `sub_results` under its key.

This means:
- **The chain never crashes** because of a single failing agent.
- All other agents (including `merge`) continue normally.
- The final answer is synthesised from whatever results are available.
- The error message is visible in the agent activity panel in the UI.

### Agent ReAct loop iterations

Each agent runs a ReAct loop (LLM call → tool call → observation → …).
The number of iterations is configurable at two levels:

| Variable | Default | Description |
|---|---|---|
| `AGENT_MAX_ITERATIONS` | `10` | Global fallback used by all agents |
| `INTENT_PARSER_AGENT_MAX_ITERATIONS` | `0` | Intent Parser override (0 = use global) |
| `NEO4J_AGENT_MAX_ITERATIONS` | `0` | Neo4j agent override (0 = use global) |
| `RDF_AGENT_MAX_ITERATIONS` | `0` | RDF/SPARQL agent override |
| `VECTOR_CHROMA_AGENT_MAX_ITERATIONS` | `0` | Vector agent override |
| `POSTGIS_AGENT_MAX_ITERATIONS` | `0` | PostGIS agent override |
| `MAPVIZ_AGENT_MAX_ITERATIONS` | `0` | Map agent override |
| `DATA_GOUV_AGENT_MAX_ITERATIONS` | `0` | data.gouv.fr agent override |
| `DATAVIZ_AGENT_MAX_ITERATIONS` | `0` | DataViz agent override |

Lower the value to reduce latency and cost; raise it for agents that need more
tool-call steps (e.g. data.gouv or PostGIS on complex spatial queries).

### Per-agent LLM configuration

Every agent (including the router and the merge node) can use a **different LLM model and provider** independently of the global `OPENAI_MODEL` setting.  Two environment variables control each agent:

| Variable pattern | Example value | Description |
|---|---|---|
| `<AGENT>_MODEL_PROVIDER` | `openai`, `anthropic`, `ollama` | Provider for this agent. Leave empty to use the global provider. |
| `<AGENT>_MODEL_NAME` | `gpt-4o`, `claude-3-5-sonnet-latest`, `llama3` | Model name for this agent. Leave empty to fall back to `OPENAI_MODEL`. |

Available `<AGENT>` prefixes: `ROUTER`, `INTENT_PARSER_AGENT`, `NEO4J_AGENT`, `RDF_AGENT`, `VECTOR_CHROMA_AGENT`, `POSTGIS_AGENT`, `MAPVIZ_AGENT`, `DATA_GOUV_AGENT`, `DATAVIZ_AGENT`, `MERGE`.

Example `.env` — use a powerful model for the router and merge, a cheaper one for sub-agents:

```env
# Global fallback
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Router and synthesis need stronger reasoning
ROUTER_MODEL_PROVIDER=openai
ROUTER_MODEL_NAME=gpt-4o
MERGE_MODEL_PROVIDER=openai
MERGE_MODEL_NAME=gpt-4o

# Use a local Ollama model for the vector chroma agent
VECTOR_CHROMA_AGENT_MODEL_PROVIDER=ollama
VECTOR_CHROMA_AGENT_MODEL_NAME=llama3
```

Leave both variables empty (the default) to use the global `OPENAI_MODEL` for every agent.

> 📖 **Using Ollama (local models):** see [`docs/ollama-gemma4-setup.md`](docs/ollama-gemma4-setup.md) for instructions on starting the Ollama service and running Gemma 4 locally.

### SSE event types

| Event type | Meaning |
|---|---|
| `session` | Session ID assigned for this conversation |
| `routing` | Which sub-agents were selected (list of names) |
| `agent_token` | Intermediate reasoning token from a sub-agent |
| `token` | Final synthesis token (streamed to user) |
| `tool_start` | A sub-agent started a tool call |
| `tool_end` | A sub-agent tool call completed |
| `geojson` | GeoJSON FeatureCollection from the Map agent (rendered as interactive Leaflet map) |
| `dataviz` | Visualisation payload from the DataViz agent (charts, KPI cards, tables) |
| `dataset_choice` | Human-in-the-loop: list of dataset candidates for user disambiguation (see below) |
| `error` | An error occurred |
| `done` | Stream complete |

### Human-in-the-Loop: Dataset Disambiguation

When the `data_gouv_agent` searches for a dataset and finds **multiple results with different titles**, it will not arbitrarily pick one.  Instead it:

1. **Asks the user** to specify which dataset they want to work with (the agent's text response lists the candidates).
2. **Emits a `dataset_choice` SSE event** containing structured candidate data so the frontend can render interactive selection cards.

**`dataset_choice` event payload:**

```json
{
  "type": "dataset_choice",
  "candidates": [
    {
      "id": "abc123",
      "title": "Capteur d'ondes électromagnétiques — site A",
      "description": "Mesures journalières des champs électromagnétiques…",
      "url": "https://www.data.gouv.fr/fr/datasets/abc123/",
      "organization": "ANFR"
    }
  ]
}
```

When the user clicks a candidate card, the frontend sends a new message of the form:
`Je veux travailler avec le dataset : "<title>" (ID: <id>)`

The agent then fetches and displays the selected dataset.  
The disambiguation step is **only triggered when**:
- the search returns ≥ 2 distinct datasets, **and**
- no data file was actually fetched in the same turn.

> **AgentState field:** `pending_dataset_choice: list[dict] | None`  
> Populated by `data_gouv_agent`; cleared to `None` after successful data retrieval.

### Intent Parser

The **Intent Parser** (`intent_parser`) is the **first preparatory stage** of the
pipeline.  It analyses the raw user query and produces a structured `ParsedIntent`
before any routing or connector call takes place.

**`ParsedIntent` fields:**

| Field | Type | Description |
|---|---|---|
| `intent_type` | string | One of: `geo_search`, `geo_analysis`, `data_retrieval`, `data_analysis`, `comparison`, `temporal`, `description`, `combined`, `unknown` |
| `entities` | list[str] | Named entities extracted from the query (places, datasets, species, events …) |
| `geo_zone` | object \| null | Geographic scope — `name` (raw text), `type` (`city` / `region` / `country` / `coordinates` / `generic`), optional `bbox` |
| `temporal_range` | object \| null | Time scope — `start_date`, `end_date`, `description` (e.g. "2020–2023") |
| `intention` | string | One-sentence normalised restatement of the query |
| `language` | string | ISO 639-1 detected language code (`fr`, `en` …) |
| `confidence` | float | Confidence in [0, 1] |

**Decision strategy:**
1. **Fast-path** — empty or very short queries skip the LLM entirely and return a
   low-confidence `unknown` intent.
2. **Heuristic pre-filter** — four lightweight regex rules detect geo, temporal, stats,
   and comparison signals to populate the intent type cheaply.
3. **LLM structured output** — when heuristics are inconclusive a model call with
   `with_structured_output(ParsedIntent)` resolves the ambiguity.
4. **Error fallback** — any exception returns a safe default with `confidence: 0.0`
   so the pipeline never stalls.

The agent can be disabled by setting `INTENT_PARSER_ENABLED=false`.  When disabled,
`parsed_intent` remains `null` in the state and downstream stages fall back to their
own logic (Smart Dispatcher uses hard rules only; the LLM router uses its own prompt).

**Default temporal range (soft hint):**
When the user query contains no explicit date or time reference, the Intent Parser
automatically sets `temporal_range` to the start of the **current calendar year**
(e.g. `{"start": "2026-01-01", "end": null, "raw": "current year"}`).
This is a **soft hint only** — connector agents should use it to sort results by
recency (most recent first) but must **not** exclude older data records.
The year is computed dynamically at request time, so no code change is needed when
the year rolls over.

### Smart Dispatcher

The **Smart Dispatcher** (`smart_dispatcher`) is the **second preparatory stage**
of the pipeline.  It uses the `ParsedIntent` produced by the Intent Parser plus the
**Source Registry** metadata to deterministically select which connector agents to
invoke — **without any LLM call**.

**Scoring algorithm** (applied to every registered source):

| Signal | Score |
|---|---|
| Agent `capabilities` include a tag matching the detected `intent_type` | +3 |
| Agent `topics` overlap with extracted `entities` | +2 |
| Agent `geo_scope` covers the detected geographic zone | +2 |
| Semantic similarity to the query (ChromaDB) ≥ 0.6 | +1 |

Agents with a total score ≥ 3 are selected.  If no agent reaches the threshold, the
highest-scoring one is kept as a fallback so the pipeline always has at least one
connector to call.

The Smart Dispatcher can be disabled by setting `SMART_DISPATCHER_ENABLED=false`,
in which case the legacy **LLM router** (structured output) takes over agent selection.

### Source Registry

The **Source Registry** lives in two files:
- **`backend/config/source_registry.yml`** — canonical data file, edit this to add/modify connectors.
- **`backend/app/agent/source/source_registry.py`** — Python loader, exposes `SOURCE_REGISTRY` and helpers.

Every data-source connector declares a `SourceEntry` with the following fields:

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique identifier |
| `connector` | string | Agent key used in `agents_to_call` (e.g. `neo4j`, `postgis`) |
| `description` | string | Human-readable description — used for ChromaDB embedding **and** as override for the LLM router prompt |
| `label` | string \| null | Optional UI label shown in the frontend agent selector — overrides the default in `agent_descriptions.yml` when set |
| `capabilities` | list[str] | Capability tags matched against `intent_type` |
| `topics` | list[str] | Domain keywords for entity-overlap scoring |
| `entity_types` | list[str] | Named entity types stored in this source |
| `geo_scope` | string \| null | `"france"`, `"global"`, or `null` |
| `mcp_url` | string \| null | MCP endpoint URL for MCP-backed connectors |
| `example_questions` | list[str] | Canonical example questions used for embedding |

**Capability vocabulary:** `graph_query`, `sparql_query`, `semantic_search`,
`spatial_query`, `open_data`, `geo_analysis`, `geocoding`, `routing`,
`buffering`, `elevation`, `viewshed`, `temporal_analysis`, `statistics`,
`data_retrieval`, `data_analysis`, `geo_search`, `comparison`.

**Bootstrap:** at startup (`main.py` lifespan), `bootstrap_registry_embeddings()`
upserts all registry descriptions into the ChromaDB collection
`pangia_source_registry`.  If ChromaDB is unavailable, scoring continues using
only the deterministic rules (the semantic similarity bonus is simply skipped).

**Adding a new source to the registry:**

1. Add a new entry to `backend/config/source_registry.yml`.
2. Choose `capabilities` that match the intent types your agent handles
   (see `_INTENT_CAPABILITIES` in `smart_dispatcher.py`).
3. Restart the backend — `bootstrap_registry_embeddings()` will upsert the new entry
   automatically on startup.

### Human Output Agent

The **Human Output Agent** (`humanoutput_agent`) sits **between `post_process_router`
and `mapviz_agent` / `dataviz_agent`** in the pipeline.  Its job is to analyse the
data already gathered by the parallel sub-agents (plus the original user query)
and decide which visualisation components — a map, charts/tables, both, or
neither — are worth rendering.

**Decision strategy:**
1. **Fast-path** — if the combined content is empty, skip both visualisation agents.
2. **Clear heuristics** — strong geo keywords (map, coordinates, GeoJSON…) or
   dataviz keywords (chart, table, statistics…) resolve each side without an LLM call.
3. **LLM classification** — when signals are ambiguous (e.g. decimal numbers that
   could be coordinates *or* statistics), a lightweight LLM call with a structured
   JSON-output prompt resolves the ambiguity.
4. **Error fallback** — any exception defaults to `{needs_map: true, needs_dataviz: true}`
   so downstream agents always have a chance to run.

The agent can be disabled by setting `HUMANOUTPUT_AGENT_ENABLED=false`. When
disabled the pipeline falls back to calling both `mapviz_agent` and `dataviz_agent`
unconditionally (legacy behaviour).

### Data Visualisation Agent

The **DataViz Agent** (`dataviz_agent`) runs **sequentially after the Map agent**, reading the accumulated
`sub_results` from all parallel sub-agents to detect and format numerical / statistical data.

### Map Agent

The **Map Agent** (`mapviz_agent`) runs after the parallel data-source agents and extracts geographic
coordinates from their `sub_results` to build a GeoJSON FeatureCollection rendered as an interactive
Leaflet map in the UI.

> **Note on iterations:** the Map Agent often requires **multiple ReAct loop iterations** to complete
> its work — it typically needs one turn to call its coordinate-extraction tool, then one or more
> additional turns to format the final GeoJSON output.  If the map is not appearing, the most common
> cause is `MAPVIZ_AGENT_MAX_ITERATIONS` (or the global `AGENT_MAX_ITERATIONS`) being set too low.
> The recommended minimum is **5**; the default is **10**.



**Responsibilities:**
- Detect visualisable data (counts, averages, distributions, time-series, proportions)
- Choose the most appropriate visualisation type
- Produce chart structures compatible with **D3.js**
- Compute **KPI cards** (value, unit, variation, trend, threshold)
- Generate **formatted tables** (column headers + row data)

**Output types:**

| Type | Description | Frontend component |
|---|---|---|
| `charts` | Bar, line, pie, scatter, or histogram chart data | `ChartViewer.vue` (D3.js) |
| `kpis` | Key performance indicator cards with trend indicators | `KpiCards.vue` |
| `tables` | Tabular data with column headers and rows | `TableViewer.vue` (PrimeVue DataTable) |

When the DataViz agent produces visualisations, they are rendered in the chat interface
automatically:
- 📊 **Charts** are rendered using D3.js for bar, line, pie, scatter, and histogram types.
- 🔢 **KPI cards** display key metrics with trend direction (↑ up / ↓ down / → stable).
- 📋 **Tables** use PrimeVue DataTable for scrollable, formatted tabular display.

The DataViz agent can be **disabled without affecting any other agent** by setting
`DATAVIZ_AGENT_ENABLED=false` in your `.env` file.

---

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env and set at minimum: OPENAI_API_KEY
```

### 2. Start all services

```bash
docker compose up --build
```

| Service | URL | Purpose |
|---|---|---|
| Frontend | http://localhost:3000 | Chat UI |
| Backend API | http://localhost:8084 | FastAPI + LangGraph |
| Neo4j Browser | http://localhost:7474 | Knowledge graph |
| GraphDB Workbench | http://localhost:7200 | RDF triplestore |
| ChromaDB | http://localhost:8001 | Vector store |
| PostGIS | localhost:5434 | Spatial database |
| Phoenix UI | http://localhost:6006 | Agent observability (traces & spans) |

---

## Observability (Arize Phoenix)

All LangChain/LangGraph spans — router decisions, sub-agent calls, LLM round-trips, and tool invocations — are captured automatically via [OpenInference](https://github.com/Arize-ai/openinference) auto-instrumentation and sent to the bundled [Arize Phoenix](https://github.com/Arize-ai/phoenix) collector.

Open **http://localhost:6006** after `docker compose up` to explore:

- **Traces** – end-to-end request traces from user query to streamed answer
- **Spans** – individual steps: routing decision, each sub-agent ReAct loop, LLM calls, tool starts/ends
- **LLM call inspector** – prompt tokens, completion tokens, latency, model name

Phoenix is registered during FastAPI's lifespan startup (`backend/app/main.py`) so it never blocks the application from starting if the collector is temporarily unavailable.

### Configuration

| Variable | Default | Description |
|---|---|---|
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://phoenix:6006/v1/traces` | OTLP HTTP endpoint (set automatically in Docker) |
| `PHOENIX_PROJECT_NAME` | `pangia-geoia` | Project name shown in the Phoenix UI |

Override `PHOENIX_PROJECT_NAME` in `.env` to organise traces across multiple environments.

---

## Project structure

```
pangia-poc/
├── docker-compose.yml
├── .env.example
├── docs/
│   └── pangIA_logo.png
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── config/                  # Runtime configuration files (editable without code changes)
│   │   ├── source_registry.yml     # Canonical list of data-source connectors (SourceEntry data)
│   │   ├── agent_descriptions.yml  # Agent descriptions for the legacy LLM router prompt
│   │   └── orchestrator_config.yml # Router prompt preamble and routing rules
│   └── app/
│       ├── main.py              # FastAPI app factory + lifespan
│       ├── config.py            # Pydantic settings
│       ├── api/
│       │   └── routes/          # Route modules
│       │       ├── __init__.py      # Router aggregator (prefix /api)
│       │       ├── chat.py          # POST /api/chat (SSE streaming)
│       │       ├── suggestions.py   # GET /api/suggestions
│       │       └── agents.py        # GET /api/agents, GET /api/health
│       ├── agent/
│       │   ├── model_config.py      # LLM provider abstraction (per-agent config)
│       │   ├── utils.py             # Shared helpers: get_active_agents, get_agent_labels, is_agent_enabled
│       │   ├── graph.py             # Backward-compat shim → core/orchestrator.py
│       │   ├── core/                # System brains
│       │   │   ├── state.py             # AgentState + ParsedIntent / GeoZone / TemporalRange models
│       │   │   ├── orchestrator.py      # Main orchestrator (4 pipeline topologies)
│       │   │   ├── geo_orchestrator.py  # Geospatial sub-orchestrator
│       │   │   ├── humanoutput_agent.py # Output decision (map / dataviz routing)
│       │   │   ├── intent_parser.py     # Stage 1 – query analysis → ParsedIntent
│       │   │   └── smart_dispatcher.py  # Stage 2 – metadata scoring → agents_to_call
│       │   ├── source/              # Source Registry package
│       │   │   └── source_registry.py   # SourceEntry models + ChromaDB bootstrap (data → backend/config/)
│       │   ├── connectors/          # Data-source agents (read-only)
│       │   │   ├── neo4j_agent.py   # Knowledge Graph sub-agent (Cypher)
│       │   │   ├── rdf_agent.py     # RDF sub-agent (SPARQL / GraphDB)
│       │   │   ├── vector_chroma_agent.py  # Vector sub-agent (ChromaDB)
│       │   │   ├── postgis_agent.py # Spatial SQL sub-agent (PostGIS)
│       │   │   └── data_gouv_agent.py # French open-data sub-agent (data.gouv.fr MCP)
│       │   ├── geo/                 # Geospatial processing agents
│       │   │   ├── l1_primitives/   # Atomic operations
│       │   │   │   ├── address_agent.py    # Geocoding address ↔ coordinates
│       │   │   │   ├── spatial_parser.py   # NL spatial understanding
│       │   │   │   ├── distance_agent.py   # Great-circle distance
│       │   │   │   └── buffer_agent.py     # Circular buffer zone
│       │   │   ├── l2_analysis/     # Composed analyses
│       │   │   │   ├── proximity_agent.py      # Nearest-entity search
│       │   │   │   ├── intersection_agent.py   # Spatial overlap analysis
│       │   │   │   ├── area_agent.py           # Polygon surface area
│       │   │   │   ├── hotspot_agent.py        # Cluster detection & density
│       │   │   │   ├── isochrone_agent.py      # Accessibility zones
│       │   │   │   └── shortest_path_agent.py  # Route optimisation
│       │   │   └── l3_advanced/     # Advanced / external processing
│       │   │       ├── elevation_agent.py      # Altitude (Open-Meteo)
│       │   │       ├── geometry_ops_agent.py   # GeoJSON transformations
│       │   │       ├── temporal_agent.py       # Spatio-temporal patterns
│       │   │       └── viewshed_agent.py       # Geometric visibility analysis
│       │   ├── output/              # Rendering and presentation agents
│       │   │   ├── mapviz_agent.py       # Interactive map (GeoJSON / Leaflet)
│       │   │   ├── dataviz_agent.py      # Charts / KPIs / tables
│       │   │   └── synthesis_agent.py   # Final fusion & reformulation
│       │   └── mermaid_graph/       # Auto-generated LangGraph diagrams
│       └── db/
│           ├── neo4j_client.py
│           ├── graphdb_client.py
│           ├── chroma_client.py
│           ├── postgis_client.py
│           ├── redis_client.py
│           ├── seed.py          # Seed runner (reads active theme, populates all stores)
│           └── themes/
│               ├── __init__.py  # SeedTheme dataclass + get_active_theme()
│               └── dinosaurs.py # Built-in seed theme (Mesozoic palaeontology)
└── frontend-client/         # ← frontend (React 19 + Tailwind CSS v4)
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── App.tsx              # Root layout (Sidebar + main)
        ├── main.tsx
        ├── types.ts             # Message, DataViz types
        ├── hooks/
        │   ├── usePangiaChat.ts # SSE streaming hook
        │   └── useSuggestions.ts
        └── components/
            ├── layout/
            │   └── Sidebar.tsx
            ├── chat/
            │   ├── ChatMessage.tsx
            │   ├── MessageList.tsx
            │   └── ChatInput.tsx
            ├── MapViewer.tsx    # Leaflet dark map
            └── DataViz/
                ├── DataVizViewer.tsx
                ├── ChartViewer.tsx  # D3 bar/line/pie/scatter
                ├── KpiCards.tsx
                └── TableViewer.tsx
```

## Development (without Docker)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env  # set OPENAI_API_KEY and data-store connection strings
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend-client
npm install
npm start
# → http://localhost:3000 (proxies /api to localhost:8084)
```

---

## Seed themes

The application is populated with sample data at startup via a **seed theme**.
The active theme is selected by the `SEED_THEME` environment variable (default: `pandemic`).
Seeding is controlled by `SEED_DB` (default: `true`); set it to `false` in production.

Each theme provides data for all four datastores (Neo4j, PostGIS, GraphDB, ChromaDB)
as well as the schema prompts, agent guidelines, and UI suggestions used by the agents.

### PostGIS schema isolation

Each built-in theme stores its PostGIS tables in a **dedicated PostgreSQL schema**
(not in the default `public` schema):

| Theme | PostgreSQL schema | Tables |
|---|---|---|
| `dinosaurs` | `dinosaures` | `dinosaures.fossil_sites`, `dinosaures.paleo_continents` |
| `pandemic` | `pandemic` | `pandemic.outbreak_sites`, `pandemic.affected_regions` |

The schema is created automatically during seeding (`CREATE SCHEMA IF NOT EXISTS …`).
When adding a new theme, follow the same convention: create a schema named after the
theme and qualify every table reference with that schema (e.g. `myschema.mytable`).
Update `postgis_schema_prompt` to include the schema name so the PostGIS agent
generates correctly qualified queries.

### Switching the theme

Set `SEED_THEME` in your `.env` before starting the stack:

```bash
SEED_THEME=my_theme docker compose up --build
```

### Adding a new theme

1. Create `backend/app/db/themes/<my_theme>.py` and expose a `theme` variable of
   type `SeedTheme` (see `backend/app/db/themes/__init__.py` for the full dataclass).
   Use `backend/app/db/themes/dinosaurs.py` as a reference implementation.

2. Fill in **all relevant fields** of `SeedTheme`:

   | Field | Purpose |
   |---|---|
   | `neo4j_statements` | Idempotent Cypher statements (MERGE) to seed the graph |
   | `postgis_statements` | DDL + DML SQL statements for tables and rows — **always start with `CREATE SCHEMA IF NOT EXISTS <schema>` and qualify every table with that schema** |
   | `graphdb_named_graph` + `graphdb_turtle` | Named graph URI and Turtle RDF content |
   | `chroma_documents` | List of `{"text": str, "metadata": dict}` docs to embed |
   | `neo4j_schema_prompt` | Graph schema description injected into the Neo4j agent |
   | `postgis_schema_prompt` | Table/column description injected into the PostGIS agent — **include the schema name and a reminder to qualify table names** |
   | `rdf_schema_prompt` | Ontology description injected into the RDF agent |
   | `neo4j_guidelines` | Theme-specific query hints for the Neo4j agent |
   | `postgis_guidelines` | Theme-specific query hints for the PostGIS agent |
   | `rdf_guidelines` | Theme-specific query hints for the RDF agent |
   | `vector_guidelines` | Theme-specific hints for the Vector agent |
   | `suggestions` | Example prompts shown in the chat UI |

3. **Review the router's agent descriptions and routing rules** in
   `backend/app/agent/core/orchestrator.py`:
   - `_AGENT_DESCRIPTIONS` — the short capability blurb shown to the router LLM
     for each agent.  If your theme stores data in a way that differs from the
     generic description (e.g. PostGIS holds domain-specific tables with
     coordinates), refine the description so the router knows to select that agent.
   - `_EXTRA_ROUTING_RULES` — explicit rules that override or supplement the
     router's judgment for common question patterns in your domain (e.g. "questions
     about X location → include both neo4j and postgis").  Add domain-specific
     rules here rather than embedding them in the agent descriptions.

   Keep both sections as generic as possible; add only rules that are genuinely
   necessary for correct routing in your theme.

4. Set `SEED_THEME=<my_theme>` and start the stack.

---

## Adding a new sub-agent

Sub-agents live in `backend/app/agent/`.  To add one:

1. **Create `backend/app/agent/<category>/<name>_agent.py`** with an `async def run(state: AgentState) -> dict` function.
   Follow the existing agents as a template (ReAct loop: LLM + tools, write result to `sub_results`).
   Place the file in the appropriate subdirectory:
   - `connectors/` for new data-source agents
   - `geo/l1_primitives/`, `geo/l2_analysis/`, or `geo/l3_advanced/` for geospatial agents
   - `output/` for rendering/post-processing agents

2. **Connect it to the orchestrator** in `backend/app/agent/core/orchestrator.py`:
   - Declare it as a valid literal in `RoutingDecision.agents`.
   - Add an import and a `Send` mapping in `fan_out_node`.
   - Register it in `backend/app/agent/output/synthesis_agent.py → AGENT_LABELS`.
   - Update `ROUTER_SYSTEM` to include its description and routing rules (used as
     legacy fallback when `SMART_DISPATCHER_ENABLED=false`).
   - **Add a `SourceEntry`** to `backend/config/source_registry.yml` with appropriate
     `capabilities`, `topics`, and `geo_scope` so the Smart Dispatcher can route to it.

3. **Write a clear `_BASE_SYSTEM_PROMPT`** for the agent. Keep generic query mechanics
   (tool selection, output format, error handling) in the base prompt in the agent file.
   Move anything **specific to the active dataset** into the theme's corresponding
   `<store>_guidelines` field so any future theme can override it without touching agent code.

   **Frugality principle** — every system prompt must end with:
   ```
   - Be concise: answer in the fewest words needed. No preambles, no repetition.
   ```
   This is intentional: PangIA is designed to run on small local models (e.g. `gemma4:e2b`
   via Ollama) where token budget is precious. Verbose preambles waste inference time and
   degrade multi-agent throughput. Keep responses dense and direct.

4. **Define the database schema** in the seed theme's `<store>_schema_prompt` field
   (node labels, relationship types, table columns, ontology prefixes, etc.).
   The more precise the schema description, the better the LLM will generate correct queries.

5. **Expose a `GET /api/suggestions`** update is automatic — suggestions are already
   served from the active theme's `suggestions` list.

---

## Geo Agent – Geospatial Analysis

> ⚠️ **Not operational – needs rework before use.**
> The Geo Agent is currently broken following the refactoring of utility functions into
> `backend/libs/geo/`.  Imports and end-to-end pipeline consistency have not yet been fully
> validated in real conditions.  Disable it via `GEO_AGENT_ENABLED=false` to avoid blocking
> the backend startup in the meantime.

The **Geo Agent** (`backend/app/agent/core/geo_orchestrator.py`) is a specialised
orchestrator for advanced geospatial analysis tasks.  It is available as a parallel
sub-agent in the orchestrator (enabled by default via `GEO_AGENT_ENABLED=true`).

When the orchestrator router selects `geo`, the Geo Agent uses its own internal LLM router
to dispatch to the most appropriate geo sub-agents and merges their outputs.

### Sub-agent hierarchy

| Level | Key | Agent file | Capability |
|-------|-----|-----------|------------|
| 1 – Primitives | `geo_address` | `geo/l1_primitives/address_agent.py` | Geocoder – address ↔ coordinates (Nominatim) |
| 1 – Primitives | `geo_spatial_parser` | `geo/l1_primitives/spatial_parser.py` | SpatialParser – natural language spatial understanding |
| 1 – Primitives | `geo_distance` | `geo/l1_primitives/distance_agent.py` | DistanceCalc – great-circle distance calculations |
| 1 – Primitives | `geo_buffer` | `geo/l1_primitives/buffer_agent.py` | BufferAnalyser – circular and multi-ring buffer zones |
| 1 – Primitives | `geo_isochrone` | `geo/l2_analysis/isochrone_agent.py` | Isochrone – travel-time accessibility zones |
| 2 – Analysis | `geo_proximity` | `geo/l2_analysis/proximity_agent.py` | Proximity – nearest-entity search and ranking |
| 2 – Analysis | `geo_intersection` | `geo/l2_analysis/intersection_agent.py` | Intersection – bounding-box overlap and containment |
| 2 – Analysis | `geo_area` | `geo/l2_analysis/area_agent.py` | AreaCalculator – polygon surface area computation |
| 2 – Analysis | `geo_hotspot` | `geo/l2_analysis/hotspot_agent.py` | Hotspot – point-cluster detection and density |
| 2 – Analysis | `geo_shortest_path` | `geo/l2_analysis/shortest_path_agent.py` | ShortestPath – waypoint route optimisation |
| 3 – Advanced | `geo_elevation` | `geo/l3_advanced/elevation_agent.py` | Elevation – altitude retrieval (Open-Meteo API) |
| 3 – Advanced | `geo_geometry_ops` | `geo/l3_advanced/geometry_ops_agent.py` | GeometryOps – GeoJSON transformations and validation |
| 3 – Advanced | `geo_temporal` | `geo/l3_advanced/temporal_agent.py` | TemporalAnalyst – spatio-temporal pattern detection |
| 3 – Advanced | `geo_viewshed` | `geo/l3_advanced/viewshed_agent.py` | Viewshed – geometric visibility analysis |

### Configuration

| Environment variable | Default | Description |
|---|---|---|
| `GEO_AGENT_ENABLED` | `true` | Enable/disable the entire Geo Agent |
| `GEO_AGENT_MODEL_PROVIDER` | `` | LLM provider for the internal geo router and merge step |
| `GEO_AGENT_MODEL_NAME` | `` | LLM model name (falls back to global `OPENAI_MODEL`) |
| `GEO_AGENT_MAX_ITERATIONS` | `0` | Max ReAct loop iterations (0 = global default) |
| `GEO_<SUBAGENT>_AGENT_MODEL_PROVIDER` | `` | Per-sub-agent model provider override |
| `GEO_<SUBAGENT>_AGENT_MODEL_NAME` | `` | Per-sub-agent model name override |
| `GEO_<SUBAGENT>_AGENT_MAX_ITERATIONS` | `0` | Per-sub-agent max iterations override |

Replace `<SUBAGENT>` with `ADDRESS`, `SPATIAL_PARSER`, `DISTANCE`, `BUFFER`,
`ISOCHRONE`, `PROXIMITY`, `INTERSECTION`, `AREA`, `HOTSPOT`, `SHORTEST_PATH`,
`ELEVATION`, `GEOMETRY_OPS`, `TEMPORAL`, or `VIEWSHED`.

### Notes

- Isochrone, buffer, and viewshed computations are **geometric approximations**
  based on straight-line (great-circle) distances and do not use road networks or DEMs.
- Elevation data is retrieved from the [Open-Meteo elevation API](https://open-meteo.com/)
  which is free and requires no API key.
- For precise polygon operations (intersection, area, routing), the PostGIS agent
  (`postgis_agent.py`) with PostGIS SQL remains the recommended approach.
