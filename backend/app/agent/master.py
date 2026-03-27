"""
Master orchestrator agent (PangIA GeoIA).

Topology
--------
        ┌──────────────────────────────────────────────┐
        │                  master graph                │
        │                                              │
  entry ─► router ──[Send fan-out]──► neo4j_agent ──┐  │
        │          │                                  │  │
        │          ├──────────────► rdf_agent ────────┤  │
        │          │                                  │  │
        │          ├──────────────► vector_agent ─────┤  │
        │          │                                  │  │
        │          └──────────────► postgis_agent ────┘  │
        │                               │               │
        │                            merge ──► END       │
        └──────────────────────────────────────────────┘

The *router* node uses an LLM with structured output to decide which subset of
the four sub-agents is relevant for a given query.  Sub-agents run
(conceptually in parallel via LangGraph's Send API) and each writes its result
into `state["sub_results"][agent_name]`.  The *merge* node synthesises all
collected results into a final conversational answer.

Only agents that are **enabled** in the application configuration are added to
the graph and eligible for routing.  The user may further narrow the set via
`state["selected_agents"]`.
"""
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.types import Send
from pydantic import BaseModel

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
}

_AGENT_DESCRIPTIONS = {
    "neo4j": (
        "  • neo4j   – Knowledge Graph (Cypher queries against Neo4j).\n"
        "               Best for: entity relationships, graph traversals, structured facts,\n"
        "               fossil site discovery (\"which sites yielded fossils of X\",\n"
        "               \"where were X fossils found\"), predator/prey chains, co-existence\n"
        "               between species, species locations, migrations."
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
        "               area calculations, coordinate transformations."
    ),
}

_EXTRA_ROUTING_RULES = (
    "  - Questions about which sites found/yielded/contain fossils of a species → neo4j.\n"
    "  - Questions about species relationships (predator, prey, coexists) → neo4j."
)

# LangGraph node name → run function for each sub-agent
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
"""


# ─── Active-agent helpers ──────────────────────────────────────────────────────

def get_active_agents() -> list[str]:
    """Return the list of agent keys that are enabled in configuration.

    The master orchestrator is always active.  Sub-agents can be disabled
    individually via ``NEO4J_AGENT_ENABLED``, ``RDF_AGENT_ENABLED``,
    ``VECTOR_AGENT_ENABLED``, and ``POSTGIS_AGENT_ENABLED`` environment
    variables (all default to ``true``).
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
        available = [a for a in active if a in user_selected]
        if not available:
            # User selected only disabled agents → fall back to all active
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
    }


async def merge_node(state: AgentState) -> dict:
    """Synthesise sub-agent results into a final answer."""
    llm = _build_llm(streaming=True)
    query = _last_human_message(state)

    sub_results: dict[str, str] = state.get("sub_results", {})
    if not sub_results:
        return {"messages": [AIMessage(content="No sub-agent results were produced.")]}

    # Build a structured context block for the synthesiser
    context_parts = []
    for agent_key, result in sub_results.items():
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
    """Fan out to selected sub-agents using LangGraph's Send API."""
    agents = state.get("agents_to_call", [])
    if not agents:
        return "merge"
    return [Send(f"{a}_agent", state) for a in agents]


# ─── Graph construction ───────────────────────────────────────────────────────

def build_graph():
    """Build and compile the master LangGraph workflow.

    Only agents that are currently **enabled** in the configuration are added
    as nodes.  The conditional edge map is restricted to those nodes so
    LangGraph is aware of all reachable targets.
    """
    active = get_active_agents()

    workflow = StateGraph(AgentState)

    # Core nodes (always present)
    workflow.add_node("router", router_node)
    workflow.add_node("merge", merge_node)

    # Sub-agent nodes – only for enabled agents
    active_node_names: list[str] = []
    for agent_key in active:
        node_name, run_fn = _AGENT_NODES[agent_key]
        workflow.add_node(node_name, run_fn)
        workflow.add_edge(node_name, "merge")
        active_node_names.append(node_name)

    # Edges
    workflow.set_entry_point("router")
    workflow.add_conditional_edges(
        "router",
        dispatch_agents,
        active_node_names + ["merge"],
    )
    workflow.add_edge("merge", END)

    return workflow.compile()


# Module-level compiled graph reused across requests
agent_graph = build_graph()

