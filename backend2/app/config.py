# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_title: str = "PangIA Multi-Agent Backend"
    app_version: str = "2.0.0"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173", "http://frontend-client"]

    # LLM — global defaults (can be overridden per-agent via {agent_name}_model_*)
    model_provider: str = "openai"
    model_name: str = "gpt-4o-mini"
    openai_api_key: str = ""
    openai_temperature: float = 0.0
    anthropic_api_key: str = ""
    mistral_api_key: str = ""

    # PostgreSQL (audit + long-term memory)
    postgres_dsn: str = "postgresql+asyncpg://pangia2:pangia2-password@postgres2:5432/pangia2"

    # Redis (short-term memory + HITL state)
    redis_url: str = "redis://redis:6379"
    session_ttl_seconds: int = 3600

    # HITL
    hitl_timeout_seconds: int = 120
    hitl_ambiguity_threshold: float = 0.8

    # Ollama
    ollama_base_url: str = "http://ollama:11434"

    # Arize Phoenix (agent observability)
    phoenix_collector_endpoint: str = "http://localhost:6006/v1/traces"
    phoenix_project_name: str = "pangia"

    # Neo4j (knowledge graph)
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""

    # ChromaDB (vector search)
    chroma_host: str = "chroma"
    chroma_port: int = 8000

    # PostGIS (spatial SQL — separate from the audit postgres_dsn)
    postgis_dsn: str = "postgresql+asyncpg://pangia:pangia-password@postgres:5432/pangia"

    # GraphDB / Ontotext (RDF / SPARQL)
    graphdb_url: str = "http://graphdb:7200"
    graphdb_repository: str = "pangia"

    # data.gouv.fr MCP
    data_gouv_mcp_url: str = "https://mcp.data.gouv.fr/mcp"

    # Routing strategy
    # When True, router_node uses SmartDispatcherAgent (keyword + semantic, no LLM).
    # When False, the LLM-based DynamicRouter is used instead.
    smart_dispatcher_enabled: bool = True

    # ReAct loop iteration limits
    # Global fallback used when a per-agent override is 0 (the default).
    agent_max_iterations: int = 10

    # Per-agent overrides — set to 0 to inherit the global value above.
    neo4j_agent_max_iterations: int = 0
    postgis_agent_max_iterations: int = 0
    rdf_agent_max_iterations: int = 0
    vector_chroma_agent_max_iterations: int = 0
    datagouv_mcp_agent_max_iterations: int = 0
    geonetwork_mcp_agent_max_iterations: int = 0
    rag_agent_max_iterations: int = 0
    calculator_agent_max_iterations: int = 0
    summary_agent_max_iterations: int = 0


@lru_cache
def get_settings() -> Settings:
    return Settings()
