"""Model configuration interface for PangIA agents.

Each agent can be individually configured to use a specific LLM provider and
model name.  The configuration falls back to the global OpenAI settings when
no agent-specific values are provided.

Supported providers
-------------------
- ``openai``    – OpenAI chat models (default; requires ``langchain-openai``)
- ``anthropic`` – Anthropic Claude models (requires ``langchain-anthropic``)
- ``ollama``    – Locally-hosted models via Ollama (requires ``langchain-ollama``)

Adding a new provider
---------------------
1. Install the corresponding ``langchain-<provider>`` package.
2. Import the chat-model class and add it to ``PROVIDER_CLASS_MAP``.
3. Set the ``<AGENT>_MODEL_PROVIDER`` env variable for the desired agent(s).
"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

# ─── Provider registry ────────────────────────────────────────────────────────

# Maps provider name → LangChain chat-model class.
# Only providers whose packages are installed are registered automatically.
PROVIDER_CLASS_MAP: dict[str, type[BaseChatModel]] = {
    "openai": ChatOpenAI,
}

try:
    from langchain_anthropic import ChatAnthropic  # type: ignore[import]

    PROVIDER_CLASS_MAP["anthropic"] = ChatAnthropic
except ImportError:
    pass

try:
    from langchain_ollama import ChatOllama  # type: ignore[import]

    PROVIDER_CLASS_MAP["ollama"] = ChatOllama
except ImportError:
    pass


# ─── ModelConfig interface ────────────────────────────────────────────────────


class ModelConfig(BaseModel):
    """Configuration for a single LLM instance used by an agent."""

    provider: str = "openai"
    """Provider name – must be a key in :data:`PROVIDER_CLASS_MAP`."""

    model: str
    """Model identifier passed to the provider (e.g. ``"gpt-4o-mini"``)."""

    temperature: float = 0.0
    """Sampling temperature (0.0 = deterministic)."""

    api_key: str | None = None
    """Provider API key.  When ``None`` the provider's default env-var is used."""

    base_url: str | None = None
    """Optional custom API base URL (e.g. for Ollama or proxy setups)."""


# ─── Factory ─────────────────────────────────────────────────────────────────


def build_llm(config: ModelConfig, *, streaming: bool = False) -> BaseChatModel:
    """Instantiate and return the appropriate LangChain chat model.

    Parameters
    ----------
    config:
        A :class:`ModelConfig` specifying the provider, model, and
        connection details.
    streaming:
        When ``True``, the returned model will stream tokens back to the
        caller (used by sub-agents and the merge node).

    Raises
    ------
    ValueError
        If ``config.provider`` is not registered in :data:`PROVIDER_CLASS_MAP`.
    """
    cls = PROVIDER_CLASS_MAP.get(config.provider)
    if cls is None:
        supported = ", ".join(sorted(PROVIDER_CLASS_MAP))
        raise ValueError(
            f"Unknown model provider {config.provider!r}. "
            f"Supported providers: {supported}."
        )

    kwargs: dict = {
        "model": config.model,
        "temperature": config.temperature,
        "streaming": streaming,
    }
    if config.api_key is not None:
        kwargs["api_key"] = config.api_key
    if config.base_url is not None:
        kwargs["base_url"] = config.base_url

    return cls(**kwargs)


# ─── Per-agent config resolver ────────────────────────────────────────────────

# Canonical agent names used as prefixes in Settings fields.
AGENT_NAMES = [
    "router",
    "neo4j_agent",
    "rdf_agent",
    "vector_agent",
    "postgis_agent",
    "map_agent",
    "data_gouv_agent",
    "merge",
]


def get_agent_model_config(agent_key: str) -> ModelConfig:
    """Return the :class:`ModelConfig` for *agent_key*.

    Looks up ``<agent_key>_model_provider`` and ``<agent_key>_model_name``
    from the application settings.  Empty or missing values fall back to the
    global ``openai_model`` / ``openai_api_key`` / ``openai_temperature``
    settings.

    Parameters
    ----------
    agent_key:
        One of the keys in :data:`AGENT_NAMES` (e.g. ``"neo4j_agent"``).
    """
    # Deferred import to avoid a circular dependency at module level
    from app.config import get_settings  # noqa: PLC0415

    settings = get_settings()

    provider = getattr(settings, f"{agent_key}_model_provider", "") or "openai"
    model = getattr(settings, f"{agent_key}_model_name", "") or settings.openai_model

    return ModelConfig(
        provider=provider,
        model=model,
        temperature=settings.openai_temperature,
        api_key=settings.openai_api_key if settings.openai_api_key else None,
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
