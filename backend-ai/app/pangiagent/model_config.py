# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Per-agent model configuration resolver for PangIA agents.

This module handles per-agent LLM configuration resolution from environment
variables.  All provider-specific code (imports, class registry, and the LLM
factory) lives in :mod:`app.pangiagent.provider_config`.

Supported providers
-------------------
See :mod:`app.pangiagent.provider_config` for the full list.  To add a new
provider, edit that module — not this one.

Public API
----------
``AgentModelConfig``
    Pydantic model grouping all LLM construction parameters for one agent.

``PROVIDER_CLASS_MAP`` / ``build_llm``
    Re-exported from :mod:`app.pangiagent.provider_config` for backwards
    compatibility; prefer importing directly from that module in new code.

``get_agent_model_config(agent_name)``
    Build an :class:`AgentModelConfig` from application settings, honouring
    per-agent overrides before falling back to global defaults.

``get_agent_max_iterations(agent_key)``
    Return the maximum ReAct loop iterations for *agent_key*.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.config import Settings

# Re-export for backwards compatibility so existing imports keep working.
from app.pangiagent.provider_config import PROVIDER_CLASS_MAP, build_llm  # noqa: F401

__all__ = [
    "AgentModelConfig",
    "PROVIDER_CLASS_MAP",
    "build_llm",
    "get_agent_model_config",
    "get_agent_max_iterations",
]


# ---------------------------------------------------------------------------
# Configuration model
# ---------------------------------------------------------------------------


class AgentModelConfig(BaseModel):
    """All parameters required to instantiate a chat LLM for one agent."""

    provider: str
    """Provider name — must be a key in :data:`~app.pangiagent.provider_config.PROVIDER_CLASS_MAP`."""

    model: str
    """Model identifier passed to the provider (e.g. ``"gpt-4o-mini"``)."""

    temperature: float
    """Sampling temperature (0.0 = deterministic)."""

    api_key: str | None = None
    """Provider API key.  When ``None`` the provider's default env-var is used."""

    base_url: str | None = None
    """Optional custom API base URL (e.g. for Ollama or proxy setups)."""

    kaggle_username: str | None = None
    """Kaggle username — required when ``provider='googleai'``."""


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def get_agent_max_iterations(
    agent_key: str,
    settings: "Settings | None" = None,
) -> int:
    """Return the maximum ReAct loop iterations for *agent_key*.

    Looks up ``<agent_key>_max_iterations`` from application settings.
    A value of 0 (the default) means "use the global ``agent_max_iterations``".

    Parameters
    ----------
    agent_key:
        Snake-case agent name, e.g. ``"neo4j_agent"``.
    settings:
        Optional :class:`~app.config.Settings` instance.  When ``None``
        (default) :func:`~app.config.get_settings` is called so the value is
        resolved from environment variables / ``.env``.
    """
    from app.config import Settings, get_settings  # noqa: PLC0415

    if settings is None:
        settings = get_settings()
    per_agent: int = getattr(settings, f"{agent_key}_max_iterations", 0)
    return per_agent if per_agent > 0 else settings.agent_max_iterations


def get_agent_model_config(
    agent_name: str,
    settings: "Settings | None" = None,
) -> AgentModelConfig:
    """Build an :class:`AgentModelConfig` for *agent_name* from settings.

    Resolution order for each field:

    1. Per-agent override env var (``{AGENT_NAME}_MODEL_PROVIDER``,
       ``{AGENT_NAME}_MODEL_NAME``, ``{AGENT_NAME}_TEMPERATURE``).
    2. Global defaults (``MODEL_PROVIDER``, ``MODEL_NAME``,
       ``OPENAI_TEMPERATURE``).

    The correct *api_key*, *base_url*, and *kaggle_username* are selected
    automatically based on the resolved provider.

    Parameters
    ----------
    agent_name:
        Snake-case agent name, e.g. ``"rag_agent"``.
    settings:
        Optional :class:`~app.config.Settings` instance.  When ``None``
        (default) :func:`~app.config.get_settings` is called so the value is
        resolved from environment variables / ``.env``.  Pass an explicit
        ``Settings(...)`` to bypass env vars entirely — useful in notebooks.

    Returns
    -------
    AgentModelConfig
    """
    from app.config import Settings, get_settings  # noqa: PLC0415

    if settings is None:
        settings = get_settings()

    provider: str = (
        getattr(settings, f"{agent_name}_model_provider", None)
        or settings.model_provider
    )
    model: str = (
        getattr(settings, f"{agent_name}_model_name", None)
        or settings.model_name
    )
    temperature_override = getattr(settings, f"{agent_name}_temperature", None)
    temperature: float = (
        float(temperature_override)
        if temperature_override is not None
        else settings.openai_temperature
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

    return AgentModelConfig(
        provider=provider,
        model=model,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
        kaggle_username=kaggle_username,
    )
