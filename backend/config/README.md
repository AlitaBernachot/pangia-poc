# `backend/config` — Runtime configuration files

This directory contains editable configuration files that are loaded at application startup. They can be modified without recompiling or restarting the Python environment (except where noted).

## Files

| File | Role |
|---|---|
| `source_registry.yml` | Declares all data-source connectors available to the agent pipeline |
| `agent_descriptions.yml` | Agent descriptions shown to the LLM in the legacy router prompt |
| `orchestrator_config.yml` | Router prompt preamble and routing rules (edited without touching Python) |

---

## `agent_descriptions.yml`

A YAML dict loaded by [`app/agent/core/orchestrator.py`](../app/agent/core/orchestrator.py) into `_AGENT_DESCRIPTIONS`.

Each key is an agent connector key (e.g. `neo4j`, `postgis`); the value is a free-text description shown to the LLM when it selects which agents to call. This is used by the **legacy LLM router** (`SMART_DISPATCHER_ENABLED=false`).

MCP connectors declared in `source_registry.yml` do **not** need an entry here — the orchestrator falls back to `SourceEntry.description`.

```yaml
my_agent: >-
  Short description of what it does.
  Best for: use-case A, use-case B.
```

---

## `source_registry.yml`

The **canonical list** of `SourceEntry` objects loaded by [`app/agent/source/source_registry.py`](../app/agent/source/source_registry.py).

Each entry describes one data-source connector: what it contains, its topics, capabilities, geographic scope, and example questions. This data is used by:

- The **Smart Dispatcher** — embedded into ChromaDB for semantic similarity routing.
- The **Orchestrator** — to dynamically register MCP-backed connectors (entries with `mcp_url` set).

### Adding a new connector

Append an entry to `source_registry.yml` and restart the application:

```yaml
- id: my-source           # unique identifier
  connector: my_source    # must match the agent key in orchestrator._AGENT_NODES
  description: >
    What this source contains.
  topics:
    - keyword1
  entity_types:
    - type1
  capabilities:
    - capability_tag
  geo_scope: null          # "france" | "global" | null
  mcp_url: null            # MCP endpoint URL, or null for non-MCP connectors
  example_questions:
    - "Example question?"
```

See [`app/agent/source/README.md`](../app/agent/source/README.md) for the full capability vocabulary and MCP connector documentation.

---

## `orchestrator_config.yml`

Loaded by [`app/agent/core/orchestrator.py`](../app/agent/core/orchestrator.py) into `_ORCHESTRATOR_CONFIG`.

Contains the router system prompt configuration:

| Key | Description |
|---|---|
| `router_system.intro` | Static preamble shown to the LLM before the agent list |
| `router_system.routing_rules` | List of rules shown after the agent list; edit to add theme-specific routing hints |

The constraint `Only output agent names from: …` is appended dynamically in Python.

**Adding a theme-specific routing rule** — append to `routing_rules`:

```yaml
routing_rules:
  # ... existing rules ...
  - >-
    Questions about my-domain-topic
    → my_agent.
```
