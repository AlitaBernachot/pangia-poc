<!--
SPDX-FileCopyrightText: 2026 AlitaBernachot

SPDX-License-Identifier: MIT
-->

# Backend V2 — PangIA Second-Generation Multi-Agent System

> **Port:** `8086`  
> **Stack:** FastAPI · asyncio · LangChain · LangGraph · PostgreSQL/pgvector · Redis

This is the second-generation backend for PangIA. It adds guardrails, structured HITL (human-in-the-loop), reusable agent-level disambiguation, long-term memory, audit trails, and a clean inheritance-based agent hierarchy on top of the V1 concepts.

---

## Table of Contents

- [Backend V2 — PangIA Second-Generation Multi-Agent System](#backend-v2--pangia-second-generation-multi-agent-system)
  - [Table of Contents](#table-of-contents)
  - [Directory structure](#directory-structure)
  - [Orchestrator graph topology](#orchestrator-graph-topology)
  - [Agent catalogue](#agent-catalogue)
  - [BaseAgent — the reusable base class](#baseagent--the-reusable-base-class)
    - [Agent inheritance hierarchy](#agent-inheritance-hierarchy)
    - [Lifecycle hooks](#lifecycle-hooks)
    - [Prompt loading](#prompt-loading)
    - [Source-augmented prompts](#source-augmented-prompts)
    - [Subgraph compilation](#subgraph-compilation)
    - [Agent-level choice requests (`request_choice`)](#agent-level-choice-requests-request_choice)
  - [HITL — ambiguity clarification](#hitl--ambiguity-clarification)
  - [Choice flow — agent-level disambiguation](#choice-flow--agent-level-disambiguation)
    - [How it works end-to-end](#how-it-works-end-to-end)
    - [Reusing `request_choice` in another agent](#reusing-request_choice-in-another-agent)
  - [Guardrails](#guardrails)
  - [Memory](#memory)
    - [Short-term memory](#short-term-memory)
    - [Long-term memory](#long-term-memory)
  - [Audit trail](#audit-trail)
  - [Routing](#routing)
    - [SmartDispatcherAgent (default, no LLM)](#smartdispatcheragent-default-no-llm)
    - [DynamicRouter (LLM-based fallback)](#dynamicrouter-llm-based-fallback)
    - [Source registry](#source-registry)
  - [Post-processing pipeline](#post-processing-pipeline)
    - [HumanOutputAgent](#humanoutputagent)
    - [DataVizAgent](#datavizagent)
    - [MapVizAgent](#mapvizagent)
  - [Synthesis agent](#synthesis-agent)
  - [DB client library (`libs/client/`)](#db-client-library-libsclient)
  - [data.gouv.fr MCP agent](#datagouvfr-mcp-agent)
    - [Capabilities](#capabilities)
    - [Dataset disambiguation via `request_choice`](#dataset-disambiguation-via-request_choice)
    - [Download links](#download-links)
  - [SSE event types](#sse-event-types)
    - [`choice_request` event payload](#choice_request-event-payload)
  - [API endpoints](#api-endpoints)
    - [`POST /api/chat`](#post-apichat)
    - [`POST /api/hitl/respond`](#post-apihitlrespond)
    - [`POST /api/choice/respond`](#post-apichoicerespond)
  - [Environment variables](#environment-variables)
  - [Configurable system prompts](#configurable-system-prompts)
  - [Adding a new agent](#adding-a-new-agent)
  - [Running locally (without Docker)](#running-locally-without-docker)

---

## Directory structure

```
backend-ai/
├── Dockerfile                      Python 3.12-slim image, exposes port 8086
├── requirements.txt
├── init.sql                        PostgreSQL DDL (audit_logs, long_term_memory)
├── init_postgis.sql                PostGIS demo data (lieux_interet, communes, zones_risque)
├── config/
│   ├── source_registry.yml         Declarative connector manifest (used by SmartDispatcher)
│   └── prompts/                    One YAML file per agent — overrides hardcoded defaults
│       ├── ambiguity_agent.yaml
│       ├── datagouv_mcp_agent.yaml
│       ├── dataviz_agent.yaml
│       ├── intent_parser_agent.yaml
│       ├── geonetwork_mcp_agent.yaml
│       ├── humanoutput_agent.yaml
│       ├── mapviz_agent.yaml
│       ├── neo4j_agent.yaml        Step-1 (query generation) prompt
│       ├── postgis_agent.yaml      Step-1 (query generation) prompt
│       ├── rag_agent.yaml          Step-2 (synthesis) prompt
│       ├── rdf_agent.yaml          Step-1 (query generation) prompt
│       ├── summary_agent.yaml
│       ├── synthesis_agent.yaml
│       └── vector_chroma_agent.yaml  Step-2 (synthesis) prompt
├── libs/
│   ├── datagouv.py
│   ├── filereader.py
│   ├── query_expander.py
│   ├── similarity.py
│   └── client/                     DB client package — one module per data store
│       ├── __init__.py             Re-exports all public client functions
│       ├── chroma_client.py        ChromaDB async HTTP client (similarity_search, add_documents)
│       ├── graphdb_client.py       GraphDB/Ontotext SPARQL client (run_sparql_select, run_sparql_construct)
│       ├── neo4j_client.py         Neo4j async driver (run_readonly_query, run_query)
│       ├── postgis_client.py       asyncpg connection pool (run_spatial_query, run_write_query)
│       └── redis_client.py         Redis async client (load_session, save_session)
└── app/
    ├── main.py                     FastAPI app factory + lifespan (CORS, router mount)
    ├── config.py                   Pydantic settings (all env-var driven, see below)
    ├── db.py                       Async SQLAlchemy engine
    ├── models.py                   Pydantic models shared across the system
    │                                 AgentInput, AgentOutput, ExecutionPlan,
    │                                 HITLRequest, HITLResponse,
    │                                 ChoiceItem, ChoiceRequest, ChoiceResponse
    ├── api/
    │   └── routes/
    │       ├── chat.py             POST /api/chat, POST /api/hitl/respond,
    │       │                       POST /api/choice/respond, GET /api/health,
    │       │                       GET /api/sources
    │       └── suggestions.py      GET /api/suggestions
    └── pangiagent/
        ├── state.py                OrchestratorState + SubAgentState TypedDicts
        ├── audit.py                AuditService — async SHA-256 hash-chain writer
        ├── memory.py               ShortTermMemory (Redis) + LongTermMemory (pgvector)
        ├── guardrails.py           check_toxic_input, check_output_length, check_ambiguous_intent
        ├── router.py               DynamicRouter — LLM → ExecutionPlan (fallback when SmartDispatcher disabled)
        ├── source_registry.py      SourceRegistry loader + ChromaDB bootstrap
        ├── hitl.py                 HITLManager — asyncio.Future-based suspend/resume + per-session notification queues
        ├── sse_stream.py           run_graph_to_queue / drain_queue_to_sse
        ├── model_config.py         Per-agent LLM provider/model resolution
        ├── graph.py                AGENTS + OUTPUT_AGENTS + SYNTHESIS_AGENT registry; ORCHESTRATOR_GRAPH
        ├── mermaid_graph/          Auto-generated LangGraph Mermaid diagrams (written at startup)
        └── agents/
            ├── base_agents/                Base agent package (abstract classes + mixins)
            │   ├── __init__.py             Re-exports BaseAgent, BaseReActAgent, BaseAddSourcesAgent
            │   ├── base_agent.py           BaseAgent (abstract) — guardrails, prompt loading, subgraph, request_choice
            │   ├── base_react_agent.py     BaseReActAgent — intermediate base for tool-using agents (ReAct loop)
            │   └── base_add_sources_agent.py BaseAddSourcesAgent — mixin: add_source / merge_sources / _generate_sources
            ├── ambiguity_agent.py      AmbiguityAgent — LLM ambiguity scorer (utility, not fanned-out)
            ├── title_agent.py          TitleAgent — generates a 4-6 word session title (utility, not fanned-out)
            ├── intent_parser_agent.py  IntentParserAgent — parses query into structured intent (utility, not fanned-out)
            ├── orchestrator_agent.py   build_graph() — assembles the full LangGraph StateGraph
            ├── smart_dispatcher_agent.py SmartDispatcherAgent — keyword + semantic routing, no LLM
            ├── calculator_agent.py     CalculatorAgent — safe AST arithmetic evaluator
            ├── rag_agent.py            RAGAgent — ChromaDB retrieval + LLM answer synthesis
            ├── summary_agent.py        SummaryAgent — custom 2-node subgraph (enrich → execute)
            ├── neo4j_agent.py          Neo4jAgent — LLM generates Cypher → executed → LLM synthesises
            ├── postgis_agent.py        PostGISAgent — LLM generates SQL → executed → LLM synthesises
            ├── rdf_agent.py            RDFAgent — LLM generates SPARQL → executed → LLM synthesises
            ├── vector_chroma_agent.py  VectorChromaAgent — ChromaDB similarity search → LLM synthesises
            ├── datagouv_mcp_agent.py   DataGouvMCPAgent — French open-data catalogue (data.gouv.fr)
            ├── geonetwork_mcp_agent.py GeoNetworkMCPAgent — geospatial metadata catalogue
            ├── humanoutput_agent.py    HumanOutputAgent — post-processing: decides needs_map / needs_dataviz
            ├── dataviz_agent.py        DataVizAgent — post-processing: chart / KPI / table structures
            ├── mapviz_agent.py         MapVizAgent — post-processing: GeoJSON extraction
            └── synthesis_agent.py      SynthesisAgent — final node: rewrites raw results into a clean answer
```

---

## Orchestrator graph topology

```
__start__
    │
    ▼
memory_node            ← loads LTM (pgvector) + STM (Redis) into context
    │
    ▼
title_node             ← generates a short session title (first turn only, non-blocking)
    │
    ▼
intent_node            ← IntentParserAgent: extracts action, entity_concept, filters, geo_scope
    │                      into state["context"]["intent"] for downstream agents
    │
    ▼
ambiguity_node         ← LLM scores query ambiguity (0–1)
    │
    ├──[pending]──► hitl_wait_node   ← suspends graph; awaits human clarification
    │                   │
    │            [timeout]──► __end__  (final_answer = timeout message)
    │            [resolved]──► router_node
    │
    └──[clear]──► router_node        ← SmartDispatcher (or LLM DynamicRouter)
                      │
                [Send fan-out — parallel]
                │       │       │
           agent_1  agent_2  agent_N  …  (each is a compiled subgraph)
                │       │       │
                └───────┴───────┘
                        ▼
                   merge_node        ← collects sub_results, builds raw final_answer
                        │
                  humanoutput_node   ← LLM decides needs_map / needs_dataviz
                        │
              ┌─────────┴─────────┐
         dataviz_node?       mapviz_node?   (conditional on output_decision)
              │                   │
              └─────────┬─────────┘
                        ▼
                 synthesis_node     ← rewrites raw results into a clean user-facing Markdown answer
                        │
                    __end__
```

The Mermaid diagram is written to `app/pangiagent/mermaid_graph/orchestrator_graph.mmd` at startup.

---

## Agent catalogue

| Agent | Class | Role | Fanned out? |
|---|---|---|---|
| `ambiguity_agent` | `AmbiguityAgent` | LLM ambiguity scorer; triggers HITL | No (utility node) |
| `title_agent` | `TitleAgent` | Generates 4-6 word session title on first turn | No (utility node) |
| `intent_parser_agent` | `IntentParserAgent` | Parses query into structured intent (action, concept, filters, geo_scope) | No (utility node) |
| `smart_dispatcher_agent` | `SmartDispatcherAgent` | Keyword + semantic router; no LLM | No (utility, inside `router_node`) |
| `rag_agent` | `RAGAgent` | Retrieves docs from ChromaDB → LLM synthesis | ✓ |
| `calculator_agent` | `CalculatorAgent` | Safe AST arithmetic | ✓ |
| `summary_agent` | `SummaryAgent` | Summarisation (custom 2-node subgraph) | ✓ |
| `neo4j_agent` | `Neo4jAgent` | LLM → Cypher → Neo4j execute → LLM synthesis | ✓ |
| `postgis_agent` | `PostGISAgent` | LLM → SQL → PostGIS execute → LLM synthesis | ✓ |
| `rdf_agent` | `RDFAgent` | LLM → SPARQL → GraphDB execute → LLM synthesis | ✓ |
| `vector_chroma_agent` | `VectorChromaAgent` | ChromaDB similarity search → LLM synthesis | ✓ |
| `datagouv_mcp_agent` | `DataGouvMCPAgent` | French open-data (data.gouv.fr MCP) | ✓ |
| `geonetwork_mcp_agent` | `GeoNetworkMCPAgent` | Geospatial metadata (GeoNetwork MCP) | ✓ |
| `humanoutput_agent` | `HumanOutputAgent` | Decides needs_map / needs_dataviz | No (post-processing) |
| `dataviz_agent` | `DataVizAgent` | Builds chart / KPI / table structures | No (post-processing) |
| `mapviz_agent` | `MapVizAgent` | Extracts GeoJSON FeatureCollection | No (post-processing) |
| `synthesis_agent` | `SynthesisAgent` | Rewrites all results into a clean answer | No (final node) |

---

## BaseAgent — the reusable base class

**File:** `app/pangiagent/agents/base_agent.py`

All sub-agents that participate in the orchestrator fan-out **must** inherit from `BaseAgent`.

### Agent inheritance hierarchy

```
object
├── BaseAgent (ABC)              base_agent.py — guardrails, prompt, HITL, intent
│   └── BaseReActAgent           base_react_agent.py — generic ReAct loop (_react_loop, _invoke_tool)
│       ├── DataVizAgent         dataviz_agent.py
│       ├── MapVizAgent          mapviz_agent.py
│       └── DataGouvMCPAgent ───┐ datagouv_mcp_agent.py
└── BaseAddSourcesAgent (mixin) ┘ base_add_sources_agent.py
    add_source / merge_sources /
    _generate_sources
```

**`BaseReActAgent`** — inherit from this (instead of `BaseAgent` directly) when your agent calls external tools in a loop. Provides:
- `_react_loop(messages, llm, tool_map)` — iterates up to `max_iterations`, dispatches tool calls, appends `ToolMessage` results.
- `_invoke_tool(tc, tool_map)` — single-call hook; override for caching, guards, or disambiguation.

**`BaseAddSourcesAgent`** — pure mixin (no `BaseAgent` dependency) for agents that expose structured data sources to the user. Combine via multiple inheritance:

```python
class MyAgent(BaseReActAgent, BaseAddSourcesAgent):
    ...
```

Provides:
- `add_source(output, title, url, kind, fmt)` — appends a deduplicated `AgentSource` to an `AgentOutput`.
- `merge_sources(outputs)` — static; deduplicates and orders sources across multiple outputs (datasets → resources → other).
- `_generate_sources(output, **context)` — no-op hook; override to populate sources after the core logic.

```python
from app.pangiagent.agents.base_agents.base_agent import BaseAgent

class MyAgent(BaseAgent):
    name = "my_agent"
    _DEFAULT_PROMPT = "You are …"

    def get_capabilities(self) -> str:
        return "One-sentence description of what this agent can do."

    async def _run(self, inp: AgentInput) -> AgentOutput:
        # Core logic here
        ...
```

Never override `run()` — put all logic in `_run()`.

### Lifecycle hooks

`BaseAgent.run()` wraps `_run()` with:

1. **Pre-guardrails** — called before `_run()`; can block execution and return an error.
2. **`_run()`** — the agent's core logic (implement this).
3. **Timing** — `output.state["duration_ms"]` is set automatically.
4. **Post-guardrails** — called after `_run()`; can flag or penalise the output.

### Prompt loading

`BaseAgent.get_prompt(default)` resolves the system prompt in two steps:

1. Load `config/prompts/<agent_name>.yaml` (key `prompt:`).
2. Fall back to the hardcoded `_DEFAULT_PROMPT` class attribute.

The YAML file is LRU-cached per process; edit it and restart the container to apply changes without rebuilding.

### Source-augmented prompts

Connector agents that query a specific data source (PostGIS, Neo4j, GraphDB, …) can call `BaseAgent.get_source_augmented_prompt(default)` instead of `get_prompt(default)`.

This method extends the base prompt with an optional `prompt` block defined directly in the source registry entry (`config/source_registry.yml`).  The block is appended under a `## Source context` heading, making it visible to the LLM at query-generation time without being hardcoded into the agent class.

**Resolution order:**

1. Base prompt via `get_prompt()` (YAML file or `_DEFAULT_PROMPT`).
2. `prompt` field from the matching `SourceEntry` in `source_registry.yml` — appended as `\n\n## Source context\n\n<prompt>`.

**Typical use — injecting a database schema:**

```yaml
# config/source_registry.yml
- id: postgis_agent
  connector: postgis_agent
  label: MyPostGIS
  prompt: |
    ## Database schema

    ### my_table — Description (POINT, SRID 4326)
    | column | type | description |
    |--------|------|-------------|
    | id     | serial | primary key |
    | nom    | text   | name        |
    | geom   | point  | WGS-84      |
```

```python
# In the agent __init__:
self._system_prompt = self.get_source_augmented_prompt(_DEFAULT_PROMPT)
```

The resulting system prompt that the LLM receives is:

```
<base prompt from config/prompts/postgis_agent.yaml or _DEFAULT_PROMPT>

## Source context

## Database schema
...
```

This keeps the agent class generic (reusable for any PostGIS database) while the schema travels as configuration data from the registry → `SourceEntry.prompt` → LLM system prompt.

### Subgraph compilation

`BaseAgent.as_subgraph()` wraps the agent in a single-node LangGraph `StateGraph`:

```
__start__ → execute_node → __end__
```

`execute_node` calls `agent.run()` and merges `dataviz`, `geojson`, and other rich-data extras into `sub_results` for the SSE layer.

Override `make_node()` to return a custom node function (used by post-processing agents like `HumanOutputAgent`, `DataVizAgent`, `MapVizAgent`, and `SynthesisAgent` that write directly to `OrchestratorState`).

Override `as_subgraph()` to define a multi-node subgraph (example: `SummaryAgent` uses `enrich_node → execute_node`).

### Agent-level choice requests (`request_choice`)

`BaseAgent` exposes a reusable `request_choice()` coroutine that any agent can call when it needs the user to pick one item from a list **before continuing its work**.

```python
from app.pangiagent.agents.base_agents.base_agent import BaseAgent, ChoiceResult
from app.models import ChoiceItem

class MyAgent(BaseAgent):
    async def _run(self, inp: AgentInput) -> AgentOutput:
        items = [
            ChoiceItem(id="a", title="Option A", description="…"),
            ChoiceItem(id="b", title="Option B", description="…"),
        ]
        result: ChoiceResult = await self.request_choice(
            session_id=inp.session_id,
            original_query=inp.query,
            items=items,
            total=42,          # optional: total results if the list is truncated
        )
        if not result.resolved:
            return AgentOutput(agent_name=self.name, answer="Selection timed out.", confidence=0.0)

        # result.chosen_id  — the id of the item the user selected
        # result.chosen_query — rewritten query targeting that item
        return await self._run(AgentInput(query=result.chosen_query, ...))
```

The method:
1. Registers a `ChoiceRequest` in `HITLManager` (stored in Redis + an `asyncio.Future`).
2. Notifies the SSE layer via a per-session notification queue → emits a `choice_request` SSE event to the frontend.
3. **Suspends** the agent inside its `_run()` call (the graph remains paused at this subgraph node).
4. When the user selects an item (`POST /api/choice/respond`), `HITLManager.resolve_choice()` resolves the future.
5. Returns a `ChoiceResult(resolved=True, chosen_id=…, chosen_query=…)`.

**`ChoiceResult` dataclass:**

| Field | Type | Description |
|---|---|---|
| `resolved` | `bool` | `True` if the user selected an item; `False` on timeout |
| `chosen_id` | `str` | The `id` of the selected `ChoiceItem` |
| `chosen_query` | `str` | Query rewritten to target the chosen item |
| `request_id` | `str` | UUID of the `ChoiceRequest` |

**`ChoiceItem` model:**

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Unique identifier for this option |
| `title` | `str` | Display title |
| `description` | `str` | Short description |
| `url` | `str` | Optional source URL |
| `organization` | `str` | Optional owning organisation |
| `metadata` | `dict` | Agent-specific extra data |

---

## HITL — ambiguity clarification

Triggered automatically by `ambiguity_node` when `AmbiguityAgent` scores the query ≥ `HITL_AMBIGUITY_THRESHOLD` (default `0.8`).

**Flow:**

```
ambiguity_node
  ├─[score < threshold]──► router_node (normal path)
  └─[score ≥ threshold]──► hitl_wait_node
                               │
                          pauses on asyncio.Future
                               │
                    POST /api/hitl/respond
                               │
                        [resolved]──► router_node (with clarified query)
                        [timeout] ──► __end__
```

**SSE events:**

| Event | Payload |
|---|---|
| `hitl_request` | `request_id`, `questions[]`, `original_query` |
| `hitl_resolved` | `clarified_query` |
| `hitl_timeout` | `message` |

**API:**

```http
POST /api/hitl/respond
Content-Type: application/json

{ "request_id": "<uuid>", "clarified_query": "The user's clarified question" }
```

---

## Choice flow — agent-level disambiguation

Unlike HITL (which suspends the entire orchestrator graph at the top level), the choice flow suspends an individual **sub-agent** inside its fan-out subgraph — other parallel agents continue running.

### How it works end-to-end

```
datagouv_mcp_agent._run()
  1. Searches data.gouv.fr → finds multiple datasets
  2. Calls self.request_choice(items=[...])
       │
       ├─ HITLManager.create_choice_request()
       │      ├─ Stores ChoiceRequest in Redis
       │      ├─ Creates asyncio.Future
       │      └─ Pushes ("choice_request", req) to the session's notification queue
       │
       ├─ sse_stream notif_task picks up the event → emits `choice_request` SSE
       │
       └─ await future  ← agent suspended
  
  Frontend shows DatasetChoicePanel; user clicks "Sélectionner"
  
  POST /api/choice/respond { request_id, chosen_id, chosen_query }
       │
       └─ HITLManager.resolve_choice() → future.set_result(ChoiceResponse)
  
  3. request_choice() returns ChoiceResult(resolved=True, chosen_id, chosen_query)
  4. Agent calls self._run(AgentInput(query=chosen_query)) — fetches the right dataset
  5. Returns final AgentOutput with dataviz + geojson + download links
```

### Reusing `request_choice` in another agent

Any `BaseAgent` subclass can call `self.request_choice()`. Build `ChoiceItem` objects from whatever candidates your agent produces, then branch on `result.resolved`:

```python
result = await self.request_choice(
    session_id=inp.session_id,
    original_query=inp.query,
    items=[ChoiceItem(id=row["id"], title=row["name"], ...) for row in candidates],
)
if not result.resolved:
    return AgentOutput(agent_name=self.name, answer="Timeout.", confidence=0.0)
# Continue with result.chosen_id or result.chosen_query
```

No orchestrator changes needed — the mechanism is entirely self-contained in `BaseAgent` and `HITLManager`.

---

## Guardrails

Defined in `app/pangiagent/guardrails.py`.

| Guardrail | Stage | Behaviour |
|---|---|---|
| `check_toxic_input` | Pre | Blocks queries containing toxic keywords |
| `check_ambiguous_intent` | Pre | Blocks queries shorter than 5 characters |
| `check_output_length` | Post | Flags answers exceeding 10 000 characters (reduces confidence by 0.2) |

Guardrails are wired per agent in `app/pangiagent/graph.py`:

```python
AGENTS = {
    "neo4j_agent": Neo4jAgent(
        pre_guardrails=[check_toxic_input, check_ambiguous_intent],
        post_guardrails=[check_output_length],
    ),
    ...
}
```

---

## Memory

### Short-term memory

**Backend:** Redis · **TTL:** `SESSION_TTL_SECONDS` (default 3 600 s)  
**Key pattern:** `session:{session_id}:stm`

Stores the last query and answer per session. Injected into agent context at the start of each request via `memory_node`.

### Long-term memory

**Backend:** PostgreSQL + pgvector · **Table:** `long_term_memory`

Stores factual information extracted from previous conversations as vector embeddings. Searched via cosine similarity at the start of each request (top-5 facts). Populated by the agents themselves when they identify reusable facts.

---

## Audit trail

**File:** `app/pangiagent/audit.py`  
**Table:** `audit_logs`

Every significant event (`request_start`, `memory_access`, `hitl_*`, `routing`, `request_end`, `stream_error`) is written with:

- `session_id` and `event_type`
- `payload` (JSONB)
- `prev_hash` + `hash` — SHA-256 chain over `(session_id, event_type, payload, prev_hash)` for tamper-evidence

---

## Routing

Two strategies, toggled by `SMART_DISPATCHER_ENABLED`:

### SmartDispatcherAgent (default, no LLM)

Scores every registered source by combining:

1. **Keyword scoring** — +2 per topic / entity_type from `source_registry.yml` found in the query.
2. **Semantic scoring** — cosine similarity from ChromaDB source-registry collection (max +1).

Agents with composite score ≥ `DISPATCH_THRESHOLD` (2.0) are selected. Falls back to the highest scorer if nothing clears the threshold.

### DynamicRouter (LLM-based fallback)

When `SMART_DISPATCHER_ENABLED=false`, calls an LLM with a structured-output prompt to produce an `ExecutionPlan` with parallel groups.

### Source registry

`config/source_registry.yml` — add an entry here to register a new connector.

| Field | Description |
|---|---|
| `id` / `connector` | Agent key matching the `AGENTS` registry key |
| `description` | Embeddable text for ChromaDB |
| `topics` | Keywords for deterministic scoring |
| `entity_types` | Entity types stored in this source |
| `capabilities` | Standardised tags (e.g. `spatial_query`, `open_data`) |
| `geo_scope` | Geographic coverage (`null` = global) |
| `example_questions` | Representative questions |

---

## Post-processing pipeline

After `merge_node`, three sequential post-processing agents run:

```
merge_node → humanoutput_node → [dataviz_node?] → [mapviz_node?] → synthesis_node
```

### HumanOutputAgent

Inspects `sub_results` and the user query to decide which visualisation components are needed. Sets `output_decision: {needs_map: bool, needs_dataviz: bool}`.

Decision strategy:
1. Fast-path — empty results → skip both.
2. Heuristics — geo keywords → `needs_map`; dataviz keywords → `needs_dataviz`.
3. LLM classification — when signals are ambiguous.
4. Fallback — `{needs_map: true, needs_dataviz: true}` on error.

### DataVizAgent

Reads `sub_results` and builds `dataviz: {charts, kpis, tables}` for the frontend.

| Type | Frontend component |
|---|---|
| `charts` | `ChartViewer` (D3.js bar / line / pie / scatter / histogram) |
| `kpis` | `KpiCards` (value, unit, trend, threshold) |
| `tables` | `DataVizViewer` (scrollable table) |

### MapVizAgent

Extracts `geojson: FeatureCollection` from `sub_results`. Rendered as a Leaflet interactive map in the frontend.

---

## Synthesis agent

**File:** `app/pangiagent/agents/synthesis_agent.py`  
**Prompt:** `config/prompts/synthesis_agent.yaml`

The last node in the graph. Rewrites the raw `[agent_name]: …` concatenation from `merge_node` into a concise, human-friendly Markdown response.

Key rules (enforced in the prompt):

- Never reproduce the raw `[agent_name]: …` format.
- Never list column names or individual row values — the UI renders these separately.
- Refer to map / table concisely ("les données sont affichées dans le tableau ci-dessus").
- Preserve any Markdown links `[text](url)` that appear in the agent results — copy them verbatim.
- If no links are present in the agent results, do **not** invent download links.
- Answer in the same language as the user's question.

---

## DB client library (`libs/client/`)

The `libs/client/` package provides thin, async DB clients used by the connector agents. Each module is self-contained with lazy imports and a module-level singleton (pool / driver / connection) to avoid reconnecting on every request.

| Module | Data store | Key functions |
|---|---|---|
| `chroma_client.py` | ChromaDB | `similarity_search(query, n_results)`, `add_documents(texts, metadatas)` |
| `graphdb_client.py` | GraphDB (Ontotext) | `run_sparql_select(sparql)`, `run_sparql_construct(sparql)`, `ensure_repository()` |
| `neo4j_client.py` | Neo4j | `run_readonly_query(cypher, params)`, `run_query(cypher, params)` |
| `postgis_client.py` | PostGIS (asyncpg) | `run_spatial_query(sql, params)`, `run_write_query(sql, params)` |
| `redis_client.py` | Redis | `load_session(session_id)`, `save_session(session_id, messages)` |

All read paths are protected: `run_spatial_query` runs inside a `readonly=True` asyncpg transaction; `run_readonly_query` uses a Neo4j read transaction. Writes are only available via explicit write functions.

**DSN note:** `postgis_client` automatically strips the SQLAlchemy `+asyncpg` driver prefix from `POSTGIS_DSN` before passing it to asyncpg's `create_pool`.

---

## data.gouv.fr MCP agent

**File:** `app/pangiagent/agents/datagouv_mcp_agent.py`  
**Prompt:** `config/prompts/datagouv_mcp_agent.yaml`

Queries the French government open-data catalogue via the data.gouv.fr MCP server.

### Capabilities

- `search_datasets` with synonym expansion (webcam → caméra, vidéosurveillance, …)
- `get_resource_info` → confirmed download URLs
- `fetch_resource_file` (local tool) — downloads CSV / JSON / GeoJSON and returns parsed rows
- Auto-fetches GeoJSON resources not explicitly fetched by the LLM

### Dataset disambiguation via `request_choice`

When `search_datasets` returns ≥ 2 results with different titles and the user has not quoted an exact title, the agent:

1. Calls `self.request_choice()` with the candidate list.
2. **Suspends** inside its `_run()` call (other parallel agents continue).
3. The frontend shows an interactive `DatasetChoicePanel`.
4. User clicks "Sélectionner" → `POST /api/choice/respond`.
5. Agent **resumes** and calls `self._run()` again with `chosen_query` targeting the selected dataset.

This replaces the old `pending_dataset_choice` pattern, which required a full round-trip (the graph terminated and the user had to manually retype the dataset title).

### Download links

After fetching files, the agent appends a `**Téléchargement :**` Markdown block with `[FORMAT](url)` links directly to `result_text`. The synthesis agent preserves these links verbatim (rule 5 in the synthesis prompt).

---

## SSE event types

| Event | Description |
|---|---|
| `session_title` | Short title generated by TitleAgent for the current conversation |
| `session` | Session ID assigned for this conversation |
| `status` | "Processing your request…" |
| `memory_access` | LTM facts + STM data loaded |
| `hitl_request` | Ambiguous query — show HITL clarification UI |
| `hitl_resolved` | Human responded — execution resuming |
| `hitl_timeout` | No response within timeout |
| `routing_plan` | Agents selected + reasoning |
| `agent_start` | A sub-agent subgraph began |
| `agent_end` | A sub-agent finished (answer preview, confidence, duration_ms) |
| `dataviz` | Chart / KPI / table payload |
| `geojson` | GeoJSON FeatureCollection |
| `output_decision` | `{needs_map, needs_dataviz}` from HumanOutputAgent |
| `choice_request` | Agent needs user to pick an item (dataset, result, …) |
| `final_answer` | Merged + synthesised final answer |
| `done` | Stream complete |
| `error` | Unhandled error |

### `choice_request` event payload

```json
{
  "type": "choice_request",
  "request_id": "uuid",
  "agent": "datagouv_mcp_agent",
  "items": [
    {
      "id": "abc123",
      "title": "Webcams — Ville d'Orléans",
      "description": "Positions des webcams installées sur le domaine public",
      "url": "https://www.data.gouv.fr/fr/datasets/abc123/",
      "organization": "Mairie d'Orléans"
    }
  ],
  "total": 14,
  "original_query": "affiche les webcams d'Orléans"
}
```

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/sources` | List available agent sources |
| `GET` | `/api/suggestions` | Example prompts for the UI |
| `POST` | `/api/chat` | Start agent execution; returns SSE stream |
| `POST` | `/api/hitl/respond` | Submit human clarification for a pending HITL request |
| `POST` | `/api/choice/respond` | Submit user's choice for a pending agent-level choice request |

### `POST /api/chat`

```json
{
  "message": "affiche les webcams d'Orléans",
  "session_id": "optional-existing-session-id",
  "selected_sources": ["datagouv_mcp_agent", "neo4j_agent"]
}
```

`selected_sources` restricts routing to the listed agents. Omit or pass `[]` for no restriction.

### `POST /api/hitl/respond`

```json
{ "request_id": "uuid", "clarified_query": "The user's clarified question" }
```

### `POST /api/choice/respond`

```json
{
  "request_id": "uuid",
  "chosen_id": "abc123",
  "chosen_query": "Je veux travailler avec le dataset : \"Webcams — Ville d'Orléans\" (ID: abc123)"
}
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | Required for LLM calls |
| `MODEL_PROVIDER` | `openai` | Global LLM provider (`openai`, `anthropic`, `ollama`) |
| `MODEL_NAME` | `gpt-4o-mini` | Global LLM model name |
| `OPENAI_TEMPERATURE` | `0.0` | LLM temperature |
| `ANTHROPIC_API_KEY` | — | Required if using Anthropic models |
| `MISTRAL_API_KEY` | — | Required if using Mistral models |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama base URL (local models) |
| `POSTGRES_DSN` | `postgresql+asyncpg://pangia2:pangia2-password@postgres2:5432/pangia2` | Audit + LTM database |
| `REDIS_URL` | `redis://redis:6379` | Redis (STM + HITL state) |
| `SESSION_TTL_SECONDS` | `3600` | Short-term memory TTL |
| `HITL_TIMEOUT_SECONDS` | `120` | Seconds before HITL or choice request times out |
| `HITL_AMBIGUITY_THRESHOLD` | `0.8` | Ambiguity score threshold that triggers HITL |
| `NEO4J_URI` | `bolt://neo4j:7687` | Neo4j Bolt URI |
| `NEO4J_USERNAME` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | — | Neo4j password |
| `CHROMA_HOST` | `chroma` | ChromaDB hostname |
| `CHROMA_PORT` | `8000` | ChromaDB port |
| `POSTGIS_DSN` | `postgresql+asyncpg://pangia:pangia-password@postgres:5432/pangia` | PostGIS database |
| `GRAPHDB_URL` | `http://graphdb:7200` | Ontotext GraphDB URL |
| `GRAPHDB_REPOSITORY` | `pangia` | GraphDB repository name |
| `DATA_GOUV_MCP_URL` | `https://mcp.data.gouv.fr/mcp` | data.gouv.fr MCP endpoint |
| `SMART_DISPATCHER_ENABLED` | `true` | `true` = SmartDispatcher (no LLM); `false` = DynamicRouter (LLM) |
| `AGENT_MAX_ITERATIONS` | `10` | Global ReAct loop iteration limit |
| `<AGENT>_MAX_ITERATIONS` | `0` | Per-agent override (0 = use global) |
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://localhost:6006/v1/traces` | Arize Phoenix OTLP endpoint |
| `PHOENIX_PROJECT_NAME` | `pangia` | Phoenix project name |

**Per-agent model overrides** — any agent name in upper snake-case:

```env
NEO4J_AGENT_MODEL_PROVIDER=openai
NEO4J_AGENT_MODEL_NAME=gpt-4o
DATAGOUV_MCP_AGENT_MODEL_PROVIDER=anthropic
DATAGOUV_MCP_AGENT_MODEL_NAME=claude-3-5-sonnet-latest
```

---

## Configurable system prompts

Each agent loads its system prompt from `config/prompts/<agent_name>.yaml` (key: `prompt:`). If the file is absent or the key is missing, the agent falls back to its hardcoded `_DEFAULT_PROMPT` class attribute.

**Edit without rebuilding:** mount `config/` as a volume (already configured in `docker-compose.yml`) and restart the container.

Example:

```yaml
# config/prompts/neo4j_agent.yaml
prompt: |
  You are an expert Cypher query generator for Neo4j.
  …
```

---

## Adding a new agent

1. **Create** `app/pangiagent/agents/<name>_agent.py`.
2. **Inherit** from `BaseAgent`, implement `get_capabilities()` and `_run()`.
3. **Add a prompt file** `config/prompts/<name>_agent.yaml`.
4. **Register** in `app/pangiagent/graph.py` under `AGENTS`.
5. **Add a source entry** in `config/source_registry.yml` with appropriate `capabilities`, `topics`, and `example_questions`.
6. **Update** `README.md` (this file) to document the new agent.

For post-processing agents (not fanned out), override `make_node()` instead and register under `OUTPUT_AGENTS`.

---

## Running locally (without Docker)

```bash
cd backend-ai

# Requires Python 3.12+
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Copy and edit env
cp ../.env.example .env
# Set at minimum: OPENAI_API_KEY, POSTGRES_DSN, REDIS_URL

uvicorn app.main:app --reload --port 8086
```

Backend V2 is available at **http://localhost:8086**.
