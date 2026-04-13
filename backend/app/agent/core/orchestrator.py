"""
Orchestrator agent (PangIA GeoIA).

Topology
--------
        ┌──────────────────────────────────────────────────────────────────┐
        │                        orchestrator graph                              │
        │                                                                  │
  entry ─► router ──[Send fan-out]──► neo4j_agent ───┐                    │
        │          │                                   │                    │
        │          ├──────────────► rdf_agent ─────────┤                    │
        │          │                                   │                    │
        │          ├──────────────► vector_agent ───────┤                    │
        │          │                                   ▼                    │
        │          └──────────────► postgis_agent ──► post_process_router   │
        │                                                │                  │
        │                                         humanoutput_agent         │
        │                                        [decides map/dataviz]      │
        │                                        ┌────┴─────┐               │
        │                                    mapviz_agent  dataviz_agent        │
        │                                        └────┬─────┘               │
        │                                           merge ──► END            │
        └──────────────────────────────────────────────────────────────────┘

The *router* decides which parallel sub-agents (neo4j, rdf, vector, postgis)
are relevant.  They run concurrently via LangGraph's Send API and each writes
results into `state["sub_results"]`.  After all parallel agents complete,
*post_process_router* acts as a barrier then routes to *humanoutput_agent*
which inspects the data and decides whether to call *mapviz_agent*, *dataviz_agent*,
both, or neither.  Finally *merge* synthesises all results into a final answer.

Only agents that are **enabled** in the application configuration are added to
the graph.  The user may narrow the parallel agents via `state["selected_agents"]`.
"""
import logging
import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.types import Send
from pydantic import BaseModel

from app.agent.output.dataviz_agent import run as dataviz_run
from app.agent.core.humanoutput_agent import run as humanoutput_run
from app.agent.output.mapviz_agent import run as map_run
from app.agent.model_config import build_llm, get_agent_model_config
from app.agent.connectors.neo4j_agent import run as neo4j_run
from app.agent.connectors.postgis_agent import run as postgis_run
from app.agent.connectors.rdf_agent import run as rdf_run
from app.agent.connectors.data_gouv_agent import run as data_gouv_run
from app.agent.connectors.geonetwork_mcp_agent import make_run as _make_geonetworkmcp_run
from app.agent.core.geo_orchestrator import run as geo_run
from app.agent.core.intent_parser import run as intent_parser_run
from app.agent.core.smart_dispatcher import run as smart_dispatcher_run
from app.agent.core.state import AgentState
from app.agent.source.source_registry import SOURCE_REGISTRY, get_entry_by_connector
from app.agent.connectors.vector_agent import run as vector_run
from app.agent.output.synthesis_agent import AGENT_LABELS, merge_node, _last_human_message
from app.config import get_settings

logger = logging.getLogger(__name__)

_AGENT_DESCRIPTIONS = {
    "neo4j": (
        "  • neo4j   – Knowledge Graph (Cypher queries against Neo4j).\n"
        "               Best for: entity relationships, graph traversals, structured facts,\n"
        "               discovering entities and their associated locations or sites,\n"
        "               relationship chains, co-occurrence, migrations, hierarchies."
    ),
    "rdf": (
        "  • rdf     – RDF/SPARQL (SPARQL queries against GraphDB).\n"
        "               Best for: ontologies, linked data, semantic relationships, GeoSPARQL."
    ),
    "vector": (
        "  • vector  – Semantic search (embedding similarity via ChromaDB).\n"
        "               Best for: free-text similarity, document retrieval, concept proximity,\n"
        "               general descriptive questions (\"tell me about X\")."
    ),
    "postgis": (
        "  • postgis – Spatial SQL (PostGIS queries against PostgreSQL).\n"
        "               Best for: geometric computations, spatial intersections, distances,\n"
        "               area calculations, coordinate transformations,\n"
        "               and retrieving entities with their geographic coordinates\n"
        "               when precise location data is needed for mapping."
    ),
    "data_gouv": (
        "  • data_gouv – French government open-data (data.gouv.fr via MCP).\n"
        "               Best for: searching French official datasets, government statistics,\n"
        "               public-sector open data, administrative boundaries, environmental\n"
        "               records, and any question whose answer is likely in French open data."
    ),
    "geo": (
        "  • geo       – Advanced geospatial analysis (multi-sub-agent orchestrator).\n"
        "               Best for: geocoding addresses, computing distances, buffer zones,\n"
        "               isochrones (accessibility zones), proximity searches, spatial\n"
        "               intersections, area calculations, hotspot detection, route\n"
        "               optimisation, elevation profiles, geometry operations,\n"
        "               spatio-temporal analysis, and viewshed estimation."
    ),
}

# Theme-specific routing hints.
# When adding a new theme, review and update these rules so the router correctly
# combines agents for domain-specific questions (see README → “Adding a new theme”).
_EXTRA_ROUTING_RULES = (
    "  - Questions asking WHERE entities were found, discovered, or are located\n"
    "    → include BOTH neo4j (relationships) AND postgis (coordinates/geometry).\n"
    "  - Questions asking to show, map, or visualise locations\n"
    "    → include BOTH neo4j AND postgis so coordinates are available for the map.\n"
    "  - Questions about relationships between entities (links, chains, co-occurrence)\n"
    "    → neo4j.\n"
    "  - Questions about geocoding, distances, buffers, isochrones, proximity,\n"
    "    area calculation, hotspot detection, route optimisation, elevation,\n"
    "    geometry operations, spatio-temporal analysis, or viewshed estimation\n"
    "    → geo."
)

# LangGraph node name → run function for each parallel sub-agent.
# mapviz_agent is intentionally excluded: it always runs sequentially AFTER these
# agents so it can read their sub_results for coordinate data.
_AGENT_NODES: dict[str, tuple[str, Any]] = {
    "neo4j": ("neo4j_agent", neo4j_run),
    "rdf": ("rdf_agent", rdf_run),
    "vector": ("vector_agent", vector_run),
    "postgis": ("postgis_agent", postgis_run),
    "data_gouv": ("data_gouv_agent", data_gouv_run),
    "geo": ("geo_agent", geo_run),
}

_REGISTRY_REQUIRED_AGENTS = {"neo4j", "rdf", "vector", "postgis"}

# Dynamically register MCP connectors declared in the Source Registry.
# Each SourceEntry with a non-null mcp_url and a unique connector key gets its
# own agent node. The factory is selected based on the connector type prefix,
# making it easy to add new MCP connector families in the future.
for _entry in SOURCE_REGISTRY:
    if _entry.mcp_url is not None and _entry.connector not in _AGENT_NODES:
        if _entry.connector == "geonetworkmcp":
            _AGENT_NODES[_entry.connector] = (
                f"{_entry.connector}_agent",
                _make_geonetworkmcp_run(_entry.mcp_url, _entry.connector),
            )
        else:
            logger.warning(
                "Source Registry entry '%s' has mcp_url but no matching factory "
                "(connector='%s'). Skipping.",
                _entry.id,
                _entry.connector,
            )


# ─── Active-agent helpers ──────────────────────────────────────────────────────

def get_active_agents() -> list[str]:
    """Return the list of agent keys that are enabled in configuration.

    Parallel sub-agents: neo4j, rdf, vector, postgis.
    map and dataviz are handled as sequential post-processing steps and NOT
    routed to by the router; they are gated by MAPVIZ_AGENT_ENABLED and
    DATAVIZ_AGENT_ENABLED separately.
    The orchestrator is always active.  Sub-agents can be disabled
    individually via ``NEO4J_AGENT_ENABLED``, ``RDF_AGENT_ENABLED``,
    ``VECTOR_AGENT_ENABLED``, ``POSTGIS_AGENT_ENABLED``, and
    ``DATA_GOUV_AGENT_ENABLED`` environment variables (all default to
    ``true``).
    """
    settings = get_settings()
    flags: dict[str, bool] = {
        "neo4j": settings.neo4j_agent_enabled,
        "rdf": settings.rdf_agent_enabled,
        "vector": settings.vector_agent_enabled,
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
    for _entry in SOURCE_REGISTRY:
        if _entry.connector not in flags:
            flags[_entry.connector] = is_agent_enabled(_entry.connector)
    active = [name for name, enabled in flags.items() if enabled]
    
    # Guard: always keep at least one agent to avoid an empty graph
    return active if active else ["neo4j"]


def is_agent_enabled(connector_key: str) -> bool:
    """Return whether the agent identified by *connector_key* is enabled in config.

    Looks up ``<connector_key>_agent_enabled`` on the Settings object.
    Defaults to ``True`` when no such flag exists (e.g. dynamically-registered
    MCP connectors that have not yet been given an explicit env variable).
    """
    return getattr(get_settings(), f"{connector_key}_agent_enabled", True)


def is_map_enabled() -> bool:
    return get_settings().mapviz_agent_enabled


def is_dataviz_enabled() -> bool:
    return get_settings().dataviz_agent_enabled


def is_humanoutput_enabled() -> bool:
    return get_settings().humanoutput_agent_enabled


def is_intent_parser_enabled() -> bool:
    return get_settings().intent_parser_enabled


def is_smart_dispatcher_enabled() -> bool:
    return get_settings().smart_dispatcher_enabled


def _build_router_system(available_agents: list[str]) -> str:
    """Build the router system prompt restricted to *available_agents*."""
    desc_lines = []
    for a in available_agents:
        if a in _AGENT_DESCRIPTIONS:
            desc_lines.append(_AGENT_DESCRIPTIONS[a])
        else:
            entry = get_entry_by_connector(a)
            desc_lines.append(
                f"  • {a} – {entry.description}" if entry else f"  • {a} – specialist agent"
            )
    agent_list = "\n".join(desc_lines)
    agent_names = ", ".join(f'"{a}"' for a in available_agents)
    return (
        "You are the main orchestrator of the PangIA GeoIA platform.\n"
        "Your role is to analyse a user's geographic question and decide which specialised\n"
        "sub-agents should be invoked to answer it.\n\n"
        "Available sub-agents:\n"
        f"{agent_list}\n\n"
        "Rules:\n"
        "  - Select the minimum set of agents needed to answer the question well.\n"
        "  - Only select from the available agents listed above.\n"
        f"{_EXTRA_ROUTING_RULES}\n"
        "  - A question about semantic similarity alone needs only \"vector\".\n"
        "  - A question about spatial distance needs only \"postgis\".\n"
        "  - A complex question might legitimately need several agents.\n"
        "  - Always include at least one agent.\n"
        f"  - Only output agent names from: {agent_names}."
    )


# ─── Structured routing output ────────────────────────────────────────────────

class RoutingDecision(BaseModel):
    agents: list[str]
    reasoning: str


# ─── Helper ───────────────────────────────────────────────────────────────────


# ─── Nodes ────────────────────────────────────────────────────────────────────

def router_node(state: AgentState) -> dict:
    """Analyse the query and decide which sub-agents to invoke.

    The eligible agent pool is the intersection of:
    1. Agents enabled in the application configuration.
    2. Agents explicitly selected by the user (``state["selected_agents"]``);
       an empty list means "no preference – use all active agents".

    The LLM then picks the most relevant subset from that pool.
    """
    active = get_active_agents()

    # Respect user selection when provided and non-empty
    user_selected: list[str] = state.get("selected_agents", [])
    if user_selected:
        # Only keep parallel-routable agents (map is not in _AGENT_NODES)
        available = [a for a in active if a in user_selected and a in _AGENT_NODES]
        if not available:
            available = active
    else:
        available = active

    llm = build_llm(get_agent_model_config("router")).with_structured_output(RoutingDecision)
    query = _last_human_message(state)
    decision: RoutingDecision = llm.invoke(
        [SystemMessage(content=_build_router_system(available)), HumanMessage(content=query)]
    )

    # Filter to only agents in the available pool (LLM may stray)
    agents = [a for a in decision.agents if a in available]
    if not agents:
        agents = available[:1]

    return {
        "agents_to_call": agents,
        "sub_results": {},
        "geojson": None,
        "dataviz": None,
        "output_decision": None,
    }


# ─── Routing edges ────────────────────────────────────────────────────────────

def dispatch_agents(state: AgentState):
    """Fan out to selected parallel sub-agents using LangGraph's Send API."""
    agents = state.get("agents_to_call", [])
    if not agents:
        # No parallel agents – jump straight to post-processing (or merge)
        if is_map_enabled() or is_dataviz_enabled():
            return "post_process_router"
        return "merge"
    return [Send(f"{a}_agent", state) for a in agents]


def post_process_router_node(state: AgentState) -> dict:
    """Barrier node that collects all parallel sub-agent results.

    Returns an empty dict (no state mutation); LangGraph uses this node as a
    synchronisation point before fanning out to mapviz_agent and dataviz_agent
    in parallel.
    """
    return {}


def post_process_dispatch(state: AgentState):
    """Fan out to mapviz_agent and dataviz_agent in parallel via Send.

    Used only when humanoutput_agent is **disabled**.  Both agents read
    `sub_results` independently so they can safely run concurrently.  Each
    writes to a distinct state key (`geojson` / `dataviz`).
    """
    sends = []
    if is_map_enabled():
        sends.append(Send("mapviz_agent", state))
    if is_dataviz_enabled():
        sends.append(Send("dataviz_agent", state))
    if sends:
        return sends
    return "merge"


def humanoutput_dispatch(state: AgentState):
    """Fan out to mapviz_agent / dataviz_agent based on humanoutput_agent decision.

    Reads ``state["output_decision"]`` written by :func:`humanoutput_run` and
    dispatches via Send only to the agents that are both **enabled** and
    **requested** by the decision.  Falls back to dispatching both if the
    decision key is missing.
    """
    decision: dict = state.get("output_decision") or {}
    needs_map = decision.get("needs_map", True)
    needs_dataviz = decision.get("needs_dataviz", True)

    sends = []
    if is_map_enabled() and needs_map:
        sends.append(Send("mapviz_agent", state))
    if is_dataviz_enabled() and needs_dataviz:
        sends.append(Send("dataviz_agent", state))
    if sends:
        return sends
    return "merge"


# ─── Graph construction ───────────────────────────────────────────────────────

def build_graph():
    """Build and compile the orchestrator LangGraph workflow.

    Entry path (evaluated at startup based on config flags):

    ┌─ INTENT_PARSER_ENABLED + SMART_DISPATCHER_ENABLED (default) ─────────┐
    │  intent_parser → smart_dispatcher → [fan-out] → … → merge → END      │
    ├─ INTENT_PARSER_ENABLED only ─────────────────────────────────────────┤
    │  intent_parser → router → [fan-out] → … → merge → END                │
    └─ legacy (both disabled) ─────────────────────────────────────────────┘
       router → [fan-out] → … → merge → END

    Post-processing (after fan-out barrier):
      post_process_router → [humanoutput_agent?] → mapviz / dataviz → merge

    If MAPVIZ_AGENT_ENABLED is False, mapviz_agent is never added.
    If DATAVIZ_AGENT_ENABLED is False, dataviz_agent is never added.
    If HUMANOUTPUT_AGENT_ENABLED is False, the decision step is skipped.
    If both map and dataviz are disabled, the pipeline proceeds directly to merge.
    """
    active = get_active_agents()
    map_enabled = is_map_enabled()
    dataviz_enabled = is_dataviz_enabled()
    humanoutput_enabled = is_humanoutput_enabled()
    intent_parser_enabled = is_intent_parser_enabled()
    smart_dispatcher_enabled = is_smart_dispatcher_enabled()

    workflow = StateGraph(AgentState)

    # ── merge is always present ───────────────────────────────────────────
    workflow.add_node("merge", merge_node)

    # ── Post-processing layer ─────────────────────────────────────────────
    if map_enabled or dataviz_enabled:
        convergence_node = "post_process_router"
        workflow.add_node("post_process_router", post_process_router_node)

        post_process_targets: list[str] = []
        if map_enabled:
            workflow.add_node("mapviz_agent", map_run)
            workflow.add_edge("mapviz_agent", "merge")
            post_process_targets.append("mapviz_agent")
        if dataviz_enabled:
            workflow.add_node("dataviz_agent", dataviz_run)
            workflow.add_edge("dataviz_agent", "merge")
            post_process_targets.append("dataviz_agent")

        if humanoutput_enabled:
            workflow.add_node("humanoutput_agent", humanoutput_run)
            workflow.add_edge("post_process_router", "humanoutput_agent")
            workflow.add_conditional_edges(
                "humanoutput_agent",
                humanoutput_dispatch,
                post_process_targets + ["merge"],
            )
        else:
            workflow.add_conditional_edges(
                "post_process_router",
                post_process_dispatch,
                post_process_targets + ["merge"],
            )
    else:
        convergence_node = "merge"

    # ── Parallel data-source sub-agents ───────────────────────────────────
    active_node_names: list[str] = []
    for agent_key in active:
        node_name, run_fn = _AGENT_NODES[agent_key]
        workflow.add_node(node_name, run_fn)
        workflow.add_edge(node_name, convergence_node)
        active_node_names.append(node_name)

    fan_out_targets = active_node_names + [convergence_node, "merge"]

    # ── Entry path: intent_parser + smart_dispatcher / router ─────────────
    if smart_dispatcher_enabled:
        # smart_dispatcher produces agents_to_call and replaces router
        workflow.add_node("smart_dispatcher", smart_dispatcher_run)
        workflow.add_conditional_edges("smart_dispatcher", dispatch_agents, fan_out_targets)

        if intent_parser_enabled:
            workflow.add_node("intent_parser", intent_parser_run)
            workflow.add_edge("intent_parser", "smart_dispatcher")
            workflow.set_entry_point("intent_parser")
        else:
            workflow.set_entry_point("smart_dispatcher")

    else:
        # Legacy LLM-based router
        workflow.add_node("router", router_node)
        workflow.add_conditional_edges("router", dispatch_agents, fan_out_targets)

        if intent_parser_enabled:
            # intent_parser enriches state; router still makes the routing call
            workflow.add_node("intent_parser", intent_parser_run)
            workflow.add_edge("intent_parser", "router")
            workflow.set_entry_point("intent_parser")
        else:
            workflow.set_entry_point("router")

    workflow.add_edge("merge", END)

    return workflow.compile()


# Module-level compiled graph reused across requests
agent_graph = build_graph()


# ----------------------------------------
# Write the Mermaid diagram of the compiled graph to a file for documentation
# ----------------------------------------

_mermaid_dir = os.path.join(os.path.dirname(__file__), "..", "mermaid_graph")
os.makedirs(_mermaid_dir, exist_ok=True)
_mermaid_path = os.path.join(_mermaid_dir, "orchestrator_graph.mmd")
with open(_mermaid_path, "w", encoding="utf-8") as _f:
    _f.write(agent_graph.get_graph().draw_mermaid())

logger.info("Mermaid graph written to %s", _mermaid_path)
