# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

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
        │          ├──────────────► vector_chroma_agent ──┤                    │
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
from pathlib import Path
from typing import Any

import yaml

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
from app.agent.connectors.datagouv_mcp_agent import run as data_gouv_run
from app.agent.connectors.geonetwork_mcp_agent import make_run as _make_geonetworkmcp_run
from app.agent.core.geo_orchestrator import run as geo_run
from app.agent.core.intent_parser import run as intent_parser_run
from app.agent.core.smart_dispatcher import run as smart_dispatcher_run
from app.agent.core.state import AgentState
from app.agent.source.source_registry import SOURCE_REGISTRY, get_entry_by_connector
from app.agent.connectors.vector_chroma_agent import run as vector_run
from app.agent.output.synthesis_agent import AGENT_LABELS, merge_node, _last_human_message
from app.agent.utils import get_active_agents, get_agent_labels, is_agent_enabled
from app.config import get_settings

logger = logging.getLogger(__name__)

_AGENT_DESCRIPTIONS_YAML = Path(__file__).parents[3] / "config" / "agent_descriptions.yml"
_ORCHESTRATOR_CONFIG_YAML = Path(__file__).parents[3] / "config" / "orchestrator_config.yml"


def _load_agent_descriptions() -> dict[str, str]:
    """Return descriptions dict parsed from agent_descriptions.yml."""
    with _AGENT_DESCRIPTIONS_YAML.open(encoding="utf-8") as f:
        raw: dict = yaml.safe_load(f)
    return {k: v["description"] for k, v in raw.items()}


def _load_orchestrator_config() -> dict:
    with _ORCHESTRATOR_CONFIG_YAML.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


_AGENT_DESCRIPTIONS: dict[str, str] = _load_agent_descriptions()
_ORCHESTRATOR_CONFIG: dict = _load_orchestrator_config()

# Theme-specific routing rules are now in backend/config/orchestrator_config.yml.

# LangGraph node name → run function for each parallel sub-agent.
# mapviz_agent is intentionally excluded: it always runs sequentially AFTER these
# agents so it can read their sub_results for coordinate data.
_AGENT_NODES: dict[str, tuple[str, Any]] = {
    "neo4j": ("neo4j_agent", neo4j_run),
    "rdf": ("rdf_agent", rdf_run),
    "vector_chroma": ("vector_chroma_agent", vector_run),
    "postgis": ("postgis_agent", postgis_run),
    "data_gouv": ("datagouv_mcp_agent", data_gouv_run),
    "geo": ("geo_agent", geo_run),
}

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
        entry = get_entry_by_connector(a)
        if entry:
            desc_lines.append(f"  • {a} – {entry.description}")
        elif a in _AGENT_DESCRIPTIONS:
            desc_lines.append(f"  • {a} – {_AGENT_DESCRIPTIONS[a]}")
        else:
            desc_lines.append(f"  • {a} – specialist agent")
    agent_list = "\n".join(desc_lines)
    agent_names = ", ".join(f'"{a}"' for a in available_agents)

    cfg = _ORCHESTRATOR_CONFIG["router_system"]
    rules = "\n".join(f"  - {r}" for r in cfg["routing_rules"])
    rules += f'\n  - Only output agent names from: {agent_names}.'

    return (
        f"{cfg['intro']}\n\n"
        "Available sub-agents:\n"
        f"{agent_list}\n\n"
        "Rules:\n"
        f"{rules}"
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
    # Guard: only send to agents whose node was actually compiled into the graph.
    # If get_active_agents() at request time diverges from build time (e.g. after
    # a reload), sending to an unknown node produces a LangGraph warning and is
    # silently dropped — better to filter explicitly here.
    agents = [a for a in agents if a in _AGENT_NODES]
    if not agents:
        # No parallel agents – jump straight to post-processing (or merge)
        if is_map_enabled() or is_dataviz_enabled():
            return "post_process_router"
        return "merge"
    return [Send(_AGENT_NODES[a][0], state) for a in agents]


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

_active = get_active_agents()
print(
    "\n"
    "██████╗  █████╗ ███╗   ██╗ ██████╗ ██╗  █████╗ \n"
    "██╔══██╗██╔══██╗████╗  ██║██╔════╝ ██║ ██╔══██╗\n"
    "██████╔╝███████║██╔██╗ ██║██║  ███╗██║ ███████║\n"
    "██╔═══╝ ██╔══██║██║╚██╗██║██║   ██║██║ ██╔══██║\n"
    "██║     ██║  ██║██║ ╚████║╚██████╔╝██║ ██║  ██║\n"
    "╚═╝     ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝ ╚═╝  ╚═╝  — Geo-AI Platform\n"
    "\n"
    f"|  🌍 Orchestrator ready\n"
    f"|  Active agents : {', '.join(_active)}\n"
    "|\n"
    f"|  Config  →  {_AGENT_DESCRIPTIONS_YAML.parent}\n"
    "|    ↳ source_registry.yml       data-source connector declarations\n"
    "|    ↳ agent_descriptions.yml    router LLM agent descriptions\n"
    "|    ↳ orchestrator_config.yml   router prompt & routing rules\n"
)

# ----------------------------------------
# Write the Mermaid diagram of the compiled graph to a file for documentation
# ----------------------------------------

_mermaid_dir = os.path.join(os.path.dirname(__file__), "..", "mermaid_graph")
os.makedirs(_mermaid_dir, exist_ok=True)
_mermaid_path = os.path.join(_mermaid_dir, "orchestrator_graph.mmd")
with open(_mermaid_path, "w", encoding="utf-8") as _f:
    _f.write(agent_graph.get_graph().draw_mermaid())

logger.info("Mermaid graph written to %s", _mermaid_path)

# ----------------------------------------
# Log the router system prompt at startup for debugging (agents may vary based on config)
# ----------------------------------------

_active_agents_at_startup = _active
logger.debug(
    "Router system prompt (agents: %s):\n%s",
    _active_agents_at_startup,
    _build_router_system(_active_agents_at_startup),
)
