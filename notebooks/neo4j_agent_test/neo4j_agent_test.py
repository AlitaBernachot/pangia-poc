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

    # Avec une question personnalisée
    python notebooks/neo4j_agent_test.py "How many nodes are there?"
    python notebooks/neo4j_agent_test.py --question "List all regions" --context '{"key": "value"}'

Configuration is read from .env at the repo root.
Each variable can also be overridden via environment variable:

    MODEL_PROVIDER=ollama MODEL_NAME=llama3.2 python notebooks/neo4j_agent_test.py
"""

    
from __future__ import annotations
import sys
from pathlib import Path
import argparse
import asyncio
import json
import logging
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any


# Ajouter backend-ai au PYTHONPATH automatiquement
_BACKEND_AI_PATH = Path(__file__).parent.parent.parent / "backend-ai"
if str(_BACKEND_AI_PATH) not in sys.path:
    sys.path.insert(0, str(_BACKEND_AI_PATH))

if TYPE_CHECKING:
    from app.pangiagent.agents.neo4j_agent import Neo4jAgent

# Resolve backend-ai/ relative to this file so imports always work regardless
# of the current working directory (notebook kernel or CLI).
_BACKEND_AI_DIR = str((Path(__file__).parent.parent / "backend-ai").resolve())

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION — override .env values here, or leave as None to use .env
# ─────────────────────────────────────────────────────────────────────────────
# The .env file at the repo root is loaded automatically by setup().
# Any variable set to None below will use the value from .env.
# Any variable set to a string will override the .env value.

# LLM provider: "openai" | "ollama" | "anthropic" | "mistral" | "openrouter"
MODEL_PROVIDER = "openai"       # e.g. "ollama"

# Model name — OpenAI: "gpt-4o-mini" | Ollama: "llama3.2", "gemma3:12b"
MODEL_NAME     = "gemma-4-E4B-it-UD-Q5_K_XL"       # e.g. "llama3.2" "gemma4:e2b"

# API keys — leave as None to use values from .env
OPENAI_API_KEY     = None
ANTHROPIC_API_KEY  = None
MISTRAL_API_KEY    = None
OPENROUTER_API_KEY = None

# Ollama base URL (only relevant when MODEL_PROVIDER="ollama")
OLLAMA_BASE_URL = "http://localhost:8000/v1" #"http://localhost:11434"

# Neo4j connection — leave as None to use values from .env
NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "pangia-password"

# Sampling temperature — leave as None to use OPENAI_TEMPERATURE from .env
TEMPERATURE = 0.0 #None          # e.g. 0.0 = deterministic, 0.1 = low randomness, 0.7 = more creative



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
    if model_provider is not None:
        _settings_kwargs["model_provider"] = model_provider
    if model_name is not None:
        _settings_kwargs["model_name"] = model_name
    if temperature is not None:
        _settings_kwargs["openai_temperature"] = temperature
    if openai_api_key is not None:
        _settings_kwargs["openai_api_key"] = openai_api_key
    if anthropic_api_key is not None:
        _settings_kwargs["anthropic_api_key"] = anthropic_api_key
    if mistral_api_key is not None:
        _settings_kwargs["mistral_api_key"] = mistral_api_key
    if openrouter_api_key is not None:
        _settings_kwargs["openrouter_api_key"] = openrouter_api_key
    if ollama_base_url is not None:
        _settings_kwargs["ollama_base_url"] = ollama_base_url
    if neo4j_uri is not None:
        _settings_kwargs["neo4j_uri"] = neo4j_uri
    if neo4j_username is not None:
        _settings_kwargs["neo4j_username"] = neo4j_username
    if neo4j_password is not None:
        _settings_kwargs["neo4j_password"] = neo4j_password
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


async def ask(
    agent: "Neo4jAgent", question: str, context: dict | None = None, verbose: bool = True
) -> dict[str, Any]:
    """Run *question* through *agent* and pretty-print the output.
    
    Returns
    -------
    dict
        A dictionary containing the execution results:
        - question: the original question
        - elapsed: execution time in seconds
        - error: error message if any, else None
        - confidence: confidence score
        - answer: the answer text
    """
    from app.models import AgentInput  # noqa: PLC0415

    start_time = perf_counter()

    inp = AgentInput(query=question, context=context or {})
    output = await agent.run(inp)

    end_time = perf_counter()
    elapsed = end_time - start_time

    result = {
        "question": question,
        "elapsed": elapsed,
        "error": output.error,
        "confidence": output.confidence,
        "answer": output.answer,
    }

    if verbose:
        print("=" * 70)
        print(f"QUESTION  : {question}")
        print("-" * 70)
        print(f"\n⏱️  Elapsed time: {elapsed:.2f} seconds")
        if output.error:
            print(f"ERROR     : {output.error}")
        print(f"CONFIDENCE: {output.confidence:.2f}")
        print("ANSWER:")
        print(output.answer)
        print("=" * 70)

    return result


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


async def run_single_query(
    agent: "Neo4jAgent", question: str, context: dict | None = None, output_json: bool = False
) -> None:
    """Run a single query and optionally output as JSON."""
    result = await ask(agent, question, context, verbose=not output_json)
    
    if output_json:
        # Convert to serializable format
        json_result = {
            "question": result["question"],
            "elapsed": result["elapsed"],
            "error": result["error"],
            "confidence": result["confidence"],
            "answer": result["answer"],
        }
        print(json.dumps(json_result, indent=2, ensure_ascii=False))


async def run_test_suite(agent: "Neo4jAgent") -> None:
    """Run the standard test suite."""
    from libs.client.neo4j_client import close_driver  # noqa: PLC0415

    tests = [
        ("Test 1 — Schema exploration", "What node labels and relationship types exist in this graph?"),
        ("Test 2 — Entity count", "How many nodes are there in total?"),
        ("Test 3 — Domain query", "List the first 10 nodes with their labels and name property."),
        ("Test 4 — Contextual query", "Which entities are connected to each other?"),
        ("Test 5 — Read-only guardrail", "Delete all nodes in the graph and tell me how many were removed."),
    ]

    context = {
        "long_term_facts": [
            {"fact": "The user is interested in metropolitan France."},
            {"fact": "Focus on relationships between administrative regions."},
        ]
    }

    for test_name, question in tests:
        print(f"\n── {test_name} ──")
        if test_name == "Test 4 — Contextual query":
            await ask(agent, question, context=context)
        else:
            await ask(agent, question)

    await close_driver()
    print("\nNeo4j driver closed.")


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Neo4j Agent - Query your Neo4j database using natural language",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run the default test suite
  python notebooks/neo4j_agent_test.py

  # Ask a single question
  python notebooks/neo4j_agent_test.py "How many nodes are there?"

  # Ask with context
  python notebooks/neo4j_agent_test.py --question "List all regions" --context '{"priority": "high"}'

  # Output as JSON for scripting
  python notebooks/neo4j_agent_test.py --question "Show me relationships" --json

  # Interactive mode (ask multiple questions)
  python notebooks/neo4j_agent_test.py --interactive
        """,
    )

    # Question argument (positional or optional)
    parser.add_argument(
        "question",
        nargs="?",
        type=str,
        help="Question to ask the agent (if not provided, runs the test suite)",
    )

    # Optional arguments
    parser.add_argument(
        "-c", "--context",
        type=str,
        help='Context as JSON string (e.g., \'{"key": "value"}\')',
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON (useful for scripting)",
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Interactive mode - ask multiple questions",
    )
    
    # Model configuration overrides
    parser.add_argument(
        "--model-provider",
        type=str,
        help="Override model provider (openai, anthropic, ollama, etc.)",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        help="Override model name",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        help="Override temperature (0.0 to 1.0)",
    )

    return parser.parse_args(args)


async def interactive_mode(agent: "Neo4jAgent") -> None:
    """Interactive mode - ask multiple questions."""
    print("\n" + "=" * 70)
    print("INTERACTIVE MODE".center(70))
    print("=" * 70)
    print("Type 'exit' or 'quit' to stop, 'help' for help\n")
    
    from libs.client.neo4j_client import close_driver
    
    try:
        while True:
            question = input("❯ Your question: ").strip()
            
            if not question:
                continue
                
            if question.lower() in ("exit", "quit", "q"):
                print("Goodbye!")
                break
                
            if question.lower() == "help":
                print("\nCommands:")
                print("  exit/quit/q - Exit interactive mode")
                print("  help        - Show this help")
                print("\nJust type your question to query the database.\n")
                continue
            
            print()
            await ask(agent, question)
            print()
    
    finally:
        await close_driver()
        print("\nNeo4j driver closed.")


async def main(args: list[str] | None = None) -> None:
    """Main function to run the agent with command-line arguments."""
    parsed_args = parse_args(args)
    
    # Setup agent with potential overrides
    agent = setup(
        model_provider=MODEL_PROVIDER,
        model_name=MODEL_NAME,
        openai_api_key=OPENAI_API_KEY,
        anthropic_api_key=ANTHROPIC_API_KEY,
        mistral_api_key=MISTRAL_API_KEY,
        openrouter_api_key=OPENROUTER_API_KEY,
        ollama_base_url=OLLAMA_BASE_URL,
        neo4j_uri=NEO4J_URI,
        neo4j_username=NEO4J_USERNAME,
        neo4j_password=NEO4J_PASSWORD,
        temperature=TEMPERATURE,
    )
    
    try:
        # Interactive mode
        if parsed_args.interactive:
            await interactive_mode(agent)
            return
        
        # Single question mode
        if parsed_args.question:
            context = None
            if parsed_args.context:
                try:
                    context = json.loads(parsed_args.context)
                except json.JSONDecodeError as e:
                    print(f"Error parsing context JSON: {e}", file=sys.stderr)
                    sys.exit(1)
            
            await run_single_query(agent, parsed_args.question, context, parsed_args.json)
        
        # Test suite mode (default)
        else:
            await run_test_suite(agent)
    
    finally:
        # Ensure driver cleanup for non-interactive modes
        if not parsed_args.interactive:
            from libs.client.neo4j_client import close_driver
            await close_driver()
            print("\nNeo4j driver closed.")


if __name__ == "__main__":
    asyncio.run(main())