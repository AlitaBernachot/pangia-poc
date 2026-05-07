<!--
SPDX-FileCopyrightText: 2026 AlitaBernachot

SPDX-License-Identifier: MIT
-->

# Backend — PangIA Seeder

> **Port:** `8084`  
> **Stack:** FastAPI · asyncpg · Neo4j · ChromaDB · GraphDB  
> **Purpose:** Database seeding for dev / demo stacks.  
> The AI multi-agent backend lives in [`backend-ai/`](../backend-ai/README.md) (port 8086).

---

## Table of Contents

- [API endpoints](#api-endpoints)
- [Development (without Docker)](#development-without-docker)
- [Seed themes](#seed-themes)
  - [PostGIS schema isolation](#postgis-schema-isolation)
  - [Switching the theme](#switching-the-theme)
  - [Adding a new theme](#adding-a-new-theme)

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Liveness probe |
| `GET` | `/api/suggestions` | Example queries for the active seed theme |

---

## Development (without Docker)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env  # set connection strings
uvicorn app.main:app --reload
```

---

## Seed themes

The application populates the data stores at startup with a **seed theme** (`SEED_THEME`, default: `pandemic`). Seeding is controlled by `SEED_DB` (default: `true`).

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
| `suggestions` | Example prompts for the UI |

3. Set `SEED_THEME=<my_theme>` and start the stack.
