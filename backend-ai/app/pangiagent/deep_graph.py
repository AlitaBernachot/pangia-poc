# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Deep-agent orchestrator for PangIA — powered by langchain deepagents.

This module replaces the previous home-made LangGraph fan-out/merge
orchestrator (``orchestrator_agent.py``) with the ``deepagents`` library from
https://github.com/langchain-ai/deepagents.

Architecture
------------

    Main deep agent (create_deep_agent)
        ├── model:         configured LLM (via model_config.build_llm)
        ├── system_prompt: PangIA geospatial orchestrator instructions
        └── subagents (CompiledSubAgent):
            ├── rag_agent
            ├── calculator_agent
            ├── summary_agent
            ├── neo4j_agent
            ├── postgis_agent
            ├── rdf_agent
            ├── vector_chroma_agent
            ├── datagouv_mcp_agent
            └── geonetwork_mcp_agent

Each connector agent is wrapped as a ``CompiledSubAgent`` — a messages-
compatible LangGraph subgraph — so that the main agent's built-in ``task``
tool can delegate to it and receive the answer as a ``ToolMessage``.

Existing agent guardrails (pre/post), prompt-loading from ``config/prompts/``,
and choice-based HITL (``request_choice``) are all preserved because the
agents' ``run()`` method is called unchanged inside the wrapper subgraph.

Home-made components superseded by this module
-----------------------------------------------
- ``orchestrator_agent.py``      → ``create_deep_agent()``
- ``router.py`` (DynamicRouter)  → deepagents ``task`` tool routing
- ``smart_dispatcher_agent.py``  → deepagents LLM-based routing
- Per-agent ``_react_loop``      → deepagents' built-in tool-calling loop
- ``OrchestratorState``          → ``AgentState`` (messages-based)
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, TYPE_CHECKING

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from deepagents import CompiledSubAgent, create_deep_agent

from app.pangiagent.model_config import build_llm, get_agent_model_config

if TYPE_CHECKING:
    from app.pangiagent.agents.base_agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


# ── Messages-compatible state for subagent wrappers ───────────────────────────

class _SubAgentState(TypedDict):
    """Minimal state schema satisfying deepagents' CompiledSubAgent requirement.

    deepagents requires the runnable passed to ``CompiledSubAgent`` to have a
    state schema that includes a ``messages`` key.  This TypedDict provides
    exactly that, with the standard ``add_messages`` reducer.
    """

    messages: Annotated[list, add_messages]


# ── Subagent capability descriptions ──────────────────────────────────────────
# Used by the main agent to decide which subagent to call via the ``task`` tool.

_AGENT_DESCRIPTIONS: dict[str, str] = {
    "rag_agent": (
        "Retrieval-Augmented Generation: retrieves relevant documents from a "
        "ChromaDB vector store and generates an accurate answer grounded in "
        "those documents."
    ),
    "calculator_agent": (
        "Evaluates arithmetic expressions (addition, subtraction, "
        "multiplication, division, powers). Use for any numerical calculation."
    ),
    "summary_agent": (
        "Summarisation: rewrites the query with an explicit summarisation "
        "instruction and answers concisely in two to three sentences."
    ),
    "neo4j_agent": (
        "Knowledge graph queries: generates and executes Cypher queries against "
        "a Neo4j graph database to answer questions about geographic entities "
        "and their relationships."
    ),
    "postgis_agent": (
        "Spatial SQL queries: generates and executes PostGIS SQL "
        "(ST_Contains, ST_Distance, ST_Intersects, …) to answer geographic and "
        "spatial analysis questions against a live PostGIS database."
    ),
    "rdf_agent": (
        "RDF/Linked Data queries: generates and executes SPARQL SELECT queries "
        "against a GraphDB triplestore to answer questions about semantically "
        "modelled geographic and thematic data."
    ),
    "vector_chroma_agent": (
        "Semantic vector search: retrieves and synthesises answers from a "
        "ChromaDB collection using embedding-based similarity search."
    ),
    "datagouv_mcp_agent": (
        "French open-data catalogue: searches, retrieves, and displays datasets "
        "from data.gouv.fr via MCP — including tabular data and GeoJSON layers."
    ),
    "geonetwork_mcp_agent": (
        "GeoNetwork metadata catalogue: finds and describes geospatial datasets "
        "and services from a GeoNetwork instance using ISO 19115/19139 metadata."
    ),
}


# ── Orchestrator system prompt ─────────────────────────────────────────────────

_ORCHESTRATOR_SYSTEM_PROMPT = """\
You are PangIA — an intelligent geospatial platform assistant.

You have access to multiple specialized sub-agents that can query different \
geospatial data sources. Use the `task` tool to delegate to the most \
appropriate sub-agent(s) based on the user's question.

## Available sub-agents

- **neo4j_agent**: Query a Neo4j knowledge graph about geographic entities \
and their relationships.
- **postgis_agent**: Execute spatial SQL queries (PostGIS) for geographic \
analysis (distances, intersections, etc.).
- **rdf_agent**: Query a semantic RDF triplestore using SPARQL for linked \
geospatial data.
- **vector_chroma_agent**: Semantic similarity search over a ChromaDB vector \
store of geospatial documents.
- **rag_agent**: Retrieve and synthesise answers from a document store using \
RAG (Retrieval-Augmented Generation).
- **datagouv_mcp_agent**: Search and retrieve French government open data from \
data.gouv.fr, including tabular data and GeoJSON layers.
- **geonetwork_mcp_agent**: Find geospatial datasets and services in a \
GeoNetwork metadata catalogue (ISO 19115/19139).
- **calculator_agent**: Evaluate arithmetic expressions and numerical \
calculations.
- **summary_agent**: Produce a concise summary and direct answer to a question.

## Guidelines

1. **Analyse the query** and identify the most relevant data source(s).
2. **Delegate to sub-agents** using `task` with clear, specific instructions.
3. For graph / ontology questions use **neo4j_agent** or **rdf_agent**.
4. For spatial / geographic queries use **postgis_agent**.
5. For French open-data discovery use **datagouv_mcp_agent**.
6. For GIS metadata catalogue queries use **geonetwork_mcp_agent**.
7. For document / knowledge-base search use **rag_agent** or \
**vector_chroma_agent**.
8. For calculations use **calculator_agent**.
9. **Synthesise results** from all sub-agents into a coherent, user-friendly \
final answer.
10. **Answer in the same language as the question** (French if asked in French).
"""


# ── Subgraph factory ───────────────────────────────────────────────────────────

def _wrap_agent(agent: "BaseAgent") -> Any:
    """Compile a messages-compatible LangGraph subgraph from a ``BaseAgent``.

    The wrapper:
    - extracts the last ``HumanMessage`` from *messages* as the query;
    - reads ``session_id`` from that message's ``additional_kwargs`` (injected
      by the chat route handler);
    - calls ``agent.run()`` which runs pre-guardrails → ``_run()`` →
      post-guardrails;
    - returns the agent's answer as an ``AIMessage``.

    Parameters
    ----------
    agent:
        Any ``BaseAgent`` subclass instance (guardrails already configured).

    Returns
    -------
    CompiledStateGraph
        Single-node graph whose state schema includes ``messages``, ready to
        be passed as ``CompiledSubAgent(runnable=...)``.
    """
    from app.models import AgentInput

    _agent = agent

    async def _run_node(state: _SubAgentState) -> dict:
        messages = state["messages"]
        query: str = ""
        session_id: str = "default"
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage) and msg.content:
                query = str(msg.content)
                session_id = (msg.additional_kwargs or {}).get(
                    "session_id", "default"
                )
                break

        inp = AgentInput(
            query=query,
            session_id=session_id,
            # NOTE: context (long-term memory facts, short-term memory, parsed intent)
            # is not populated here because memory_node / intent_node no longer run as
            # graph nodes in the deepagents architecture.  Memory integration via
            # deepagents middleware is planned as a follow-up improvement.
            context={},
        )
        output = await _agent.run(inp)
        content = (
            output.answer
            or (f"[Error] {output.error}" if output.error else "No result produced.")
        )
        return {"messages": [AIMessage(content=content)]}

    workflow: StateGraph = StateGraph(_SubAgentState)
    workflow.add_node("run", _run_node)
    workflow.set_entry_point("run")
    workflow.add_edge("run", END)
    return workflow.compile()


# ── Graph builder ──────────────────────────────────────────────────────────────

def build_deep_graph():
    """Build and return the deepagents-based orchestrator graph.

    Each domain connector agent is wrapped as a ``CompiledSubAgent``.  The
    main orchestrator is assembled with ``create_deep_agent`` from the
    ``deepagents`` library, which provides:

    - planning and task breakdown (``write_todos``);
    - sub-agent delegation via the ``task`` tool (replaces custom routing);
    - context summarisation when conversations grow long.

    The following home-made components are superseded:

    - ``build_graph()`` / ``orchestrator_agent.py`` → ``create_deep_agent()``
    - ``DynamicRouter`` / ``SmartDispatcherAgent`` → ``task`` tool routing
    - ``BaseReActAgent._react_loop`` → deepagents built-in tool-calling loop

    Returns
    -------
    CompiledStateGraph
        The compiled deep-agent orchestrator graph, ready for use in the API.
    """
    from app.pangiagent.agents.calculator_agent import CalculatorAgent
    from app.pangiagent.agents.datagouv_mcp_agent import DataGouvMCPAgent
    from app.pangiagent.agents.geonetwork_mcp_agent import GeoNetworkMCPAgent
    from app.pangiagent.agents.neo4j_agent import Neo4jAgent
    from app.pangiagent.agents.postgis_agent import PostGISAgent
    from app.pangiagent.agents.rag_agent import RAGAgent
    from app.pangiagent.agents.rdf_agent import RDFAgent
    from app.pangiagent.agents.summary_agent import SummaryAgent
    from app.pangiagent.agents.vector_chroma_agent import VectorChromaAgent
    from app.pangiagent.guardrails import (
        check_ambiguous_intent,
        check_output_length,
        check_toxic_input,
    )

    # Instantiate agents with the same guardrail configuration as before.
    agent_instances: dict[str, BaseAgent] = {
        "rag_agent": RAGAgent(
            pre_guardrails=[check_toxic_input, check_ambiguous_intent],
            post_guardrails=[check_output_length],
        ),
        "calculator_agent": CalculatorAgent(
            pre_guardrails=[check_toxic_input],
        ),
        "summary_agent": SummaryAgent(
            pre_guardrails=[check_toxic_input, check_ambiguous_intent],
            post_guardrails=[check_output_length],
        ),
        "neo4j_agent": Neo4jAgent(
            pre_guardrails=[check_toxic_input, check_ambiguous_intent],
            post_guardrails=[check_output_length],
        ),
        "postgis_agent": PostGISAgent(
            pre_guardrails=[check_toxic_input, check_ambiguous_intent],
            post_guardrails=[check_output_length],
        ),
        "rdf_agent": RDFAgent(
            pre_guardrails=[check_toxic_input, check_ambiguous_intent],
            post_guardrails=[check_output_length],
        ),
        "vector_chroma_agent": VectorChromaAgent(
            pre_guardrails=[check_toxic_input, check_ambiguous_intent],
            post_guardrails=[check_output_length],
        ),
        "datagouv_mcp_agent": DataGouvMCPAgent(
            pre_guardrails=[check_toxic_input],
            post_guardrails=[check_output_length],
        ),
        "geonetwork_mcp_agent": GeoNetworkMCPAgent(
            pre_guardrails=[check_toxic_input],
            post_guardrails=[check_output_length],
        ),
    }

    # Build CompiledSubAgent specs — each wraps the agent's run() in a
    # messages-compatible LangGraph subgraph so that deepagents' `task` tool
    # can delegate to it and receive the answer as a ToolMessage.
    subagents: list[CompiledSubAgent] = [
        CompiledSubAgent(
            name=name,
            description=_AGENT_DESCRIPTIONS.get(
                name,
                f"Agent for {name.replace('_', ' ')}.",
            ),
            runnable=_wrap_agent(agent),
        )
        for name, agent in agent_instances.items()
    ]

    model = build_llm(get_agent_model_config("orchestrator"))

    graph = create_deep_agent(
        model=model,
        system_prompt=_ORCHESTRATOR_SYSTEM_PROMPT,
        subagents=subagents,
    )

    logger.info(
        "Deep agent orchestrator compiled | subagents: %s",
        ", ".join(s["name"] for s in subagents),
    )

    return graph
