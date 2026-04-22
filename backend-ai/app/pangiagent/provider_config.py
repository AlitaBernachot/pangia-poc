# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Provider registration and LLM factory for PangIA agents.

This module centralises all provider-specific code: lazy imports, the
provider class registry, and the :func:`build_llm` factory.  It is the
single place to add or modify an LLM provider without touching agent code
or the per-agent configuration resolver in
:mod:`app.pangiagent.model_config`.

Supported providers
-------------------
- ``openai``      – OpenAI chat models (requires ``langchain-openai``)
- ``anthropic``   – Anthropic Claude models (requires ``langchain-anthropic``)
- ``mistral``     – Mistral AI models (requires ``langchain-mistralai``)
- ``ollama``      – Locally-hosted models via Ollama (requires ``langchain-ollama``)
- ``openrouter``  – OpenRouter proxy — routes to 200+ models via native client
                    (requires ``langchain-openrouter``; set ``OPENROUTER_API_KEY``)
- ``googleai``    – Google Gemma local model via Kaggle
                    (requires ``langchain-google-vertexai``;
                    set ``KAGGLE_USERNAME`` and ``KAGGLE_KEY``)

Adding a new provider
---------------------
1. Install the corresponding ``langchain-<provider>`` package and add it to
   ``requirements.txt``.
2. Add a guarded import block below and register the class (or ``None`` if
   unavailable) in :data:`PROVIDER_CLASS_MAP`.
3. If the provider has a non-standard constructor, add a branch in
   :func:`build_llm` to build ``kwargs`` correctly.
4. Add the provider's credentials to ``config.py`` and handle them inside
   :func:`~app.pangiagent.model_config.get_agent_model_config`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

if TYPE_CHECKING:
    from app.pangiagent.model_config import AgentModelConfig

# ---------------------------------------------------------------------------
# Optional provider imports — guarded so startup never fails due to a missing
# optional dependency.
# ---------------------------------------------------------------------------

try:
    from langchain_anthropic import ChatAnthropic  # type: ignore[import-untyped]

    PROVIDER_CLASS_MAP: dict[str, type] = {
        "anthropic": ChatAnthropic,
    }
except ImportError:
    PROVIDER_CLASS_MAP = {}

try:
    from langchain_mistralai import ChatMistralAI  # type: ignore[import-untyped]

    PROVIDER_CLASS_MAP["mistral"] = ChatMistralAI
except ImportError:
    pass

try:
    from langchain_ollama import ChatOllama  # type: ignore[import-untyped]

    PROVIDER_CLASS_MAP["ollama"] = ChatOllama
except ImportError:
    pass

try:
    from langchain_google_vertexai import GemmaLocalKaggle  # type: ignore[import-untyped]

    PROVIDER_CLASS_MAP["googleai"] = GemmaLocalKaggle
except ImportError:
    pass

# OpenAI is a required dependency — no guard needed.
PROVIDER_CLASS_MAP["openai"] = ChatOpenAI

try:
    from langchain_openrouter import ChatOpenRouter  # type: ignore[import-untyped]

    PROVIDER_CLASS_MAP["openrouter"] = ChatOpenRouter
except ImportError:
    pass


def build_llm(config: "AgentModelConfig") -> BaseChatModel:
    """Instantiate and return the ``BaseChatModel`` described by *config*.

    Parameters
    ----------
    config:
        An :class:`~app.pangiagent.model_config.AgentModelConfig` obtained
        from :func:`~app.pangiagent.model_config.get_agent_model_config`.

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
    cls = PROVIDER_CLASS_MAP.get(provider)
    if cls is None:
        supported = ", ".join(sorted(PROVIDER_CLASS_MAP))
        raise ValueError(
            f"Unknown LLM provider '{provider}'. "
            f"Supported providers: {supported}"
        )

    # ── Google AI — GemmaLocalKaggle has a different constructor ───────────
    if provider == "googleai":
        kaggle_envs: dict[str, str] = {}
        if config.kaggle_username is not None:
            kaggle_envs["KAGGLE_USERNAME"] = config.kaggle_username
        if config.api_key is not None:
            kaggle_envs["KAGGLE_KEY"] = config.api_key
        return cls(model=config.model, kaggle_envs=kaggle_envs)  # type: ignore[return-value]

    # ── All other providers (OpenAI, Anthropic, Mistral, Ollama, OpenRouter) ─
    kwargs: dict[str, Any] = {
        "model": config.model,
        "temperature": config.temperature,
    }
    if config.api_key is not None:
        kwargs["api_key"] = config.api_key
    if config.base_url is not None:
        kwargs["base_url"] = config.base_url

    return cls(**kwargs)  # type: ignore[return-value]
