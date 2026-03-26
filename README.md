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
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py              # FastAPI app factory + lifespan
│       ├── config.py            # Pydantic settings
│       ├── api/
│       │   └── routes.py        # POST /api/chat  SSE endpoint
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
│           └── redis_client.py
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── main.ts
        ├── App.vue
        └── components/
            └── ChatInterface.vue   # Routing banner + per-agent panels + synthesis stream
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
