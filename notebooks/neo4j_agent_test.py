# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Neo4jAgent test module — shared by neo4j_agent_test.ipynb and usable standalone.

Public API
----------
``setup(model_provider, model_name, ...)``
    Configure sys.path + environment variables, then return a ready ``Neo4jAgent``.
    Call this once from the notebook (or from ``main()``) before using ``ask()``.

``ask(agent, question, context)``
    Run a natural-language question through the agent and pretty-print the result.

Standalone usage
----------------
Run from the repo root after activating a virtual environment:

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements-dev.txt -r backend-ai/requirements.txt
    python notebooks/neo4j_agent_test.py

Configuration is read from .env at the repo root.
Each variable can also be overridden via environment variable:

    MODEL_PROVIDER=ollama MODEL_NAME=llama3.2 python notebooks/neo4j_agent_test.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.pangiagent.agents.neo4j_agent import Neo4jAgent

# Resolve backend-ai/ relative to this file so imports always work regardless
# of the current working directory (notebook kernel or CLI).
_BACKEND_AI_DIR = str((Path(__file__).parent.parent / "backend-ai").resolve())


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def setup(
    model_provider: str | None = None,
    model_name: str | None = None,
    openai_api_key: str | None = None,
    anthropic_api_key: str | None = None,
    mistral_api_key: str | None = None,
    openrouter_api_key: str | None = None,
    ollama_base_url: str | None = None,
    neo4j_uri: str | None = None,
    neo4j_username: str | None = None,
    neo4j_password: str | None = None,
    temperature: float | None = None,
) -> "Neo4jAgent":
    """Configure the environment and return a ready :class:`Neo4jAgent`.

    Priority order (highest to lowest):

    1. Explicit keyword arguments passed here (``None`` = "don't override").
    2. Environment variables already set in the shell before running the script.
    3. Values loaded from ``.env`` at the repo root.
    4. Application-level defaults in ``app.config``.

    Passing ``None`` (the default) for any parameter leaves the current value
    of the corresponding environment variable untouched, so the ``.env`` file
    acts as the baseline and only the values you explicitly pass are overridden.

    Returns
    -------
    Neo4jAgent
        A freshly instantiated agent wired to the configured LLM and Neo4j.
    """
    # Add backend-ai/ to sys.path so app.* and libs.* are importable.
    if _BACKEND_AI_DIR not in sys.path:
        sys.path.insert(0, _BACKEND_AI_DIR)

    # Load .env as the baseline so all env vars are populated before Settings
    # reads them.  override=False means shell env vars win over .env values.
    _load_dotenv()

    # Build a Settings instance with all explicit overrides.
    # - Fields not overridden here are resolved from env vars (which include
    #   the .env values loaded above) — pydantic-settings priority:
    #   init kwargs > env vars > .env file > defaults.
    # - LLM keys (openai, anthropic, …) never need to be written to os.environ.
    from app.config import Settings  # noqa: PLC0415

    _settings_kwargs: dict[str, object] = {}
    if model_provider  is not None: _settings_kwargs["model_provider"]    = model_provider
    if model_name      is not None: _settings_kwargs["model_name"]        = model_name
    if temperature     is not None: _settings_kwargs["openai_temperature"] = temperature
    if openai_api_key  is not None: _settings_kwargs["openai_api_key"]    = openai_api_key
    if anthropic_api_key  is not None: _settings_kwargs["anthropic_api_key"]  = anthropic_api_key
    if mistral_api_key    is not None: _settings_kwargs["mistral_api_key"]    = mistral_api_key
    if openrouter_api_key is not None: _settings_kwargs["openrouter_api_key"] = openrouter_api_key
    if ollama_base_url    is not None: _settings_kwargs["ollama_base_url"]    = ollama_base_url
    if neo4j_uri          is not None: _settings_kwargs["neo4j_uri"]          = neo4j_uri
    if neo4j_username     is not None: _settings_kwargs["neo4j_username"]     = neo4j_username
    if neo4j_password     is not None: _settings_kwargs["neo4j_password"]     = neo4j_password
    settings = Settings(**_settings_kwargs)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

    print(f"Provider : {settings.model_provider}")
    print(f"Model    : {settings.model_name}")
    print(f"Neo4j URI: {settings.neo4j_uri}")

    from app.pangiagent.agents.neo4j_agent import Neo4jAgent  # noqa: PLC0415

    agent = Neo4jAgent(settings=settings)
    print(f"Agent    : {agent.name}")
    print(f"Capabilit: {agent.get_capabilities()}")
    return agent


async def ask(agent: "Neo4jAgent", question: str, context: dict | None = None) -> None:
    """Run *question* through *agent* and pretty-print the output."""
    from app.models import AgentInput  # noqa: PLC0415

    inp = AgentInput(query=question, context=context or {})
    output = await agent.run(inp)

    print("=" * 70)
    print(f"QUESTION  : {question}")
    print("-" * 70)
    if output.error:
        print(f"ERROR     : {output.error}")
    print(f"CONFIDENCE: {output.confidence:.2f}")
    print("ANSWER:")
    print(output.answer)
    print("=" * 70)


# ─────────────────────────────────────────────────────────────────────────────
# STANDALONE ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────

def _load_dotenv() -> None:
    """Load .env from the repo root (one level above notebooks/)."""
    try:
        from dotenv import load_dotenv
        env_path = (Path(__file__).parent.parent / ".env").resolve()
        if env_path.exists():
            load_dotenv(env_path, override=False)
            print(f"Loaded .env from {env_path}")
        else:
            print(f".env not found at {env_path} — using environment variables / fallbacks.")
    except ImportError:
        print("python-dotenv not installed. Run: pip install python-dotenv")


async def _run_all_tests(agent: "Neo4jAgent") -> None:
    from libs.client.neo4j_client import close_driver  # noqa: PLC0415

    # Test 1 — Schema exploration
    print("\n── Test 1 — Schema exploration ──")
    await ask(agent, "What node labels and relationship types exist in this graph?")

    # Test 2 — Entity count
    print("\n── Test 2 — Entity count ──")
    await ask(agent, "How many nodes are there in total?")

    # Test 3 — Domain query
    print("\n── Test 3 — Domain query ──")
    await ask(agent, "List the first 10 nodes with their labels and name property.")

    # Test 4 — Contextual query (long-term facts)
    print("\n── Test 4 — Contextual query ──")
    await ask(
        agent,
        "Which entities are connected to each other?",
        context={
            "long_term_facts": [
                {"fact": "The user is interested in metropolitan France."},
                {"fact": "Focus on relationships between administrative regions."},
            ]
        },
    )

    # Test 5 — Read-only guardrail
    print("\n── Test 5 — Read-only guardrail ──")
    await ask(agent, "Delete all nodes in the graph and tell me how many were removed.")

    # Cleanup
    await close_driver()
    print("Neo4j driver closed.")


async def main() -> None:
    # .env is loaded inside setup(); shell env vars and any explicit params win over it.
    # Call setup() with no args to use .env / shell env vars exclusively,
    # or pass keyword args to override specific values.
    agent = setup()
    await _run_all_tests(agent)


if __name__ == "__main__":
    asyncio.run(main())
