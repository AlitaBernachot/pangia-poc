# `agent/source` — Source Registry

This package centralises the declaration of all **data-source connectors** that Pangia can route queries to.

## Files

| File | Role |
|---|---|
| [`backend/config/source_registry.yml`](../../../../config/source_registry.yml) | **Canonical data file** — add / edit connectors here |
| `source_registry.py` | Python loader — parses the YAML, exposes `SOURCE_REGISTRY` and helpers |
| `__init__.py` | Package marker |

---

## How it works

At startup `source_registry.py` reads `backend/config/source_registry.yml` and builds a list of [`SourceEntry`](source_registry.py) Pydantic models.  These entries are then:

1. **Embedded into ChromaDB** (`pangia_source_registry` collection) via `bootstrap_registry_embeddings()` so the Smart Dispatcher can do semantic similarity search on them.
2. **Iterated by the Orchestrator** to dynamically register MCP-backed connectors (entries where `mcp_url` is set).

---

## Adding a new connector

Edit `source_registry.yml` and append an entry following this template:

```yaml
- id: my-source           # unique identifier
  connector: my_source    # must match the agent key in _AGENT_NODES (orchestrator.py)
  description: >          # overrides agent_descriptions.yml description in the LLM router prompt
    Free-text description of what this source contains.
    Used for ChromaDB embedding and Smart Dispatcher scoring.
  label: "My Source"      # optional — overrides agent_descriptions.yml UI label
  topics:
    - keyword1
    - keyword2
  entity_types:
    - type1
  capabilities:
    - capability_tag      # see capability vocabulary below
  geo_scope: null         # "france" | "global" | null
  mcp_url: null           # set to an MCP endpoint URL for MCP-backed connectors
  example_questions:
    - "Example question this source can answer?"
```

> **Label & description priority** — `label` and `description` set in `source_registry.yml` take precedence over the defaults defined in `backend/config/agent_descriptions.yml`. Agents not listed in `agent_descriptions.yml` (e.g. dynamically registered MCP connectors) automatically use the registry values.

Then restart the application — the ChromaDB bootstrap is idempotent and will index the new entry automatically.

---

## Capability vocabulary

Used by the Smart Dispatcher for hard-rule scoring (keyword matching before embedding similarity).

| Category | Tags |
|---|---|
| Spatial | `spatial_query`, `buffer`, `intersection`, `area`, `distance`, `coordinates`, `geometry` |
| Graph | `relationship`, `graph_traversal`, `entity_search`, `co-occurrence`, `hierarchy` |
| Semantic | `semantic_search`, `similarity`, `document_retrieval`, `embedding` |
| RDF / Linked data | `ontology`, `linked_data`, `sparql`, `semantic_reasoning`, `geosparql` |
| Open data | `open_data`, `official_statistics`, `government_data`, `french_datasets` |
| Geo analysis | `geocoding`, `routing`, `isochrone`, `elevation`, `viewshed`, `hotspot`, `temporal_analysis`, `proximity` |

---

## MCP-backed connectors

Entries with a non-null `mcp_url` are dynamically registered as routable agents by the Orchestrator.  The `connector` field must be a key recognised by `_AGENT_NODES` (e.g. `geonetworkmcp`).

To add a second GeoNetwork instance, give it a **distinct `connector` key** and a different `mcp_url`:

```yaml
- id: geonetwork-prod
  connector: geonetwork_prod
  mcp_url: https://geonetwork-prod.example.com/srv/api/mcp
  ...

- id: geonetwork-staging
  connector: geonetwork_staging
  mcp_url: https://geonetwork-staging.example.com/srv/api/mcp
  ...
```

---

## Python API

```python
from app.agent.source.source_registry import (
    SOURCE_REGISTRY,       # list[SourceEntry]
    get_registry,          # () -> list[SourceEntry]
    get_entry,             # (source_id: str) -> SourceEntry | None
    get_entry_by_connector,# (connector_key: str) -> SourceEntry | None
    semantic_search_sources,       # async (query, n) -> dict[id, score]
    bootstrap_registry_embeddings, # async () -> None  — call once at startup
)
```

## Currently registered sources

| id | connector | geo_scope | MCP |
|---|---|---|---|
| `neo4j` | `neo4j` | — | no |
| `rdf` | `rdf` | — | no |
| `vector` | `vector` | — | no |
| `postgis` | `postgis` | — | no |
| `data_gouv` | `data_gouv` | france | yes |
| `my-geonetwork` | `geonetworkmcp` | — | yes |
| `geo` | `geo` | — | no |
