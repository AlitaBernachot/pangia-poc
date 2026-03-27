![PangIA Banner](docs/banner.png)

# PangIA – GeoIA Agent 🌍

A minimal AI agent chat application with a **multi-agent architecture**:

| Layer | Technology |
|---|---|
| **Frontend** | Vue 3 + ai-elements-vue, Vite, TypeScript |
| **Backend** | FastAPI, Server-Sent Events (SSE) |
| **Orchestration** | LangChain + LangGraph (master agent + 4 sub-agents) |
| **Knowledge Graph** | Neo4j (Cypher) |
| **RDF / Linked Data** | Ontotext GraphDB (SPARQL) |
| **Vector Search** | ChromaDB (embeddings) |
| **Spatial SQL** | PostgreSQL + PostGIS |
| **Sessions** | Redis |
| **Observability** | Arize Phoenix (traces, spans, LLM call inspection) |
| **Infrastructure** | Docker Compose |

---

## Multi-agent architecture

```
User query
    │
    ▼
┌───────────────────────────────────────────────────────┐
│                   Master Agent                        │
│                                                       │
│  ┌─────────┐   Send fan-out   ┌──────────────────┐    │
│  │ router  │─────────────────►│ neo4j_agent      │─┐  │
│  │  (LLM + │                  │ (Cypher / Neo4j) │ │  │
│  │  struct)│─────────────────►│ rdf_agent        │─┤  │
│  └─────────┘                  │ (SPARQL/GraphDB) │ │  │
│                               │ vector_agent     │─┤  │
│                               │ (Chroma embeds)  │ │  │
│                               │ postgis_agent    │─┘  │
│                               │ (PostGIS SQL)    │    │
│                               └──────────────────┘    │
│                                       │               │
│                               ┌───────▼──────┐        │
│                               │  merge node  │        │
│                               │ (synthesise) │        │
│                               └───────┬──────┘        │
└───────────────────────────────────────┼───────────────┘
                                        ▼
                                   Streamed answer (SSE)
```

The **router** uses an LLM with structured output to select the minimum relevant
set of sub-agents.  Each sub-agent runs its own ReAct loop (LLM + tools) and
writes its result into a shared `sub_results` dict.  The **merge** node then
synthesises all results into a final streamed answer.

### SSE event types

| Event type | Meaning |
|---|---|
| `session` | Session ID assigned for this conversation |
| `routing` | Which sub-agents were selected (list of names) |
| `agent_token` | Intermediate reasoning token from a sub-agent |
| `token` | Final synthesis token (streamed to user) |
| `tool_start` | A sub-agent started a tool call |
| `tool_end` | A sub-agent tool call completed |
| `error` | An error occurred |
| `done` | Stream complete |

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
| Backend API | http://localhost:8000 | FastAPI + LangGraph |
| Neo4j Browser | http://localhost:7474 | Knowledge graph |
| GraphDB Workbench | http://localhost:7200 | RDF triplestore |
| ChromaDB | http://localhost:8001 | Vector store |
| PostGIS | localhost:5432 | Spatial database |
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
│   └── banner.png
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py              # FastAPI app factory + lifespan
│       ├── config.py            # Pydantic settings
│       ├── api/
│       │   └── routes.py        # POST /api/chat (SSE), GET /api/suggestions
│       ├── agent/
│       │   ├── state.py         # AgentState (messages, agents_to_call, sub_results)
│       │   ├── master.py        # Master orchestrator (router → fan-out → merge)
│       │   ├── neo4j_agent.py   # Knowledge Graph sub-agent (Cypher)
│       │   ├── rdf_agent.py     # RDF sub-agent (SPARQL / GraphDB)
│       │   ├── vector_agent.py  # Vector sub-agent (ChromaDB)
│       │   └── postgis_agent.py # Spatial SQL sub-agent (PostGIS)
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
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── main.ts              # PrimeVue setup + theme (Yellow/Aura preset)
        ├── types.ts             # Message, AgentActivity types + helpers
        ├── assets/
        │   └── main.css
        └── components/
            ├── ChatView.vue             # Root chat controller (SSE, state)
            └── ChatView/
                ├── ChatHeader.vue       # Session ID display
                ├── ChatMessages.vue     # Message list + suggestions
                ├── ChatMessage.vue      # Router: user vs agent
                ├── ChatUserMessage.vue  # User bubble
                ├── ChatAgentMessage.vue # Agent bubble (activity panels + answer)
                └── ChatPrompt.vue       # Textarea + send button
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
cd frontend
npm install --legacy-peer-deps
npm run dev
# → http://localhost:5173 (proxies /api to localhost:8000)
```

---

## Seed themes

The application is populated with sample data at startup via a **seed theme**.
The active theme is selected by the `SEED_THEME` environment variable (default: `dinosaurs`).
Seeding is controlled by `SEED_DB` (default: `true`); set it to `false` in production.

Each theme provides data for all four datastores (Neo4j, PostGIS, GraphDB, ChromaDB)
as well as the schema prompts, agent guidelines, and UI suggestions used by the agents.

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
   | `postgis_statements` | DDL + DML SQL statements for tables and rows |
   | `graphdb_named_graph` + `graphdb_turtle` | Named graph URI and Turtle RDF content |
   | `chroma_documents` | List of `{"text": str, "metadata": dict}` docs to embed |
   | `neo4j_schema_prompt` | Graph schema description injected into the Neo4j agent |
   | `postgis_schema_prompt` | Table/column description injected into the PostGIS agent |
   | `rdf_schema_prompt` | Ontology description injected into the RDF agent |
   | `neo4j_guidelines` | Theme-specific query hints for the Neo4j agent |
   | `postgis_guidelines` | Theme-specific query hints for the PostGIS agent |
   | `rdf_guidelines` | Theme-specific query hints for the RDF agent |
   | `vector_guidelines` | Theme-specific hints for the Vector agent |
   | `suggestions` | Example prompts shown in the chat UI |

3. Set `SEED_THEME=<my_theme>` and start the stack.

---

## Adding a new sub-agent

Sub-agents live in `backend/app/agent/`.  To add one:

1. **Create `backend/app/agent/<name>_agent.py`** with an `async def run(state: AgentState) -> dict` function.
   Follow the existing agents as a template (ReAct loop: LLM + tools, write result to `sub_results`).

2. **Connect it to the master orchestrator** in `backend/app/agent/master.py`:
   - Declare it as a valid literal in `RoutingDecision.agents`.
   - Add an import and a `Send` mapping in `fan_out_node`.
   - Register it in `AGENT_LABELS`.
   - Update `ROUTER_SYSTEM` to include its description and routing rules.

3. **Write a clear `_BASE_SYSTEM_PROMPT`** for the agent. Keep generic query mechanics
   (tool selection, output format, error handling) in the base prompt in the agent file.
   Move anything **specific to the active dataset** into the theme's corresponding
   `<store>_guidelines` field so any future theme can override it without touching agent code.

4. **Define the database schema** in the seed theme's `<store>_schema_prompt` field
   (node labels, relationship types, table columns, ontology prefixes, etc.).
   The more precise the schema description, the better the LLM will generate correct queries.

5. **Expose a `GET /api/suggestions`** update is automatic — suggestions are already
   served from the active theme's `suggestions` list.

