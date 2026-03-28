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
    mapviz_agent_enabled: bool = True
    data_gouv_agent_enabled: bool = True
    dataviz_agent_enabled: bool = True
    geo_agent_enabled: bool = True
    humanoutput_agent_enabled: bool = True

    # Maximum number of LLM+tool iterations (ReAct loop) per agent.
    # Each iteration = one LLM call + zero or more tool calls.
    # Lower this to reduce latency / cost; raise it for complex multi-step tasks.
    # Global fallback used when no per-agent value is set (or when set to 0).
    agent_max_iterations: int = 10

    # Per-agent max iterations overrides.
    # Set to 0 (default) to fall back to the global AGENT_MAX_ITERATIONS value.
    neo4j_agent_max_iterations: int = 0
    rdf_agent_max_iterations: int = 0
    vector_agent_max_iterations: int = 0
    postgis_agent_max_iterations: int = 0
    mapviz_agent_max_iterations: int = 0
    data_gouv_agent_max_iterations: int = 0
    dataviz_agent_max_iterations: int = 0
    geo_agent_max_iterations: int = 0
    humanoutput_agent_max_iterations: int = 0
    geo_address_agent_max_iterations: int = 0
    geo_spatial_parser_agent_max_iterations: int = 0
    geo_distance_agent_max_iterations: int = 0
    geo_buffer_agent_max_iterations: int = 0
    geo_isochrone_agent_max_iterations: int = 0
    geo_proximity_agent_max_iterations: int = 0
    geo_intersection_agent_max_iterations: int = 0
    geo_area_agent_max_iterations: int = 0
    geo_hotspot_agent_max_iterations: int = 0
    geo_shortest_path_agent_max_iterations: int = 0
    geo_elevation_agent_max_iterations: int = 0
    geo_geometry_ops_agent_max_iterations: int = 0
    geo_temporal_agent_max_iterations: int = 0
    geo_viewshed_agent_max_iterations: int = 0

    # Per-agent model configuration
    # For each agent set <AGENT>_MODEL_PROVIDER and <AGENT>_MODEL_NAME to
    # override the model used by that agent.  Leave empty ("") to fall back to
    # the global OPENAI_MODEL / OPENAI_API_KEY values above.
    # Supported providers: "openai" (default), "anthropic", "ollama".
    router_model_provider: str = ""
    router_model_name: str = ""
    neo4j_agent_model_provider: str = ""
    neo4j_agent_model_name: str = ""
    rdf_agent_model_provider: str = ""
    rdf_agent_model_name: str = ""
    vector_agent_model_provider: str = ""
    vector_agent_model_name: str = ""
    postgis_agent_model_provider: str = ""
    postgis_agent_model_name: str = ""
    mapviz_agent_model_provider: str = ""
    mapviz_agent_model_name: str = ""
    data_gouv_agent_model_provider: str = ""
    data_gouv_agent_model_name: str = ""
    dataviz_agent_model_provider: str = ""
    dataviz_agent_model_name: str = ""
    humanoutput_agent_model_provider: str = ""
    humanoutput_agent_model_name: str = ""
    geo_agent_model_provider: str = ""
    geo_agent_model_name: str = ""
    geo_address_agent_model_provider: str = ""
    geo_address_agent_model_name: str = ""
    geo_spatial_parser_agent_model_provider: str = ""
    geo_spatial_parser_agent_model_name: str = ""
    geo_distance_agent_model_provider: str = ""
    geo_distance_agent_model_name: str = ""
    geo_buffer_agent_model_provider: str = ""
    geo_buffer_agent_model_name: str = ""
    geo_isochrone_agent_model_provider: str = ""
    geo_isochrone_agent_model_name: str = ""
    geo_proximity_agent_model_provider: str = ""
    geo_proximity_agent_model_name: str = ""
    geo_intersection_agent_model_provider: str = ""
    geo_intersection_agent_model_name: str = ""
    geo_area_agent_model_provider: str = ""
    geo_area_agent_model_name: str = ""
    geo_hotspot_agent_model_provider: str = ""
    geo_hotspot_agent_model_name: str = ""
    geo_shortest_path_agent_model_provider: str = ""
    geo_shortest_path_agent_model_name: str = ""
    geo_elevation_agent_model_provider: str = ""
    geo_elevation_agent_model_name: str = ""
    geo_geometry_ops_agent_model_provider: str = ""
    geo_geometry_ops_agent_model_name: str = ""
    geo_temporal_agent_model_provider: str = ""
    geo_temporal_agent_model_name: str = ""
    geo_viewshed_agent_model_provider: str = ""
    geo_viewshed_agent_model_name: str = ""
    merge_model_provider: str = ""
    merge_model_name: str = ""

    # ── Input Guardrails ──────────────────────────────────────────────────────
    # Master switch – set to false to bypass all guardrail checks.
    guardrail_enabled: bool = True

    # Content filtering
    # Scan for PII patterns (email, phone, credit card, …) using regex.
    guardrail_content_filter_enabled: bool = True
    guardrail_pii_filter_enabled: bool = True
    # Classify toxicity / harmful content using the LLM (adds one LLM call).
    guardrail_toxicity_filter_enabled: bool = True

    # Intent validation – detect prompt-injection / jailbreak (adds one LLM call).
    guardrail_intent_validation_enabled: bool = True

    # Rate limiting (Redis-backed fixed-window counter).
    guardrail_rate_limit_enabled: bool = True
    # Maximum number of requests allowed per session within the window.
    guardrail_rate_limit_max_requests: int = 60
    # Window duration in seconds.
    guardrail_rate_limit_window_seconds: int = 60

    # Authentication – require X-API-Key header when enabled.
    guardrail_auth_enabled: bool = False
    # Secret API key value (set this in .env; never commit the real key).
    guardrail_api_key: str = ""

    # Arize Phoenix (agent observability)
    phoenix_collector_endpoint: str = "http://localhost:6006/v1/traces"
    phoenix_project_name: str = "pangia-geoia"


@lru_cache
def get_settings() -> Settings:
    return Settings()
