from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    app_title: str = "PangIA GeoIA Agent"
    app_version: str = "0.1.0"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # LLM
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = 0.0

    # Neo4j (Knowledge Graph agent)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "pangia-password"

    # GraphDB / SPARQL (RDF agent)
    graphdb_url: str = "http://localhost:7200"
    graphdb_repository: str = "pangia"

    # ChromaDB (Vector agent)
    chroma_host: str = "localhost"
    chroma_port: int = 8001

    # PostGIS (Spatial SQL agent)
    postgis_dsn: str = "postgresql://pangia:pangia-password@localhost:5432/pangia"

    # Redis (sessions)
    redis_url: str = "redis://localhost:6379"
    session_ttl_seconds: int = 3600  # 1 hour

    # Seeding (dev / demo mode only – set to false in production)
    seed_db: bool = False
    # Theme to seed.  Must match a module name under app/db/themes/.
    # Built-in themes: dinosaurs, pandemic
    seed_theme: str = "pandemic"

    # data.gouv.fr MCP agent
    data_gouv_mcp_url: str = "https://mcp.data.gouv.fr/mcp"

    # Agent enable / disable flags  (master orchestrator is always active)
    # Set any of these to false via environment variable to disable that agent.
    neo4j_agent_enabled: bool = True
    rdf_agent_enabled: bool = True
    vector_agent_enabled: bool = True
    postgis_agent_enabled: bool = True
    map_agent_enabled: bool = True
    data_gouv_agent_enabled: bool = True

    # Arize Phoenix (agent observability)
    phoenix_collector_endpoint: str = "http://localhost:6006/v1/traces"
    phoenix_project_name: str = "pangia-geoia"


@lru_cache
def get_settings() -> Settings:
    return Settings()
