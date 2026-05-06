<!--
SPDX-FileCopyrightText: 2026 AlitaBernachot

SPDX-License-Identifier: MIT
-->

![PangIA Banner](docs/pangIA_logo.png)

# PangIA — Multi-agent geospatial assistant 🌍

A full-stack AI chat application built around a **multi-agent architecture** for geospatial open data.

| Layer | Technology |
|---|---|
| **Frontend** | React 19 + Tailwind CSS v4, Vite, TypeScript (`frontend-client/`) |
| **Backend** | FastAPI · asyncio · LangChain · LangGraph (`backend-ai/`, port 8086) |
| **Orchestration** | LangGraph — Intent Parser → Smart Dispatcher → parallel sub-agents |
| **Knowledge Graph** | Neo4j (Cypher) |
| **RDF / Linked Data** | Ontotext GraphDB (SPARQL) |
| **Vector Search** | ChromaDB (embeddings) |
| **Spatial SQL** | PostgreSQL + PostGIS |
| **Long-term Memory** | PostgreSQL + pgvector |
| **Sessions** | Redis |
| **Local LLM** | Ollama (Gemma 4, Llama 3, …) |
| **Observability** | Arize Phoenix (traces, spans, LLM call inspection) |
| **Infrastructure** | Docker Compose |

---

## Table of Contents

- [Quick Start](#quick-start)
- [Services](#services)
- [Project structure](#project-structure)
- [Observability](#observability)
- [Development (without Docker)](#development-without-docker)
- [Documentation](#documentation)

---

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — set at minimum: OPENAI_API_KEY
```

### 2. Start all services

```bash
docker compose up --build
```

> **PostGIS demo data** — if it's the first start and the PostGIS volume does not yet exist, the demo tables (`lieux_interet`, `communes`, `zones_risque`) are created automatically from `backend-ai/init_postgis.sql`. If the volume already exists from a previous run without demo data, recreate it:
> ```bash
> docker compose down -v && docker compose up --build
> ```

---

## Services

| Service | URL | Description |
|---|---|---|
| Frontend | http://localhost:3000 | Chat UI |
| Backend | http://localhost:8086 | FastAPI + LangGraph (active backend) |
| Neo4j Browser | http://localhost:7474 | Knowledge graph |
| GraphDB Workbench | http://localhost:7200 | RDF triplestore |
| ChromaDB | http://localhost:8001 | Vector store |
| PostGIS | `localhost:5434` | Spatial database |
| Redis | `localhost:6379` | Sessions + HITL state |
| Phoenix UI | http://localhost:6006 | Agent observability |

---

## Project structure

```
pangia-poc/
├── docker-compose.yml
├── .env.example
├── docs/
├── backend-ai/             ← Active backend (port 8086)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── init.sql            PostgreSQL DDL (audit_logs, long_term_memory)
│   ├── init_postgis.sql    PostGIS demo data
│   ├── config/
│   │   ├── source_registry.yml   Connector manifest + routing metadata
│   │   └── prompts/              Per-agent YAML system prompts
│   ├── libs/
│   │   └── client/         DB clients (chroma, graphdb, neo4j, postgis, redis)
│   └── app/
│       ├── config.py       Pydantic settings
│       ├── models.py       Shared Pydantic models
│       └── pangiagent/     Multi-agent system
│           ├── agents/     All agents (base classes + connectors + post-processing)
│           ├── graph.py    LangGraph orchestrator
│           ├── router.py   SmartDispatcherAgent / DynamicRouter
│           ├── memory.py   Short-term (Redis) + long-term (pgvector) memory
│           ├── hitl.py     Human-in-the-loop manager
│           └── audit.py    SHA-256 hash-chain audit log
├── backend/                ← Database seeder (port 8084) — seeds Neo4j, PostGIS, GraphDB, ChromaDB
├── frontend-client/        ← React 19 + Tailwind CSS v4 chat UI
│   └── src/
│       ├── hooks/
│       │   └── usePangiaChat.ts   SSE streaming hook
│       └── components/
│           ├── chat/              Chat panel, agent activity, HITL modal
│           ├── MapViewer.tsx      Leaflet interactive map
│           └── DataViz/           Charts (D3.js), KPI cards, tables
└── LICENSES/
```

---

## Observability

All LangChain/LangGraph spans are automatically captured via [OpenInference](https://github.com/Arize-ai/openinference) and sent to the bundled [Arize Phoenix](https://github.com/Arize-ai/phoenix) collector.

Open **http://localhost:6006** to explore traces, spans, LLM call details, and token counts.

| Variable | Default | Description |
|---|---|---|
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://phoenix:6006/v1/traces` | OTLP HTTP endpoint |
| `PHOENIX_PROJECT_NAME` | `pangia` | Project name in the Phoenix UI |

---

## Development (without Docker)

**Backend:**
```bash
cd backend-ai
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # set OPENAI_API_KEY and connection strings
uvicorn app.main:app --reload --port 8086
```

**Frontend:**
```bash
cd frontend-client
npm install
npm run dev
# → http://localhost:5173 (proxies /api to localhost:8086)
```

---

## Documentation

| Document | Description |
|---|---|
| [backend-ai/README.md](backend-ai/README.md) | Full backend documentation — agents, routing, HITL, memory, API, env vars |
| [backend/README.md](backend/README.md) | Legacy backend V1 documentation |
| [docs/ollama-gemma4-setup.md](docs/ollama-gemma4-setup.md) | Running local models via Ollama |
