# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""SummaryAgent — demonstrates a custom multi-node subgraph.

Unlike the default single-node subgraph produced by ``make_subgraph()``,
``SummaryAgent.as_subgraph()`` compiles a two-node graph:

    enrich_node  →  execute_node  →  __end__

``enrich_node`` prepends an explicit summarisation instruction to the query
so that the LLM always produces a concise summary rather than a free-form
answer.  ``execute_node`` then calls ``agent.run()`` with the enriched state
and writes the result to ``sub_results``.

This pattern is the recommended starting point for agents that need to
transform or augment the incoming state before (or after) the main LLM call —
for example a RAG agent that would do retrieve → rerank → generate.
"""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.agents.base_agent import BaseAgent
from app.config import get_settings
from app.models import AgentInput, AgentOutput

logger = logging.getLogger(__name__)

_SUMMARISE_PREFIX = (
    "Please summarise the following question or passage in two to three "
    "concise sentences, then give a direct answer:\n\n"
)


class SummaryAgent(BaseAgent):
    """LLM-backed agent that always summarises before answering.

    Uses a custom two-node subgraph (``enrich_node`` → ``execute_node``)
    so that every query is rewritten with an explicit summarisation
    instruction before the LLM is invoked.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="summary_agent", **kwargs)
        settings = get_settings()
        self._llm = ChatOpenAI(
            model=settings.model_name,
            api_key=settings.openai_api_key,
            temperature=settings.openai_temperature,
        )

    # ------------------------------------------------------------------
    # BaseAgent contract
    # ------------------------------------------------------------------

    def get_capabilities(self) -> str:
        return (
            "Summarisation: rewrites the query with an explicit summarisation "
            "instruction, then answers concisely in two to three sentences."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        response = await self._llm.ainvoke([HumanMessage(content=inp.query)])
        return AgentOutput(
            agent_name=self.name,
            answer=str(response.content),
            confidence=0.80,
        )

    # ------------------------------------------------------------------
    # Custom subgraph: enrich_node → execute_node
    # ------------------------------------------------------------------

    def as_subgraph(self):
        """Return a two-node compiled LangGraph subgraph.

        Graph topology::

            __start__
                │
                ▼
            enrich_node   ← prepends summarisation instruction to query
                │
                ▼
            execute_node  ← calls agent.run(), writes sub_results
                │
             __end__

        Returns
        -------
        CompiledStateGraph
            Ready to be added as a node in the orchestrator StateGraph.
        """
        from langgraph.graph import END, StateGraph

        from app.models import AgentInput
        from app.state import SubAgentState

        agent = self  # capture for closures
        agent_name = self.name

        async def enrich_node(state: SubAgentState) -> dict:
            """Prepend summarisation instruction to the query."""
            enriched = _SUMMARISE_PREFIX + state["query"]
            return {"query": enriched}

        async def execute_node(state: SubAgentState) -> dict:
            """Call agent.run() with the enriched query, write sub_results."""
            inp = AgentInput(
                query=state["query"],
                session_id=state["session_id"],
                context=state.get("context", {}),  # type: ignore[arg-type]
            )
            output = await agent.run(inp)
            return {
                "sub_results": {
                    agent_name: {
                        "answer": output.answer,
                        "confidence": output.confidence,
                        "error": output.error,
                        "duration_ms": output.state.get("duration_ms", 0),
                        "violations": output.state.get("post_guardrail_violations", []),
                    }
                }
            }

        workflow = StateGraph(SubAgentState)
        workflow.add_node("enrich_node", enrich_node)
        workflow.add_node("execute_node", execute_node)

        workflow.set_entry_point("enrich_node")
        workflow.add_edge("enrich_node", "execute_node")
        workflow.add_edge("execute_node", END)

        return workflow.compile()
