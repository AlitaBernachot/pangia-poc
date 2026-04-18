# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Multi-provider LLM configuration for PangIA agents.

This module centralises all LLM instantiation logic so that:

* Any agent can switch provider (OpenAI, Anthropic, Mistral, Ollama) via
  environment variables without touching agent code.
* Per-agent model overrides are supported by naming env vars after the agent
  (e.g. ``RAG_AGENT_MODEL_NAME``).
* Optional provider packages (Anthropic, Mistral, Ollama) are imported
  lazily so that a missing package only raises an error when that specific
  provider is actually requested.

Public API
----------
``AgentModelConfig``
    Pydantic model grouping all LLM construction parameters.

``PROVIDER_CLASS_MAP``
    ``dict[str, type[BaseChatModel]]`` used by :func:`build_llm`.

``build_llm(config)``
    Instantiate and return the correct ``BaseChatModel`` for *config*.

``get_agent_model_config(agent_name)``
    Build an :class:`AgentModelConfig` from :func:`~app.config.get_settings`,
    honouring per-agent overrides before falling back to global defaults.
"""
from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.config import get_settings

# ---------------------------------------------------------------------------
# Optional provider imports — guarded so startup never fails due to a missing
# optional dependency.
# ---------------------------------------------------------------------------

try:
    from langchain_anthropic import ChatAnthropic  # type: ignore[import-untyped]
except ImportError:
    ChatAnthropic = None  # type: ignore[assignment,misc]

try:
    from langchain_mistralai import ChatMistralAI  # type: ignore[import-untyped]
except ImportError:
    ChatMistralAI = None  # type: ignore[assignment,misc]

try:
    from langchain_ollama import ChatOllama  # type: ignore[import-untyped]
except ImportError:
    ChatOllama = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

PROVIDER_CLASS_MAP: dict[str, type[BaseChatModel] | None] = {
    "openai": ChatOpenAI,
    "anthropic": ChatAnthropic,
    "mistral": ChatMistralAI,
    "ollama": ChatOllama,
}


# ---------------------------------------------------------------------------
# Configuration model
# ---------------------------------------------------------------------------


class AgentModelConfig(BaseModel):
    """All parameters required to instantiate a chat LLM for one agent."""

    provider: str
    model: str
    temperature: float
    api_key: str | None = None
    base_url: str | None = None


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def build_llm(config: AgentModelConfig) -> BaseChatModel:
    """Instantiate and return the ``BaseChatModel`` described by *config*.

    Parameters
    ----------
    config:
        An :class:`AgentModelConfig` obtained from
        :func:`get_agent_model_config`.

    Returns
    -------
    BaseChatModel
        A ready-to-use LangChain chat model instance.

    Raises
    ------
    ValueError
        If *config.provider* is not a key in :data:`PROVIDER_CLASS_MAP` or
        if the corresponding package has not been installed.
    """
    provider = config.provider.lower()
    if provider not in PROVIDER_CLASS_MAP:
        raise ValueError(
            f"Unknown LLM provider '{provider}'. "
            f"Supported providers: {sorted(PROVIDER_CLASS_MAP)}"
        )

    cls = PROVIDER_CLASS_MAP[provider]
    if cls is None:
        raise ValueError(
            f"Provider '{provider}' is registered but its package is not "
            "installed. Install the corresponding langchain integration package."
        )

    kwargs: dict[str, Any] = {
        "model": config.model,
        "temperature": config.temperature,
    }
    if config.api_key:
        kwargs["api_key"] = config.api_key
    if config.base_url:
        kwargs["base_url"] = config.base_url

    return cls(**kwargs)  # type: ignore[return-value]


def get_agent_model_config(agent_name: str) -> AgentModelConfig:
    """Build an :class:`AgentModelConfig` for *agent_name* from settings.

    Resolution order for each field:

    1. Per-agent override env var (``{AGENT_NAME}_MODEL_PROVIDER``,
       ``{AGENT_NAME}_MODEL_NAME``, ``{AGENT_NAME}_TEMPERATURE``).
    2. Global defaults (``MODEL_PROVIDER``, ``MODEL_NAME``,
       ``OPENAI_TEMPERATURE``).

    The correct *api_key* and *base_url* are selected automatically based on
    the resolved provider.

    Parameters
    ----------
    agent_name:
        Snake-case agent name, e.g. ``"rag_agent"``.

    Returns
    -------
    AgentModelConfig
    """
    settings = get_settings()

    # Per-agent override field names follow the pattern "{agent_name}_model_*"
    # so that they map to env vars like RAG_AGENT_MODEL_PROVIDER.
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

    # Pick api_key and base_url based on the resolved provider.
    provider_lower = provider.lower()
    api_key: str | None
    base_url: str | None

    if provider_lower == "openai":
        api_key = settings.openai_api_key or None
        base_url = None
    elif provider_lower == "anthropic":
        api_key = getattr(settings, "anthropic_api_key", None) or None
        base_url = None
    elif provider_lower == "mistral":
        api_key = getattr(settings, "mistral_api_key", None) or None
        base_url = None
    elif provider_lower == "ollama":
        api_key = None
        base_url = getattr(settings, "ollama_base_url", None) or None
    else:
        api_key = None
        base_url = None

    return AgentModelConfig(
        provider=provider,
        model=model,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
    )
