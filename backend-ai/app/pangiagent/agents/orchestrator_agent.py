# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""
Orchestrator graph (PangIA V2).

Topology
--------

    __start__
        │
        ▼
    memory_node          ← loads LTM + STM, injects into context
        │
        ▼
    ambiguity_node       ← LLM scores ambiguity; sets hitl_* if score ≥ threshold
        │
        ├──[pending]──► hitl_wait_node  ← creates HITL request, awaits response
        │                   │
        │            [timeout]──► __end__  (final_answer = timeout message)
        │            [resolved]──► router_node
        │
        └──[clear]──► router_node       ← LLM routing → agents_to_call
                          │
                    [Send fan-out]
                    │           │
               rag_agent   calculator_agent   …   (compiled subgraphs)
                    │           │
                    └─────┬─────┘
                          ▼
                     merge_node   ← collects sub_results → final_answer
                          │
                       __end__

Each sub-agent (rag_agent, calculator_agent, …) is a compiled LangGraph
subgraph built by ``BaseAgent.as_subgraph()``.  Mermaid diagrams for the orchestrator
and every sub-agent subgraph are written to
``app/pangiagent/mermaid_graph/*.mmd`` at module import time.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from app.pangiagent.audit import get_audit
from app.config import get_settings
from app.pangiagent.hitl import get_hitl_manager
from app.pangiagent.memory import LongTermMemory, ShortTermMemory
from app.models import AgentInput, HITLRequest
from app.pangiagent.router import DynamicRouter
from app.pangiagent.state import OrchestratorState
from app.pangiagent.agents.ambiguity_agent import AmbiguityAgent
from app.pangiagent.agents.title_agent import TitleAgent
from app.pangiagent.agents.intent_parser_agent import IntentParserAgent

if TYPE_CHECKING:
    from app.pangiagent.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_HITL_TIMEOUT_MSG = "Request timed out waiting for clarification."
_NO_AGENT_ANSWER_MSG = "No agents produced a valid answer."

# ── Mermaid output directory ───────────────────────────────────────────────────
# Resolves to backend-ai/app/pangiagent/mermaid_graph/
_MERMAID_DIR = Path(__file__).parent.parent / "mermaid_graph"
_MERMAID_DIR.mkdir(exist_ok=True)

# ── Module-level agent registry (populated by build_graph) ────────────────────
# These are referenced by router_node and _dispatch_agents at request time.
_AGENT_REGISTRY: dict[str, Any] = {}
_AGENT_NODE_NAMES: set[str] = set()


# ── Orchestrator node functions ────────────────────────────────────────────────

async def memory_node(state: OrchestratorState) -> dict:
    """Load long-term and short-term memory; inject facts into context."""
    ltm = LongTermMemory()
    stm = ShortTermMemory(state["session_id"])

    try:
        facts = await ltm.search(state["query"], top_k=5)
    except Exception:
        logger.exception("LTM search failed")
        facts = []

    stm_data = await stm.load()

    audit = get_audit()
    await audit.log(
        state["session_id"],
        "memory_access",
        {"long_term_facts": len(facts), "short_term_keys": list(stm_data.keys())},
    )
    return {"context": {"long_term_facts": facts, "short_term": stm_data}}


async def title_node(state: OrchestratorState) -> dict:
    """Generate a short session title from the user's first query.

    Only runs on the first turn of a session (when ``session_title`` is still
    empty).  On subsequent turns the existing title is preserved.
    """
    if state.get("session_title"):
        return {}
    agent = TitleAgent()
    title = await agent.generate(state["query"])
    return {"session_title": title}


async def ambiguity_node(state: OrchestratorState) -> dict:
    """LLM ambiguity detection.

    Sets ``hitl_request_id``, ``hitl_questions``, and ``hitl_status``
    when the ambiguity score exceeds the configured threshold; otherwise
    clears those fields.
    """
    detector = AmbiguityAgent()
    score, questions = await detector.detect(state["query"])
    settings = get_settings()
    audit = get_audit()

    if score >= settings.hitl_ambiguity_threshold and questions:
        request_id = str(uuid.uuid4())
        await audit.log(
            state["session_id"],
            "hitl_ambiguity_detected",
            {"score": score, "request_id": request_id},
        )
        # Register the future BEFORE returning so it exists when the SSE
        # fires to the frontend.  If the user responds before hitl_wait_node
        # runs, respond() will find the future and resolve it immediately.
        hitl_manager = get_hitl_manager()
        await hitl_manager.create_request(
            HITLRequest(
                request_id=request_id,
                session_id=state["session_id"],
                original_query=state["query"],
                context=state.get("context", {}),  # type: ignore[arg-type]
                clarifying_questions=questions,
            )
        )
        return {
            "hitl_request_id": request_id,
            "hitl_questions": questions,
            "hitl_status": "pending",
        }
    return {"hitl_status": "", "hitl_request_id": "", "hitl_questions": []}


async def hitl_wait_node(state: OrchestratorState) -> dict:
    """Wait for the human's clarification response.

    The future was already registered by ``ambiguity_node`` before the
    ``hitl_request`` SSE fired, so this node only needs to await it.
    """
    hitl_manager = get_hitl_manager()
    clarified = await hitl_manager.wait_for_response(state["hitl_request_id"])
    audit = get_audit()

    if clarified:
        await audit.log(
            state["session_id"],
            "hitl_response_received",
            {"clarified_query": clarified},
        )
        return {"query": clarified, "hitl_status": "resolved"}

    await audit.log(
        state["session_id"],
        "hitl_timeout",
        {"request_id": state["hitl_request_id"]},
    )
    return {
        "hitl_status": "timeout",
        "final_answer": _HITL_TIMEOUT_MSG,
        "confidence": 0.0,
    }


async def router_node(state: OrchestratorState) -> dict:
    """Route the query to one or more agents.

    When ``settings.smart_dispatcher_enabled`` is ``True`` (default), uses
    :class:`SmartDispatcherAgent` — a deterministic + semantic scorer that
    requires no LLM call.  When ``False``, falls back to the LLM-based
    :class:`DynamicRouter`.
    """
    settings = get_settings()
    audit = get_audit()

    if settings.smart_dispatcher_enabled:
        from app.pangiagent.agents.smart_dispatcher_agent import SmartDispatcherAgent

        dispatcher = SmartDispatcherAgent()
        user_selected: list[str] = state.get("selected_sources") or []
        active = (
            [k for k in _AGENT_REGISTRY if k in user_selected]
            if user_selected
            else list(_AGENT_REGISTRY.keys())
        )
        inp = AgentInput(
            query=state["query"],
            session_id=state["session_id"],
            context={"active_agents": active},
        )
        output = await dispatcher._run(inp)
        agents_to_call: list[str] = output.state.get("agents_to_call", [])
        reasoning = f"SmartDispatcher selected: {agents_to_call}"

        await audit.log(
            state["session_id"],
            "routing",
            {"mode": "smart_dispatcher", "agents_to_call": agents_to_call},
        )
    else:
        router = DynamicRouter(_AGENT_REGISTRY)
        plan = await router.plan(state["query"])
        await audit.log(state["session_id"], "routing", {"plan": plan.model_dump()})
        agents_to_call = [s.agent_name for s in plan.steps if s.agent_name in _AGENT_NODE_NAMES]
        reasoning = plan.reasoning

    # Keep only agents whose nodes were compiled into the graph
    valid = [a for a in agents_to_call if a in _AGENT_NODE_NAMES]
    if not valid:
        # Deterministic fallback: use the lexicographically first registered agent
        valid = sorted(_AGENT_NODE_NAMES)[:1]

    return {
        "agents_to_call": valid,
        "execution_reasoning": reasoning,
    }


async def merge_node(state: OrchestratorState) -> dict:
    """Merge parallel sub-agent results into a single final answer.

    Produces a raw ``final_answer`` (``[agent]: …`` concatenation) used as
    internal context by ``synthesis_node``.  The synthesis agent then rewrites
    it into a clean user-facing response.  When no synthesis agent is wired,
    ``final_answer`` is surfaced directly.
    """
    sub_results: dict[str, Any] = state.get("sub_results") or {}
    successful = [
        (name, r)
        for name, r in sub_results.items()
        if not r.get("error")
    ]
    combined = (
        "\n\n".join(f"[{name}]: {r['answer']}" for name, r in successful)
        if successful
        else _NO_AGENT_ANSWER_MSG
    )
    avg_confidence = (
        sum(r["confidence"] for _, r in successful) / len(successful)
        if successful
        else 0.0
    )

    # Persist to short-term memory; log and swallow errors to avoid blocking
    stm = ShortTermMemory(state["session_id"])

    async def _save_stm() -> None:
        try:
            await stm.update("last_answer", combined[:2000])
            await stm.update("last_query", state["query"])
        except Exception:
            logger.exception("merge_node: failed to save short-term memory")

    asyncio.create_task(_save_stm())

    audit = get_audit()
    await audit.log(
        state["session_id"],
        "request_end",
        {"answer_length": len(combined), "confidence": avg_confidence},
    )

    return {"final_answer": combined, "confidence": avg_confidence}


# ── Routing / conditional-edge helpers ────────────────────────────────────────

def _hitl_decision(state: OrchestratorState) -> str:
    return "hitl_wait_node" if state.get("hitl_status") == "pending" else "router_node"


def _hitl_after_wait(state: OrchestratorState) -> str:
    return END if state.get("hitl_status") == "timeout" else "router_node"


def _dispatch_agents(state: OrchestratorState):
    """Fan-out to selected agents via LangGraph's Send API."""
    agents = [a for a in (state.get("agents_to_call") or []) if a in _AGENT_NODE_NAMES]
    if not agents:
        return "merge_node"
    # Pass only the keys SubAgentState needs — avoids InvalidUpdateError when
    # multiple agents run in parallel and LangGraph merges their outputs back
    # into OrchestratorState (plain keys like `query` can only be written once
    # per step without a reducer).
    subgraph_input = {
        "query": state["query"],
        "session_id": state["session_id"],
        "context": state.get("context", {}),
        "sub_results": {},
    }
    return [Send(a, subgraph_input) for a in agents]


def _after_humanoutput(state: OrchestratorState) -> str:
    """Route after humanoutput_node based on output_decision."""
    decision = state.get("output_decision") or {}
    if decision.get("needs_dataviz"):
        return "dataviz_node"
    # Skip mapviz_node if a real GeoJSON or OGC layer was already provided
    # by a sub-agent (e.g. datagouv_mcp_agent fetched a .geojson or WFS service).
    if decision.get("needs_map") and not state.get("geojson") and not state.get("ogc_layers"):
        return "mapviz_node"
    return END


def _after_dataviz(state: OrchestratorState) -> str:
    """Route after dataviz_node: run mapviz if needed and no real GeoJSON or OGC layer exists, else end."""
    decision = state.get("output_decision") or {}
    return "mapviz_node" if decision.get("needs_map") and not state.get("geojson") and not state.get("ogc_layers") else END


# ── Mermaid helper ─────────────────────────────────────────────────────────────

def _write_mermaid(graph, filename: str) -> None:
    path = _MERMAID_DIR / filename
    try:
        mermaid_text = graph.get_graph(xray=True).draw_mermaid()
        path.write_text(mermaid_text, encoding="utf-8")
        logger.info("Mermaid diagram written → %s", path)
    except Exception:
        logger.exception("Failed to write Mermaid diagram for %s", filename)


# ── Graph construction ─────────────────────────────────────────────────────────

def build_graph(
    agents: "dict[str, BaseAgent]",
    output_agents: "dict[str, BaseAgent] | None" = None,
    synthesis_agent: "BaseAgent | None" = None,
    intent_agent: "BaseAgent | None" = None,
):
    """Build and compile the orchestrator StateGraph.

    For each agent in *agents*:
      1. A sub-agent subgraph (single ``execute_node``) is compiled and added
         as a node in the orchestrator graph.
      2. A Mermaid diagram ``app/pangiagent/mermaid_graph/<agent>_graph.mmd``
         is written.

    When *output_agents* is provided (keys: ``"humanoutput_agent"``,
    ``"dataviz_agent"``, ``"mapviz_agent"``), three sequential post-processing
    nodes are added **after** ``merge_node``.

    When *synthesis_agent* is provided, a ``synthesis_node`` is appended as the
    **very last node** before END.  It synthesises all sub-agent results into a
    single concise user-facing answer, replacing the raw ``[agent]: …`` text.

    .. code-block:: text

        merge_node
            → humanoutput_node
                → dataviz_node  (if needs_dataviz)
                    → mapviz_node?  → synthesis_node → END
                → mapviz_node?  → synthesis_node → END
                → synthesis_node → END

    The orchestrator Mermaid diagram is written to
    ``app/pangiagent/mermaid_graph/orchestrator_graph.mmd``.

    Parameters
    ----------
    agents:
        Registry of ``BaseAgent`` instances keyed by agent node name.
    output_agents:
        Optional registry of post-processing agents
        (``humanoutput_agent``, ``dataviz_agent``, ``mapviz_agent``).
    synthesis_agent:
        Optional agent that synthesises all results into the final user-facing
        answer (``SynthesisAgent``).  When provided it becomes the last node.
    intent_agent:
        Optional agent that parses the user query into structured intent
        (``IntentParserAgent``).  When provided, an ``intent_node`` is inserted
        between ``title_node`` and ``ambiguity_node`` and the parsed intent is
        merged into ``state["context"]["intent"]`` for downstream agents.
        Defaults to a fresh ``IntentParserAgent`` when *None* is passed so that
        intent parsing is always active; pass a pre-configured instance to
        inject custom guardrails or a different model.

    Returns
    -------
    CompiledStateGraph
        The compiled orchestrator graph.
    """
    global _AGENT_REGISTRY, _AGENT_NODE_NAMES
    _AGENT_REGISTRY = agents
    _AGENT_NODE_NAMES.clear()

    workflow = StateGraph(OrchestratorState)

    # ── Core orchestration nodes ───────────────────────────────────────────
    workflow.add_node("memory_node", memory_node)
    workflow.add_node("title_node", title_node)
    workflow.add_node("ambiguity_node", ambiguity_node)
    workflow.add_node("hitl_wait_node", hitl_wait_node)
    workflow.add_node("router_node", router_node)
    workflow.add_node("merge_node", merge_node)

    # ── Intent node (optional, between title and ambiguity) ───────────────
    _effective_intent_agent: BaseAgent = intent_agent or IntentParserAgent()
    workflow.add_node("intent_node", _effective_intent_agent.make_node())

    # ── Synthesis node (final step, optional) ─────────────────────────────
    _end_target = END
    if synthesis_agent is not None:
        workflow.add_node("synthesis_node", synthesis_agent.make_node())
        workflow.add_edge("synthesis_node", END)
        _end_target = "synthesis_node"

    # ── Sub-agent subgraphs ────────────────────────────────────────────────
    subgraphs: dict[str, Any] = {}
    for agent_name, agent in agents.items():
        subgraph = agent.as_subgraph()
        workflow.add_node(agent_name, subgraph)
        workflow.add_edge(agent_name, "merge_node")
        subgraphs[agent_name] = subgraph
        _AGENT_NODE_NAMES.add(agent_name)

    # ── Sequential backbone ────────────────────────────────────────────────
    workflow.set_entry_point("memory_node")
    workflow.add_edge("memory_node", "title_node")
    workflow.add_edge("title_node", "intent_node")
    workflow.add_edge("intent_node", "ambiguity_node")

    workflow.add_conditional_edges(
        "ambiguity_node",
        _hitl_decision,
        {"hitl_wait_node": "hitl_wait_node", "router_node": "router_node"},
    )
    workflow.add_conditional_edges(
        "hitl_wait_node",
        _hitl_after_wait,
        {"router_node": "router_node", END: END},
    )

    fan_out_targets = list(_AGENT_NODE_NAMES) + ["merge_node"]
    workflow.add_conditional_edges("router_node", _dispatch_agents, fan_out_targets)

    # ── Post-processing phase (optional) ──────────────────────────────────
    if output_agents:
        humanoutput = output_agents.get("humanoutput_agent")
        dataviz = output_agents.get("dataviz_agent")
        mapviz = output_agents.get("mapviz_agent")

        if humanoutput:
            workflow.add_node("humanoutput_node", humanoutput.make_node())
            workflow.add_edge("merge_node", "humanoutput_node")

            after_humanoutput_targets: dict[str, str] = {END: _end_target}
            if dataviz:
                workflow.add_node("dataviz_node", dataviz.make_node())
                after_humanoutput_targets["dataviz_node"] = "dataviz_node"
            if mapviz:
                workflow.add_node("mapviz_node", mapviz.make_node())
                after_humanoutput_targets["mapviz_node"] = "mapviz_node"

            workflow.add_conditional_edges(
                "humanoutput_node",
                _after_humanoutput,
                after_humanoutput_targets,
            )

            if dataviz:
                after_dataviz_targets: dict[str, str] = {END: _end_target}
                if mapviz:
                    after_dataviz_targets["mapviz_node"] = "mapviz_node"
                workflow.add_conditional_edges(
                    "dataviz_node",
                    _after_dataviz,
                    after_dataviz_targets,
                )

            if mapviz:
                workflow.add_edge("mapviz_node", _end_target)
        else:
            workflow.add_edge("merge_node", _end_target)
    else:
        workflow.add_edge("merge_node", _end_target)

    orchestrator_graph = workflow.compile()

    # ── Write Mermaid diagrams at startup ──────────────────────────────────
    _write_mermaid(orchestrator_graph, "orchestrator_graph.mmd")
    for agent_name, subgraph in subgraphs.items():
        _write_mermaid(subgraph, f"{agent_name}_graph.mmd")

    logger.info(
        "Orchestrator graph compiled | agents: %s | output_agents: %s | synthesis: %s",
        ", ".join(agents.keys()),
        ", ".join((output_agents or {}).keys()),
        synthesis_agent.name if synthesis_agent else "none",
    )

    return orchestrator_graph
