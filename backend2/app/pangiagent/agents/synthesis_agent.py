# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Synthesis Agent — produces a concise, user-facing final answer.

This agent runs **after** all sub-agents and post-processing nodes
(humanoutput → dataviz → mapviz) have completed.  It reads:

- ``state["sub_results"]``  — raw answers from each sub-agent
- ``state["dataviz"]``      — structured charts/tables (if any)
- ``state["geojson"]``      — GeoJSON layer (if any)
- ``state["query"]``        — the original user question

and produces a single, clean, human-friendly response in Markdown.

Design notes
------------
- This agent is **not** registered in the fan-out AGENTS dict and does
  **not** inherit from `BaseAgent` as a sub-graph participant.  It is
  instantiated directly and called from a dedicated ``synthesis_node``
  that is the final node in the orchestrator graph.
- The raw ``[agent_name]: …`` concatenation produced by ``merge_node``
  is fed to the LLM as *internal context* only — it is never surfaced
  directly to the user.
- When a dataset-choice HITL panel is pending, the synthesis step is
  skipped so the UI stays clean.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine

import yaml
from langchain_core.messages import HumanMessage, SystemMessage

from app.models import AgentInput, AgentOutput
from app.pangiagent.agents.base_agent import BaseAgent
from app.pangiagent.model_config import build_llm, get_agent_model_config

if TYPE_CHECKING:
    from app.pangiagent.state import OrchestratorState

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = """\
You are the final synthesis layer of PangIA, a geospatial intelligence platform.

Your job is to produce a **concise, precise, human-friendly response** to the user's question,
based on the internal results provided by one or more specialist sub-agents.

## Input you receive

You will be given:
- `[QUERY]`: the original user question.
- `[AGENT RESULTS]`: the combined raw answers from one or more specialist agents.
  These are internal intermediate results — **do not copy them verbatim**.
- `[CONTEXT]`: optional metadata indicating whether a map view or data charts
  are being displayed alongside your text response.

## Rules

1. **Never** reproduce the raw `[agent_name]: …` format in your response.
2. **Never** list dataset column names or individual row values in detail — the UI
   renders tables and charts separately.
3. When structured data (CSV, table, chart) is available, mention it concisely
   ("les données sont affichées dans le tableau ci-dessus") without repeating values.
4. When a GeoJSON / map layer is available, mention it concisely
   ("les webcams sont localisées sur la carte ci-dessus").
5. Preserve any Markdown links `[text](url)` that appear in the agent results — copy them
   verbatim at the end of your response without altering the URL.
   If no links are present in the agent results, do **not** invent or mention download links.
6. If you cannot determine a meaningful answer from the agent results, say so clearly.
7. Answer in the **same language as the user's question**.
8. Be concise: 1–4 sentences is ideal. Expand only if the topic genuinely requires it.
9. Use Markdown for emphasis (bold, italic, lists) when it improves readability.
"""


class SynthesisAgent(BaseAgent):
    """LLM-backed agent that synthesises sub-agent results into a clean final answer.

    Note: this agent is **not** registered in the orchestrator fan-out; it is
    called directly inside ``synthesis_node``, which is the **last** node in
    the orchestrator graph (runs after humanoutput → dataviz → mapviz).
    """

    name = "synthesis_agent"
    _DEFAULT_PROMPT = _DEFAULT_PROMPT

    def __init__(self, **kwargs) -> None:
        super().__init__(name="synthesis_agent", **kwargs)
        self._system_prompt = self.get_prompt(self._DEFAULT_PROMPT)

    def get_capabilities(self) -> str:
        return (
            "Final synthesis: converts raw sub-agent outputs into a concise, "
            "user-friendly Markdown response."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        raw_results: str = inp.context.get("raw_results", "")
        has_dataviz: bool = bool(inp.context.get("has_dataviz"))
        has_geojson: bool = bool(inp.context.get("has_geojson"))

        context_notes: list[str] = []
        if has_dataviz:
            context_notes.append("A data visualisation (chart/table) is displayed above the text.")
        if has_geojson:
            context_notes.append("A map layer (GeoJSON) is displayed above the text.")

        user_content = (
            f"[QUERY]\n{inp.query}\n\n"
            f"[AGENT RESULTS]\n{raw_results}\n"
        )
        if context_notes:
            user_content += f"\n[CONTEXT]\n" + "\n".join(context_notes) + "\n"

        llm = build_llm(get_agent_model_config(self.name))
        response = await llm.ainvoke([
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=user_content),
        ])

        content = response.content
        text = content if isinstance(content, str) else " ".join(
            p.get("text", "") for p in content if isinstance(p, dict)
        )
        return AgentOutput(agent_name=self.name, answer=text.strip(), confidence=0.9)

    def make_node(self) -> Callable[[OrchestratorState], Coroutine[Any, Any, dict]]:
        """Return an async node function to be used as the final synthesis step."""
        agent = self

        async def synthesis_node(state: OrchestratorState) -> dict:
            # Build raw context from the merged sub-agent answers
            sub_results: dict[str, Any] = state.get("sub_results") or {}

            # Build raw context from the merged sub-agent answers
            successful = [
                (name, r)
                for name, r in sub_results.items()
                if isinstance(r, dict) and not r.get("error") and r.get("answer")
            ]
            raw_results = (
                "\n\n".join(f"[{name}]: {r['answer']}" for name, r in successful)
                if successful
                else ""
            )

            inp = AgentInput(
                query=state["query"],
                session_id=state["session_id"],
                context={
                    "raw_results": raw_results,
                    "has_dataviz": bool(state.get("dataviz")),
                    "has_geojson": bool(state.get("geojson")),
                },
            )
            try:
                output = await agent.run(inp)
                synthesised = output.answer
            except Exception:
                logger.exception("synthesis_node: agent raised, falling back to raw results")
                synthesised = state.get("final_answer", "")

            return {"final_answer": synthesised}

        return synthesis_node
