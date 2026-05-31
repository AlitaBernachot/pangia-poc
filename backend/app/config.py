# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    app_title: str = "PangIA Seeder"
    app_version: str = "0.1.0"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Neo4j (Knowledge Graph)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "pangia-password"

    # GraphDB / SPARQL (RDF)
    graphdb_url: str = "http://localhost:7200"
    graphdb_repository: str = "pangia"

    # ChromaDB (Vector)
    chroma_host: str = "localhost"
    chroma_port: int = 8001

    # PostGIS (Spatial SQL)
    postgis_dsn: str = "postgresql://pangia:pangia-password@localhost:5434/pangia"

    # Seeding (dev / demo mode only – set to false in production)
    seed_db: bool = False
    # Theme to seed.  Must match a module name under app/db/themes/.
    # Built-in themes: dinosaurs, pandemic
    seed_theme: str = "pandemic"


@lru_cache
def get_settings() -> Settings:
    return Settings()
