"""
Master orchestrator agent (PangIA GeoIA).

Topology
--------
        ┌─────────────────────────────────────────────────────────────┐
        │                    master graph                             │
        │                                                             │
  entry ─► router ──[Send fan-out]──► neo4j_agent ───┐               │
        │          │                                   │               │
        │          ├──────────────► rdf_agent ─────────┤               │
        │          │                                   │               │
        │          ├──────────────► vector_agent ───────┤               │
        │          │                                   ▼               │
        │          └──────────────► postgis_agent ──► map_agent ──► merge ──► END
        └─────────────────────────────────────────────────────────────┘

The *router* decides which parallel sub-agents (neo4j, rdf, vector, postgis)
are relevant.  They run concurrently via LangGraph's Send API and each writes
results into `state["sub_results"]`.  After all parallel agents complete,
*map_agent* always runs and inspects the accumulated `sub_results` for
coordinate data; if coordinates are found it produces a GeoJSON FeatureCollection
in `state["geojson"]` (otherwise it exits immediately without calling the LLM).
The *merge* node synthesises all collected results into a final answer.

Only agents that are **enabled** in the application configuration are added to
the graph.  The user may narrow the parallel agents via `state["selected_agents"]`.
"""
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.types import Send
from pydantic import BaseModel

from app.agent.map_agent import run as map_run
from app.agent.neo4j_agent import run as neo4j_run
from app.agent.postgis_agent import run as postgis_run
from app.agent.rdf_agent import run as rdf_run
from app.agent.state import AgentState
from app.agent.vector_agent import run as vector_run
from app.config import get_settings

# ─── Agent metadata ────────────────────────────────────────────────────────────

AGENT_LABELS = {
    "neo4j": "Neo4j Knowledge Graph",
    "rdf": "RDF / SPARQL (GraphDB)",
    "vector": "Vector Search (Chroma)",
    "postgis": "PostGIS Spatial SQL",
    "map": "Map Agent (GeoJSON)",
}

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
    "    → neo4j."
)

# LangGraph node name → run function for each parallel sub-agent.
# map_agent is intentionally excluded: it always runs sequentially AFTER these
# agents so it can read their sub_results for coordinate data.
_AGENT_NODES: dict[str, tuple[str, Any]] = {
    "neo4j": ("neo4j_agent", neo4j_run),
    "rdf": ("rdf_agent", rdf_run),
    "vector": ("vector_agent", vector_run),
    "postgis": ("postgis_agent", postgis_run),
}

MERGE_SYSTEM = """You are the synthesis module of the PangIA GeoIA platform.
You will receive the original user question and the individual answers from one or
more specialised sub-agents (Neo4j, RDF/SPARQL, Vector, PostGIS).

Your job:
1. Merge the sub-agent answers into a single, coherent, well-structured response.
2. Remove redundancy; reconcile any contradictions by noting them clearly.
3. Cite the source agent(s) when referencing specific facts.
4. Use plain, accessible language appropriate for a geographic information system.
5. Whenever a geographic location, site, or place is mentioned, **always include
   its coordinates (latitude, longitude)** if they were provided by any sub-agent.
6. If geographic coordinates were found, inform the user that an interactive map
   has been generated and is displayed below the response.
"""


# ─── Active-agent helpers ──────────────────────────────────────────────────────

def get_active_agents() -> list[str]:
    """Return the list of agent keys that are enabled in configuration.

    Parallel sub-agents: neo4j, rdf, vector, postgis.
    map is handled as a sequential post-processing step and NOT routed to by the
    router; it is gated by MAP_AGENT_ENABLED separately.
    """
    settings = get_settings()
    flags: dict[str, bool] = {
        "neo4j": settings.neo4j_agent_enabled,
        "rdf": settings.rdf_agent_enabled,
        "vector": settings.vector_agent_enabled,
        "postgis": settings.postgis_agent_enabled,
    }
    active = [name for name, enabled in flags.items() if enabled]
    # Guard: always keep at least one agent to avoid an empty graph
    return active if active else ["neo4j"]


def is_map_enabled() -> bool:
    return get_settings().map_agent_enabled


def _build_router_system(available_agents: list[str]) -> str:
    """Build the router system prompt restricted to *available_agents*."""
    agent_list = "\n".join(_AGENT_DESCRIPTIONS[a] for a in available_agents)
    agent_names = ", ".join(f'"{a}"' for a in available_agents)
    return (
        "You are the master orchestrator of the PangIA GeoIA platform.\n"
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
    agents: list[Literal["neo4j", "rdf", "vector", "postgis"]]
    reasoning: str


# ─── Helper ───────────────────────────────────────────────────────────────────

def _build_llm(streaming: bool = False) -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.openai_model,
        temperature=settings.openai_temperature,
        api_key=settings.openai_api_key,
        streaming=streaming,
    )


def _last_human_message(state: AgentState) -> str:
    return next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )


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

    llm = _build_llm().with_structured_output(RoutingDecision)
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
    }


async def merge_node(state: AgentState) -> dict:
    """Synthesise sub-agent results into a final answer."""
    llm = _build_llm(streaming=True)
    query = _last_human_message(state)

    sub_results: dict[str, str] = state.get("sub_results", {})
    # Filter out empty / whitespace-only results (e.g. map agent produced nothing)
    non_empty = {k: v for k, v in sub_results.items() if v and v.strip()}
    if not non_empty:
        return {"messages": [AIMessage(content="No sub-agent results were produced.")]}

    # Build a structured context block for the synthesiser
    context_parts = []
    for agent_key, result in non_empty.items():
        label = AGENT_LABELS.get(agent_key, agent_key)
        context_parts.append(f"### {label}\n{result}")
    context = "\n\n".join(context_parts)

    synthesis_prompt = (
        f"User question:\n{query}\n\n"
        f"Sub-agent answers:\n\n{context}\n\n"
        "Please synthesise a complete, well-structured answer."
    )

    response: AIMessage = await llm.ainvoke(
        [SystemMessage(content=MERGE_SYSTEM), HumanMessage(content=synthesis_prompt)]
    )
    return {"messages": [response]}


# ─── Routing edge ─────────────────────────────────────────────────────────────

def dispatch_agents(state: AgentState):
    """Fan out to selected parallel sub-agents using LangGraph's Send API."""
    agents = state.get("agents_to_call", [])
    if not agents:
        # No parallel agents – go straight to the map post-processing step
        return "map_agent"
    return [Send(f"{a}_agent", state) for a in agents]


# ─── Graph construction ───────────────────────────────────────────────────────

def build_graph():
    """Build and compile the master LangGraph workflow.

    Parallel sub-agents (neo4j, rdf, vector, postgis) fan out from the router.
    After ALL parallel agents complete (LangGraph barrier), the map_agent node
    runs sequentially to extract GeoJSON from their sub_results.  Finally, the
    merge node synthesises a conversational answer.

    If MAP_AGENT_ENABLED is False the parallel agents route directly to merge.
    """
    active = get_active_agents()
    map_enabled = is_map_enabled()

    workflow = StateGraph(AgentState)

    # Core nodes (always present)
    workflow.add_node("router", router_node)
    workflow.add_node("merge", merge_node)

    # Determine the node that parallel agents converge on
    convergence_node = "map_agent" if map_enabled else "merge"

    # Parallel sub-agent nodes – only for enabled agents
    active_node_names: list[str] = []
    for agent_key in active:
        node_name, run_fn = _AGENT_NODES[agent_key]
        workflow.add_node(node_name, run_fn)
        workflow.add_edge(node_name, convergence_node)
        active_node_names.append(node_name)

    # Sequential map post-processing node (always after parallel agents)
    if map_enabled:
        workflow.add_node("map_agent", map_run)
        workflow.add_edge("map_agent", "merge")

    # Router → fan-out edge
    workflow.set_entry_point("router")
    workflow.add_conditional_edges(
        "router",
        dispatch_agents,
        active_node_names + [convergence_node],
    )
    workflow.add_edge("merge", END)

    return workflow.compile()


# Module-level compiled graph reused across requests
agent_graph = build_graph()
