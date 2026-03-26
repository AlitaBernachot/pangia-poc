from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    app_title: str = "Pangia GeoIA Agent"
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

    # Arize Phoenix (agent observability)
    phoenix_collector_endpoint: str = "http://localhost:6006/v1/traces"
    phoenix_project_name: str = "pangia-geoia"


@lru_cache
def get_settings() -> Settings:
    return Settings()
