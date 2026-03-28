#!/usr/bin/env python3
"""Generate a Mermaid workflow graph for the PangIA agent architecture.

Parses master.py with the stdlib ``ast`` module (no extra dependencies) to
extract the agent nodes and labels, then writes GRAPH.md in the same directory.

Usage::

    python backend/app/agent/generate_graph.py
"""
import ast
import pathlib

AGENT_DIR = pathlib.Path(__file__).parent
MASTER_PY = AGENT_DIR / "master.py"
OUTPUT_MD = AGENT_DIR / "GRAPH.md"


def _extract_dict(source: str, var_name: str) -> dict[str, str]:
    """Return a ``{key: value}`` dict extracted from a top-level assignment in *source*.

    Only handles dicts whose keys and values are plain string constants.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == var_name:
                if isinstance(node.value, ast.Dict):
                    result: dict[str, str] = {}
                    for k, v in zip(node.value.keys, node.value.values):
                        if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                            result[str(k.value)] = str(v.value)
                    return result
    return {}


def _extract_agent_nodes(source: str) -> dict[str, str]:
    """Extract ``_AGENT_NODES`` as ``{agent_key: node_name}`` from *source*.

    ``_AGENT_NODES`` is a dict mapping agent key → ``(node_name, run_fn)``.
    The variable uses a type annotation (``ast.AnnAssign``), so we handle
    both ``ast.Assign`` and ``ast.AnnAssign``.
    """
    tree = ast.parse(source)

    def _parse_dict(dict_node: ast.Dict) -> dict[str, str]:
        result: dict[str, str] = {}
        for k, v in zip(dict_node.keys, dict_node.values):
            if isinstance(k, ast.Constant) and isinstance(v, ast.Tuple):
                agent_key = str(k.value)
                # First element of the tuple is the node name string
                if v.elts and isinstance(v.elts[0], ast.Constant):
                    result[agent_key] = str(v.elts[0].value)
        return result

    for node in ast.walk(tree):
        # Handle: _AGENT_NODES: dict[...] = {...}
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "_AGENT_NODES":
                if isinstance(node.value, ast.Dict):
                    return _parse_dict(node.value)
        # Handle: _AGENT_NODES = {...}
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_AGENT_NODES":
                    if isinstance(node.value, ast.Dict):
                        return _parse_dict(node.value)
    return {}


def _build_mermaid(agent_nodes: dict[str, str], agent_labels: dict[str, str]) -> str:
    """Return a Mermaid ``graph TD`` diagram as a string."""
    lines: list[str] = ["graph TD"]

    # ── Fixed nodes ──────────────────────────────────────────────────────────
    lines += [
        "    __start__([\"<b>Start</b>\"])",
        "    router[\"🔀 <b>Router</b><br/>LLM routing decision\"]",
        "    post_process_router[\"⚙️ <b>post_process_router</b><br/>barrier — waits for all sub-agents\"]",
        "    map_agent[\"🗺️ <b>map_agent</b><br/>GeoJSON / interactive map\"]",
        "    dataviz_agent[\"📊 <b>dataviz_agent</b><br/>charts · KPIs · tables\"]",
        "    merge[\"🧠 <b>merge</b><br/>synthesis LLM — final answer\"]",
        "    __end__([\"<b>End</b>\"])",
        "",
    ]

    # ── Entry ─────────────────────────────────────────────────────────────────
    lines.append("    __start__ --> router")
    lines.append("")

    # ── Parallel sub-agents ───────────────────────────────────────────────────
    for agent_key, node_name in agent_nodes.items():
        label = agent_labels.get(agent_key, agent_key)
        lines.append(f'    {node_name}["{label}"]')

    lines.append("")

    for agent_key, node_name in agent_nodes.items():
        lines.append(f"    router -- Send --> {node_name}")

    lines.append("")

    for node_name in agent_nodes.values():
        lines.append(f"    {node_name} --> post_process_router")

    lines.append("")

    # ── Post-processing ───────────────────────────────────────────────────────
    lines += [
        "    post_process_router -- Send --> map_agent",
        "    post_process_router -- Send --> dataviz_agent",
        "    map_agent --> merge",
        "    dataviz_agent --> merge",
        "    merge --> __end__",
    ]

    return "\n".join(lines)


def _build_markdown(mermaid: str) -> str:
    return f"""\
# PangIA – Agent Workflow Graph

> This file is **auto-generated** at build time by
> [`generate_graph.py`](./generate_graph.py).  
> Re-generate locally with:
> ```
> python backend/app/agent/generate_graph.py
> ```

The diagram below maps the full LangGraph workflow executed by the PangIA
multi-agent backend for every user query.

```mermaid
{mermaid}
```

## Node descriptions

| Node | Role |
|---|---|
| **Router** | LLM with structured output — selects the minimal set of parallel sub-agents relevant to the query |
| **neo4j\\_agent** | Knowledge-graph queries (Cypher / Neo4j) |
| **rdf\\_agent** | Linked-data queries (SPARQL / GraphDB) |
| **vector\\_agent** | Semantic similarity search (ChromaDB embeddings) |
| **postgis\\_agent** | Spatial SQL queries (PostGIS / PostgreSQL) |
| **data\\_gouv\\_agent** | French government open-data (data.gouv.fr via MCP) |
| **post\\_process\\_router** | Barrier node — synchronises after all parallel agents complete, then fans out to post-processors |
| **map\\_agent** | Converts spatial data into a GeoJSON layer for the interactive map |
| **dataviz\\_agent** | Generates charts, KPI cards and tables from sub-agent results |
| **merge** | Synthesis LLM — combines all sub-agent answers into a single streamed response |

## Configuration

Each agent can be individually enabled or disabled via environment variables.
Disabled agents are excluded from the graph entirely.

| Variable | Default |
|---|---|
| `NEO4J_AGENT_ENABLED` | `true` |
| `RDF_AGENT_ENABLED` | `true` |
| `VECTOR_AGENT_ENABLED` | `true` |
| `POSTGIS_AGENT_ENABLED` | `true` |
| `DATA_GOUV_AGENT_ENABLED` | `true` |
| `MAP_AGENT_ENABLED` | `true` |
| `DATAVIZ_AGENT_ENABLED` | `true` |
"""


def main() -> None:
    source = MASTER_PY.read_text(encoding="utf-8")
    agent_nodes = _extract_agent_nodes(source)
    agent_labels = _extract_dict(source, "AGENT_LABELS")

    if not agent_nodes:
        print(
            "ERROR: could not parse _AGENT_NODES from master.py — "
            "check that the variable is defined as a top-level annotated or plain assignment.",
            flush=True,
        )
        raise SystemExit(1)

    mermaid = _build_mermaid(agent_nodes, agent_labels)
    markdown = _build_markdown(mermaid)

    OUTPUT_MD.write_text(markdown, encoding="utf-8")
    print(f"✅  Written {OUTPUT_MD.relative_to(AGENT_DIR.parent.parent.parent)}")
    print()
    print("--- Mermaid diagram ---")
    print(mermaid)


if __name__ == "__main__":
    main()
