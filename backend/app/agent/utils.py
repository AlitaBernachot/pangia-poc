"""
Agent utility helpers.

This module exposes lightweight helpers that are used both by the orchestrator
and by external callers (API routes, smart dispatcher, …) without creating
circular imports.

Public API
----------
get_active_agents()   Return the list of agent keys enabled in configuration.
is_agent_enabled()    Check whether a single connector key is enabled.
get_agent_labels()    Return agent key → UI label mapping from agent_descriptions.yml.
"""
import logging
from pathlib import Path

import yaml

from app.agent.source.source_registry import SOURCE_REGISTRY, get_entry_by_connector
from app.config import get_settings

logger = logging.getLogger(__name__)

# Agents that MUST have a SourceEntry in source_registry.yml to be routable.
_REGISTRY_REQUIRED_AGENTS: frozenset[str] = frozenset({"neo4j", "rdf", "vector_chroma", "postgis"})

_AGENT_DESCRIPTIONS_YAML = Path(__file__).parents[2] / "config" / "agent_descriptions.yml"


def _load_agent_labels() -> dict[str, str]:
    with _AGENT_DESCRIPTIONS_YAML.open(encoding="utf-8") as f:
        raw: dict = yaml.safe_load(f)
    return {k: v["label"] for k, v in raw.items()}


_AGENT_LABELS: dict[str, str] = _load_agent_labels()


# ─── Public helpers ────────────────────────────────────────────────────────────

def get_agent_labels() -> dict[str, str]:
    """Return a mapping of agent key → UI label.

    Priority: label defined in source_registry.yml > label in agent_descriptions.yml.
    Falls back to the connector key itself when neither source defines a label.
    """
    labels = dict(_AGENT_LABELS)  # defaults from agent_descriptions.yml
    for entry in SOURCE_REGISTRY:
        if entry.label is not None:
            labels[entry.connector] = entry.label
    return labels


def is_agent_enabled(connector_key: str) -> bool:
    """Return whether the agent identified by *connector_key* is enabled in config.

    Looks up ``<connector_key>_agent_enabled`` on the Settings object.
    Defaults to ``True`` when no such flag exists (e.g. dynamically-registered
    MCP connectors that have not yet been given an explicit env variable).
    """
    return getattr(get_settings(), f"{connector_key}_agent_enabled", True)


def get_active_agents() -> list[str]:
    """Return the list of agent keys that are enabled in configuration.

    Parallel sub-agents: neo4j, rdf, vector_chroma, postgis.
    map and dataviz are handled as sequential post-processing steps and NOT
    routed to by the router; they are gated by MAPVIZ_AGENT_ENABLED and
    DATAVIZ_AGENT_ENABLED separately.
    Sub-agents can be disabled individually via environment variables:
    ``NEO4J_AGENT_ENABLED``, ``RDF_AGENT_ENABLED``,
    ``VECTOR_CHROMA_AGENT_ENABLED``, ``POSTGIS_AGENT_ENABLED``, and
    ``DATA_GOUV_AGENT_ENABLED`` (all default to ``true``).
    """
    settings = get_settings()
    flags: dict[str, bool] = {
        "neo4j": settings.neo4j_agent_enabled,
        "rdf": settings.rdf_agent_enabled,
        "vector_chroma": settings.vector_chroma_agent_enabled,
        "postgis": settings.postgis_agent_enabled,
        "data_gouv": settings.data_gouv_agent_enabled,
        "geo": settings.geo_agent_enabled,
    }

    # Database connectors require a SourceEntry in the registry to be routable.
    # If none is declared, the agent has no declared data and is disabled.
    for agent_key in _REGISTRY_REQUIRED_AGENTS:
        if flags.get(agent_key) and get_entry_by_connector(agent_key) is None:
            logger.warning(
                "Agent '%s' is enabled but has no SourceEntry in the Source Registry — disabling it.",
                agent_key,
            )
            flags[agent_key] = False

    # Dynamic connectors from Source Registry
    for entry in SOURCE_REGISTRY:
        if entry.connector not in flags:
            flags[entry.connector] = is_agent_enabled(entry.connector)

    active = [name for name, enabled in flags.items() if enabled]

    # Guard: always keep at least one agent to avoid an empty graph
    return active if active else ["neo4j"]
