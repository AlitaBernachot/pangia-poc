# PangIA – Agent Workflow Graph

> This file is **auto-generated** at build time by
> [`generate_graph.py`](./generate_graph.py).  
> Re-generate locally with:
> ```
> python backend/app/agent/generate_graph.py
> ```

The diagram below maps the full LangGraph workflow executed by the PangIA
multi-agent backend for every user query.

```mermaid
graph TD
    __start__(["<b>Start</b>"])
    router["🔀 <b>Router</b><br/>LLM routing decision"]
    post_process_router["⚙️ <b>post_process_router</b><br/>barrier — waits for all sub-agents"]
    map_agent["🗺️ <b>map_agent</b><br/>GeoJSON / interactive map"]
    dataviz_agent["📊 <b>dataviz_agent</b><br/>charts · KPIs · tables"]
    merge["🧠 <b>merge</b><br/>synthesis LLM — final answer"]
    __end__(["<b>End</b>"])

    __start__ --> router

    neo4j_agent["Neo4j Knowledge Graph"]
    rdf_agent["RDF / SPARQL (GraphDB)"]
    vector_agent["Vector Search (Chroma)"]
    postgis_agent["PostGIS Spatial SQL"]
    data_gouv_agent["Data.gouv.fr Open Data"]

    router -- Send --> neo4j_agent
    router -- Send --> rdf_agent
    router -- Send --> vector_agent
    router -- Send --> postgis_agent
    router -- Send --> data_gouv_agent

    neo4j_agent --> post_process_router
    rdf_agent --> post_process_router
    vector_agent --> post_process_router
    postgis_agent --> post_process_router
    data_gouv_agent --> post_process_router

    post_process_router -- Send --> map_agent
    post_process_router -- Send --> dataviz_agent
    map_agent --> merge
    dataviz_agent --> merge
    merge --> __end__
```

## Node descriptions

| Node | Role |
|---|---|
| **Router** | LLM with structured output — selects the minimal set of parallel sub-agents relevant to the query |
| **neo4j\_agent** | Knowledge-graph queries (Cypher / Neo4j) |
| **rdf\_agent** | Linked-data queries (SPARQL / GraphDB) |
| **vector\_agent** | Semantic similarity search (ChromaDB embeddings) |
| **postgis\_agent** | Spatial SQL queries (PostGIS / PostgreSQL) |
| **data\_gouv\_agent** | French government open-data (data.gouv.fr via MCP) |
| **post\_process\_router** | Barrier node — synchronises after all parallel agents complete, then fans out to post-processors |
| **map\_agent** | Converts spatial data into a GeoJSON layer for the interactive map |
| **dataviz\_agent** | Generates charts, KPI cards and tables from sub-agent results |
| **merge** | Synthesis LLM — combines all sub-agent answers into a single streamed response |

## Configuration

Each agent can be individually enabled or disabled via environment variables.
Disabled agents are excluded from the graph entirely.

| Variable | Default |
|---|---|
| `NEO4J_AGENT_ENABLED` | `true` |
| `RDF_AGENT_ENABLED` | `true` |
| `VECTOR_AGENT_ENABLED` | `true` |
| `POSTGIS_AGENT_ENABLED` | `true` |
| `DATA_GOUV_AGENT_ENABLED` | `true` |
| `MAP_AGENT_ENABLED` | `true` |
| `DATAVIZ_AGENT_ENABLED` | `true` |
