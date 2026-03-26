# Pangia – GeoIA Agent 🌍

A minimal AI agent chat application built with:

| Layer | Technology |
|---|---|
| **Frontend** | Vue 3 + ai-elements-vue, Vite, TypeScript |
| **Backend** | FastAPI, Server-Sent Events (SSE) |
| **Agent** | LangChain + LangGraph (ReAct pattern) |
| **Knowledge Graph** | Neo4j |
| **Sessions** | Redis |
| **Infrastructure** | Docker Compose |

---

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY
```

### 2. Start all services

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Neo4j Browser | http://localhost:7474 |

### 3. Chat

Open http://localhost:3000 in your browser and start chatting with the GeoIA agent.

---

## Architecture

```
Browser (Vue 3)
    │  POST /api/chat  (JSON)
    │  ← text/event-stream (SSE tokens)
    ▼
FastAPI (backend)
    │
    ├─ LangGraph agent graph
    │     ├─ LLM node  (OpenAI, streaming)
    │     └─ Tools node
    │           └─ Neo4j knowledge-graph tools
    │
    ├─ Redis  (session / conversation history)
    └─ Neo4j  (knowledge graph)
```

### Agent flow (LangGraph)

```
[entry] → agent (LLM) → should_continue?
                              │ tool_calls? → tools (Neo4j) → agent
                              │ done?       → END
```

The agent streams individual LLM tokens back to the browser via SSE so responses
appear word-by-word. Tool calls (Neo4j queries) are surfaced as status badges in
the chat UI.

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
│       ├── main.py          # FastAPI app factory
│       ├── config.py        # Pydantic settings
│       ├── api/
│       │   └── routes.py    # /api/chat SSE endpoint
│       ├── agent/
│       │   ├── graph.py     # LangGraph agent
│       │   ├── tools.py     # Neo4j tools
│       │   └── state.py     # AgentState TypedDict
│       └── db/
│           ├── neo4j_client.py
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
            └── ChatInterface.vue
```

## Development (without Docker)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # set OPENAI_API_KEY, point NEO4J/REDIS to local instances
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install --legacy-peer-deps
npm run dev
# → http://localhost:5173 (proxies /api to localhost:8000)
```
