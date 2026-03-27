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
"""
from typing import Literal

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

# ─── Prompts ──────────────────────────────────────────────────────────────────

ROUTER_SYSTEM = """You are the master orchestrator of the PangIA GeoIA platform.
Your role is to analyse a user's geographic question and decide which specialised
sub-agents should be invoked to answer it.

Available sub-agents:
  • neo4j   – Knowledge Graph (Cypher queries against Neo4j).
              Best for: entity relationships, graph traversals, structured facts,
              fossil site discovery ("which sites yielded fossils of X",
              "where were X fossils found"), predator/prey chains, co-existence
              between species, species locations, migrations.
  • rdf     – RDF/SPARQL (SPARQL queries against GraphDB).
              Best for: ontologies, linked data, semantic relationships, GeoSPARQL.
  • vector  – Semantic search (embedding similarity via ChromaDB).
              Best for: free-text similarity, document retrieval, concept proximity,
              general descriptive questions ("tell me about X").
  • postgis – Spatial SQL (PostGIS queries against PostgreSQL).
              Best for: geometric computations, spatial intersections, distances,
              area calculations, coordinate transformations.

Rules:
  - Select the minimum set of agents needed to answer the question well.
  - Questions about which sites found/yielded/contain fossils of a species → neo4j.
  - Questions about species relationships (predator, prey, coexists) → neo4j.
  - A question about semantic similarity alone needs only "vector".
  - A question about spatial distance needs only "postgis".
  - A complex question might legitimately need several agents.
  - Always include at least one agent.
"""

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

AGENT_LABELS = {
    "neo4j": "Neo4j Knowledge Graph",
    "rdf": "RDF / SPARQL (GraphDB)",
    "vector": "Vector Search (Chroma)",
    "postgis": "PostGIS Spatial SQL",
}


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
    """Analyse the query and decide which sub-agents to invoke."""
    llm = _build_llm().with_structured_output(RoutingDecision)
    query = _last_human_message(state)
    decision: RoutingDecision = llm.invoke(
        [SystemMessage(content=ROUTER_SYSTEM), HumanMessage(content=query)]
    )
    # Guard: ensure at least one agent is selected
    agents = decision.agents if decision.agents else ["neo4j"]
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
    workflow = StateGraph(AgentState)

    # Nodes
    workflow.add_node("router", router_node)
    workflow.add_node("neo4j_agent", neo4j_run)
    workflow.add_node("rdf_agent", rdf_run)
    workflow.add_node("vector_agent", vector_run)
    workflow.add_node("postgis_agent", postgis_run)
    workflow.add_node("merge", merge_node)

    # Edges
    workflow.set_entry_point("router")
    workflow.add_conditional_edges(
        "router",
        dispatch_agents,
        ["neo4j_agent", "rdf_agent", "vector_agent", "postgis_agent", "merge"],
    )
    workflow.add_edge("neo4j_agent", "merge")
    workflow.add_edge("rdf_agent", "merge")
    workflow.add_edge("vector_agent", "merge")
    workflow.add_edge("postgis_agent", "merge")
    workflow.add_edge("merge", END)

    return workflow.compile()


# Module-level compiled graph reused across requests
agent_graph = build_graph()
