<!--
SPDX-FileCopyrightText: 2026 AlitaBernachot

SPDX-License-Identifier: MIT
-->

# Backend V1 — PangIA Legacy Multi-Agent System

> **Port:** `8084`  
> **Stack:** FastAPI · SSE · LangChain · LangGraph  
> ⚠️ **Legacy.** The active backend is [`backend-ai/`](../backend-ai/README.md) (port 8086).  
> This backend is kept for reference; it is still started by `docker compose up`.

---

## Table of Contents

- [Multi-agent architecture](#multi-agent-architecture)
  - [Agent enable / disable flags](#agent-enable--disable-flags)
  - [Agent fault tolerance](#agent-fault-tolerance)
  - [Agent ReAct loop iterations](#agent-react-loop-iterations)
  - [Per-agent LLM configuration](#per-agent-llm-configuration)
  - [SSE event types](#sse-event-types)
  - [Human-in-the-Loop: Dataset Disambiguation](#human-in-the-loop-dataset-disambiguation)
  - [Intent Parser](#intent-parser)
  - [Smart Dispatcher](#smart-dispatcher)
  - [Source Registry](#source-registry)
  - [Human Output Agent](#human-output-agent)
  - [Data Visualisation Agent](#data-visualisation-agent)
  - [Map Agent](#map-agent)
  - [Synthesis Agent](#synthesis-agent)
- [Development (without Docker)](#development-without-docker)
- [Seed themes](#seed-themes)
  - [PostGIS schema isolation](#postgis-schema-isolation)
  - [Switching the theme](#switching-the-theme)
  - [Adding a new theme](#adding-a-new-theme)
- [Adding a new sub-agent](#adding-a-new-sub-agent)
- [Geo Agent – Geospatial Analysis](#geo-agent--geospatial-analysis)
  - [Sub-agent hierarchy](#sub-agent-hierarchy)
  - [Configuration](#configuration)
  - [Notes](#notes)
- [data.gouv.fr Agent](#datagouvfr-agent)

---

## Multi-agent architecture

> 📊 **Mermaid graph:** [`backend/app/agent/mermaid_graph/orchestrator_graph.mmd`](app/agent/mermaid_graph/orchestrator_graph.mmd)  
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

The query passes through up to two **preparatory stages** before being fanned out to the data-source connectors:

1. **Intent Parser** (`intent_parser`) — extracts a structured `ParsedIntent` using fast heuristics followed by an LLM structured-output call when needed. Enabled by `INTENT_PARSER_ENABLED` (default `true`).

2. **Smart Dispatcher** (`smart_dispatcher`) — uses the `ParsedIntent` to score every registered source against the **Source Registry** metadata. Returns a ranked `agents_to_call` list **without any LLM call**. Enabled by `SMART_DISPATCHER_ENABLED` (default `true`).

### Agent enable / disable flags

| Variable | Default | Description |
|---|---|---|
| `INTENT_PARSER_ENABLED` | `true` | Stage 1 – query analyser |
| `SMART_DISPATCHER_ENABLED` | `true` | Stage 2 – metadata-based router |
| `NEO4J_AGENT_ENABLED` | `true` | Knowledge Graph connector |
| `RDF_AGENT_ENABLED` | `true` | RDF/Linked Data connector |
| `VECTOR_CHROMA_AGENT_ENABLED` | `true` | Semantic search connector |
| `POSTGIS_AGENT_ENABLED` | `true` | Spatial SQL connector |
| `DATAGOUV_MCP_AGENT_ENABLED` | `true` | French open-data connector |
| `GEO_AGENT_ENABLED` | `true` | Geospatial analysis orchestrator |
| `HUMANOUTPUT_AGENT_ENABLED` | `true` | Output decision agent |
| `MAPVIZ_AGENT_ENABLED` | `true` | Geographic visualisation agent |
| `DATAVIZ_AGENT_ENABLED` | `true` | Data visualisation agent |

### Agent fault tolerance

Every agent's `run()` wraps its logic in a top-level `try/except`. If an agent raises any exception it catches it and returns a graceful fallback result so the chain never crashes.

### Agent ReAct loop iterations

| Variable | Default | Description |
|---|---|---|
| `AGENT_MAX_ITERATIONS` | `10` | Global fallback |
| `NEO4J_AGENT_MAX_ITERATIONS` | `0` | 0 = use global |
| `RDF_AGENT_MAX_ITERATIONS` | `0` | |
| `VECTOR_CHROMA_AGENT_MAX_ITERATIONS` | `0` | |
| `POSTGIS_AGENT_MAX_ITERATIONS` | `0` | |
| `MAPVIZ_AGENT_MAX_ITERATIONS` | `0` | |
| `DATAGOUV_MCP_AGENT_MAX_ITERATIONS` | `0` | |
| `DATAVIZ_AGENT_MAX_ITERATIONS` | `0` | |

### Per-agent LLM configuration

Every agent can use a different LLM independently of the global `OPENAI_MODEL`:

| Variable pattern | Example | Description |
|---|---|---|
| `<AGENT>_MODEL_PROVIDER` | `openai`, `anthropic`, `ollama` | Provider for this agent |
| `<AGENT>_MODEL_NAME` | `gpt-4o`, `claude-3-5-sonnet-latest` | Model name |

Available prefixes: `ROUTER`, `INTENT_PARSER_AGENT`, `NEO4J_AGENT`, `RDF_AGENT`, `VECTOR_CHROMA_AGENT`, `POSTGIS_AGENT`, `MAPVIZ_AGENT`, `DATAGOUV_MCP_AGENT`, `DATAVIZ_AGENT`, `MERGE`.

### SSE event types

| Event type | Meaning |
|---|---|
| `session` | Session ID assigned |
| `routing` | Which sub-agents were selected |
| `agent_token` | Intermediate reasoning token |
| `token` | Final synthesis token |
| `tool_start` | Sub-agent started a tool call |
| `tool_end` | Sub-agent tool call completed |
| `geojson` | GeoJSON FeatureCollection |
| `dataviz` | Visualisation payload |
| `dataset_choice` | Human-in-the-loop dataset candidates |
| `error` | Error occurred |
| `done` | Stream complete |

### Human-in-the-Loop: Dataset Disambiguation

When `datagouv_mcp_agent` finds multiple datasets it emits a `dataset_choice` SSE event:

```json
{
  "type": "dataset_choice",
  "candidates": [
    {
      "id": "abc123",
      "title": "Capteur d'ondes électromagnétiques — site A",
      "description": "Mesures journalières…",
      "url": "https://www.data.gouv.fr/fr/datasets/abc123/",
      "organization": "ANFR"
    }
  ]
}
```

The user selects a candidate and the frontend sends a follow-up message targeting it.

### Intent Parser

`ParsedIntent` fields:

| Field | Type | Description |
|---|---|---|
| `intent_type` | string | `geo_search`, `geo_analysis`, `data_retrieval`, `data_analysis`, `comparison`, `temporal`, `description`, `combined`, `unknown` |
| `entities` | list[str] | Named entities |
| `geo_zone` | object | `name`, `type`, optional `bbox` |
| `temporal_range` | object | `start_date`, `end_date`, `description` |
| `intention` | string | Normalised restatement |
| `language` | string | ISO 639-1 code |
| `confidence` | float | 0–1 |

When the query contains no explicit date, `temporal_range` defaults to the start of the current calendar year as a soft recency hint.

### Smart Dispatcher

Scoring per source entry:

| Signal | Score |
|---|---|
| Capability matches `intent_type` | +3 |
| Topic overlaps with entities | +2 |
| `geo_scope` covers detected zone | +2 |
| Semantic similarity ≥ 0.6 (ChromaDB) | +1 |

Agents scoring ≥ 3 are selected; if none qualify, the highest-scoring one is used as fallback.

### Source Registry

- **`backend/config/source_registry.yml`** — canonical data file.
- **`backend/app/agent/source/source_registry.py`** — Python loader.

`SourceEntry` fields:

| Field | Description |
|---|---|
| `id` / `connector` | Agent key |
| `description` | Embeddable description for ChromaDB |
| `label` | Optional UI label |
| `capabilities` | Capability tags |
| `topics` | Domain keywords |
| `entity_types` | Entity types |
| `geo_scope` | `"france"`, `"global"`, or `null` |
| `example_questions` | Representative questions |

Bootstrap: at startup, `bootstrap_registry_embeddings()` upserts all entries into the `pangia_source_registry` ChromaDB collection.

### Human Output Agent

Analyses `sub_results` and decides which visualisation components to render (map, charts, both, or neither) using fast heuristics and a fallback LLM call. Disable with `HUMANOUTPUT_AGENT_ENABLED=false`.

### Data Visualisation Agent

Reads `sub_results` and builds `dataviz: {charts, kpis, tables}` for the frontend.

| Type | Frontend component |
|---|---|
| `charts` | D3.js bar / line / pie / scatter / histogram |
| `kpis` | KPI cards (value, unit, trend, threshold) |
| `tables` | PrimeVue DataTable |

### Map Agent

Extracts `geojson: FeatureCollection` from `sub_results`. Rendered as a Leaflet map.

> Recommended minimum `MAPVIZ_AGENT_MAX_ITERATIONS`: **5**.

### Synthesis Agent

Final node — rewrites all raw results into a single concise Markdown answer.  
**File:** `app/agent/output/synthesis_agent.py`

---

## Development (without Docker)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env  # set OPENAI_API_KEY and connection strings
uvicorn app.main:app --reload
```

---

## Seed themes

The application is populated with sample data at startup via a **seed theme** (`SEED_THEME`, default: `pandemic`). Seeding is controlled by `SEED_DB` (default: `true`).

### PostGIS schema isolation

| Theme | PostgreSQL schema | Tables |
|---|---|---|
| `dinosaurs` | `dinosaures` | `fossil_sites`, `paleo_continents` |
| `pandemic` | `pandemic` | `outbreak_sites`, `affected_regions` |

### Switching the theme

```bash
SEED_THEME=my_theme docker compose up --build
```

### Adding a new theme

1. Create `app/db/themes/<my_theme>.py` and expose a `theme: SeedTheme` variable (see `app/db/themes/__init__.py`).
2. Fill all `SeedTheme` fields:

| Field | Purpose |
|---|---|
| `neo4j_statements` | Idempotent Cypher (MERGE) |
| `postgis_statements` | DDL + DML — start with `CREATE SCHEMA IF NOT EXISTS <schema>` |
| `graphdb_named_graph` + `graphdb_turtle` | Named graph URI + Turtle RDF |
| `chroma_documents` | `[{"text": str, "metadata": dict}]` |
| `neo4j_schema_prompt` | Graph schema for the Neo4j agent |
| `postgis_schema_prompt` | Table/column description for the PostGIS agent |
| `rdf_schema_prompt` | Ontology description for the RDF agent |
| `*_guidelines` | Theme-specific query hints |
| `suggestions` | Example prompts for the UI |

3. Update `_AGENT_DESCRIPTIONS` / `_EXTRA_ROUTING_RULES` in `app/agent/core/orchestrator.py` if needed.
4. Set `SEED_THEME=<my_theme>` and start the stack.

---

## Adding a new sub-agent

1. Create `app/agent/<category>/<name>_agent.py` with `async def run(state: AgentState) -> dict`.
2. Connect to the orchestrator (`app/agent/core/orchestrator.py`):
   - Add to `RoutingDecision.agents`.
   - Add `Send` mapping in `fan_out_node`.
   - Register in `synthesis_agent.py → AGENT_LABELS`.
   - Add a `SourceEntry` to `config/source_registry.yml`.
3. Write a `_BASE_SYSTEM_PROMPT`. Move dataset-specific parts to the theme's `<store>_guidelines`.
4. End every prompt with: `- Be concise: answer in the fewest words needed.`

---

## Geo Agent – Geospatial Analysis

> ⚠️ **Not operational** — broken after the `backend/libs/geo/` refactor. Disable via `GEO_AGENT_ENABLED=false`.

The **Geo Agent** (`app/agent/core/geo_orchestrator.py`) is a specialised sub-orchestrator for advanced geospatial analysis tasks.

### Sub-agent hierarchy

| Level | Key | File | Capability |
|---|---|---|---|
| 1 | `geo_address` | `l1_primitives/address_agent.py` | Geocoding (Nominatim) |
| 1 | `geo_spatial_parser` | `l1_primitives/spatial_parser.py` | NL spatial understanding |
| 1 | `geo_distance` | `l1_primitives/distance_agent.py` | Great-circle distance |
| 1 | `geo_buffer` | `l1_primitives/buffer_agent.py` | Buffer zones |
| 1 | `geo_isochrone` | `l2_analysis/isochrone_agent.py` | Travel-time accessibility |
| 2 | `geo_proximity` | `l2_analysis/proximity_agent.py` | Nearest-entity search |
| 2 | `geo_intersection` | `l2_analysis/intersection_agent.py` | Spatial overlap |
| 2 | `geo_area` | `l2_analysis/area_agent.py` | Polygon surface area |
| 2 | `geo_hotspot` | `l2_analysis/hotspot_agent.py` | Cluster detection |
| 2 | `geo_shortest_path` | `l2_analysis/shortest_path_agent.py` | Route optimisation |
| 3 | `geo_elevation` | `l3_advanced/elevation_agent.py` | Altitude (Open-Meteo) |
| 3 | `geo_geometry_ops` | `l3_advanced/geometry_ops_agent.py` | GeoJSON transforms |
| 3 | `geo_temporal` | `l3_advanced/temporal_agent.py` | Spatio-temporal patterns |
| 3 | `geo_viewshed` | `l3_advanced/viewshed_agent.py` | Visibility analysis |

### Configuration

| Variable | Default | Description |
|---|---|---|
| `GEO_AGENT_ENABLED` | `true` | Enable/disable |
| `GEO_AGENT_MODEL_PROVIDER` | `` | LLM provider |
| `GEO_AGENT_MODEL_NAME` | `` | Model name |
| `GEO_<SUBAGENT>_AGENT_MODEL_PROVIDER` | `` | Per-sub-agent override |
| `GEO_<SUBAGENT>_AGENT_MODEL_NAME` | `` | |

### Notes

- Buffer, isochrone, viewshed are **geometric approximations** (great-circle), not road-network based.
- Elevation uses the [Open-Meteo API](https://open-meteo.com/) (free, no key required).

---

## data.gouv.fr Agent

See [`app/agent/connectors/README.md`](app/agent/connectors/README.md).
