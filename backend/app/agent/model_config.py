# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Per-agent model configuration resolver for PangIA agents.

This module handles per-agent LLM configuration resolution from environment
variables.  All provider-specific code (imports, class registry, and the LLM
factory) lives in :mod:`app.agent.provider_config`.

Supported providers
-------------------
See :mod:`app.agent.provider_config` for the full list.  To add a new
provider, edit that module — not this one.

Public API
----------
``ModelConfig``
    Pydantic model grouping all LLM construction parameters for one agent.

``build_llm`` / ``PROVIDER_CLASS_MAP``
    Re-exported from :mod:`app.agent.provider_config` for backwards
    compatibility; prefer importing directly from that module in new code.

``get_agent_model_config(agent_key)``
    Build a :class:`ModelConfig` from application settings, honouring
    per-agent overrides before falling back to global defaults.

``get_agent_max_iterations(agent_key)``
    Return the maximum ReAct loop iterations for *agent_key*.
"""
from __future__ import annotations

from pydantic import BaseModel

# Re-export for backwards compatibility so existing imports keep working.
from app.agent.provider_config import PROVIDER_CLASS_MAP, build_llm  # noqa: F401

__all__ = [
    "ModelConfig",
    "PROVIDER_CLASS_MAP",
    "build_llm",
    "AGENT_NAMES",
    "get_agent_model_config",
    "get_agent_max_iterations",
]


# ─── ModelConfig interface ────────────────────────────────────────────────────


class ModelConfig(BaseModel):
    """Configuration for a single LLM instance used by an agent."""

    provider: str = "openai"
    """Provider name – must be a key in :data:`~app.agent.provider_config.PROVIDER_CLASS_MAP`."""

    model: str
    """Model identifier passed to the provider (e.g. ``"gpt-4o-mini"``)."""

    temperature: float = 0.0
    """Sampling temperature (0.0 = deterministic)."""

    api_key: str | None = None
    """Provider API key.  When ``None`` the provider's default env-var is used."""

    base_url: str | None = None
    """Optional custom API base URL (e.g. for Ollama or proxy setups)."""

    kaggle_username: str | None = None
    """Kaggle username — required when ``provider='googleai'``."""


# ─── Per-agent config resolver ────────────────────────────────────────────────

# Canonical agent names used as prefixes in Settings fields.
AGENT_NAMES = [
    "router",
    "intent_parser_agent",
    "smart_dispatcher_agent",
    "neo4j_agent",
    "rdf_agent",
    "vector_chroma_agent",
    "postgis_agent",
    "mapviz_agent",
    "datagouv_mcp_agent",
    "geonetwork_mcp_agent",
    "dataviz_agent",
    "humanoutput_agent",
    "geo_agent",
    "geo_address_agent",
    "geo_spatial_parser_agent",
    "geo_distance_agent",
    "geo_buffer_agent",
    "geo_isochrone_agent",
    "geo_proximity_agent",
    "geo_intersection_agent",
    "geo_area_agent",
    "geo_hotspot_agent",
    "geo_shortest_path_agent",
    "geo_elevation_agent",
    "geo_geometry_ops_agent",
    "geo_temporal_agent",
    "geo_viewshed_agent",
    "merge",
]


def get_agent_model_config(agent_key: str) -> ModelConfig:
    """Return the :class:`ModelConfig` for *agent_key*.

    Looks up ``<agent_key>_model_provider`` and ``<agent_key>_model_name``
    from the application settings.  Empty or missing values fall back to the
    global ``model_provider`` / ``model_name`` settings.

    The correct *api_key*, *base_url*, and *kaggle_username* are selected
    automatically based on the resolved provider.

    Parameters
    ----------
    agent_key:
        One of the keys in :data:`AGENT_NAMES` (e.g. ``"neo4j_agent"``).
    """
    # Deferred import to avoid a circular dependency at module level
    from app.config import get_settings  # noqa: PLC0415

    settings = get_settings()

    provider: str = (
        getattr(settings, f"{agent_key}_model_provider", "") or settings.model_provider
    )
    model: str = (
        getattr(settings, f"{agent_key}_model_name", "")
        or settings.model_name
        or getattr(settings, "openai_model", "")
        or "gpt-4o-mini"
    )

    provider_lower = provider.lower()
    api_key: str | None = None
    base_url: str | None = None
    kaggle_username: str | None = None

    if provider_lower == "openai":
        api_key = settings.openai_api_key or None
    elif provider_lower == "anthropic":
        api_key = getattr(settings, "anthropic_api_key", None) or None
    elif provider_lower == "mistral":
        api_key = getattr(settings, "mistral_api_key", None) or None
    elif provider_lower == "ollama":
        base_url = getattr(settings, "ollama_base_url", None) or None
    elif provider_lower == "openrouter":
        api_key = getattr(settings, "openrouter_api_key", None) or None
    elif provider_lower == "googleai":
        api_key = getattr(settings, "kaggle_key", None) or None
        kaggle_username = getattr(settings, "kaggle_username", None) or None

    return ModelConfig(
        provider=provider,
        model=model,
        temperature=settings.openai_temperature,
        api_key=api_key,
        base_url=base_url,
        kaggle_username=kaggle_username,
    )


def get_agent_max_iterations(agent_key: str) -> int:
    """Return the maximum ReAct loop iterations for *agent_key*.

    Looks up ``<agent_key>_max_iterations`` from application settings.
    A value of 0 (the default) means "use the global ``agent_max_iterations``".

    Parameters
    ----------
    agent_key:
        One of the keys in :data:`AGENT_NAMES` (e.g. ``"neo4j_agent"``).
    """
    from app.config import get_settings  # noqa: PLC0415

    settings = get_settings()
    per_agent: int = getattr(settings, f"{agent_key}_max_iterations", 0)
    return per_agent if per_agent > 0 else settings.agent_max_iterations
