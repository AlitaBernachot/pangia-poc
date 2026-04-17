# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_title: str = "PangIA V2 Multi-Agent Backend"
    app_version: str = "2.0.0"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173", "http://frontend-client"]

    # LLM
    model_provider: str = "openai"
    model_name: str = "gpt-4o-mini"
    openai_api_key: str = ""
    openai_temperature: float = 0.0

    # PostgreSQL (audit + long-term memory)
    postgres_dsn: str = "postgresql+asyncpg://pangia2:pangia2-password@postgres2:5432/pangia2"

    # Redis (short-term memory + HITL state)
    redis_url: str = "redis://redis:6379"
    session_ttl_seconds: int = 3600

    # HITL
    hitl_timeout_seconds: int = 120
    hitl_ambiguity_threshold: float = 0.7

    # Ollama
    ollama_base_url: str = "http://ollama:11434"

    # Arize Phoenix (agent observability)
    phoenix_collector_endpoint: str = "http://localhost:6006/v1/traces"
    phoenix_project_name: str = "pangia"


@lru_cache
def get_settings() -> Settings:
    return Settings()
