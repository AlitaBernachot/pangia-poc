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
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from langchain_core.messages import HumanMessage, SystemMessage

from app.models import AgentInput, AgentOutput, AgentSource
from app.pangiagent.agents.base_agents.base_agent import BaseAgent
from app.pangiagent.model_config import build_llm, get_agent_model_config

if TYPE_CHECKING:
    from app.pangiagent.state import OrchestratorState

logger = logging.getLogger(__name__)


def _format_sources_footer(sources: list[AgentSource]) -> str:
    """Format a list of :class:`~app.models.AgentSource` into a Markdown footer.

    Produces two sections when both kinds are present:
    - **Source(s) :** — dataset catalogue links
    - **Téléchargement :** — downloadable resource links

    Returns an empty string when *sources* is empty.
    """
    datasets = [s for s in sources if s.kind == "dataset"]
    resources = [s for s in sources if s.kind == "resource"]
    others = [s for s in sources if s.kind == "other"]

    parts: list[str] = []
    if datasets:
        lines = "\n".join(
            f"- [{s.title}]({s.url})" if s.url else f"- {s.title}"
            for s in datasets
        )
        parts.append(f"**Source(s) :**\n{lines}")
    if resources or others:
        items = resources + others
        lines = "\n".join(
            f"- [{s.format or s.title}]({s.url})" if s.url else f"- {s.format or s.title}"
            for s in items
        )
        parts.append(f"**Téléchargement :**\n{lines}")
    return "\n\n".join(parts)


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
3. Only mention a chart or table ("les données sont affichées dans le tableau ci-dessus")
   if `[CONTEXT]` **explicitly** states that a data visualisation is displayed.
   If `[CONTEXT]` does not mention a chart/table, do **not** refer to one — even if the
   agent results contain numbers, statistics, or dataset listings.
4. Only mention a map ("les éléments sont localisés sur la carte ci-dessus")
   if `[CONTEXT]` **explicitly** states that a map layer is displayed.
5. **When `[CONTEXT]` mentions a visualisation (table, chart) or a map**, do **not**
   list individual items (locations, names, records…) in your text response — they are
   already visible in the UI component above. Simply state the total count and refer to
   the visual: e.g. "Les 74 parkings sont affichés dans le tableau et localisés sur la
   carte ci-dessus." One or two sentences maximum.
6. Do **not** include source or download links in your response — they are appended
   automatically after your text.
7. If you cannot determine a meaningful answer from the agent results, say so clearly.
8. Answer in the **same language as the user's question**.
9. Be concise: 1–4 sentences for factual answers. **When the answer is a list of items
   with no visual component present, include ALL items — never truncate or summarise
   a list by showing only a subset.**
10. Use Markdown for emphasis (bold, italic, lists) when it improves readability.
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
        if inp.context.get("has_ogc_layers"):
            context_notes.append("A map layer (WFS/WMS service) is displayed above the text.")

        user_content = (
            f"[QUERY]\n{inp.query}\n\n"
            f"[AGENT RESULTS]\n{raw_results}\n"
        )
        if context_notes:
            user_content += "\n[CONTEXT]\n" + "\n".join(context_notes) + "\n"

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
            sub_results: dict[str, Any] = state.get("sub_results") or {}

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

            # Collect structured sources from all sub-agent outputs
            all_sources: list[AgentSource] = []
            seen_urls: set[str] = set()
            seen_titles: set[str] = set()
            for kind_filter in ("dataset", "resource", "other"):
                for r in sub_results.values():
                    if not isinstance(r, dict):
                        continue
                    for s in r.get("sources") or []:
                        if not isinstance(s, dict) or s.get("kind") != kind_filter:
                            continue
                        url = s.get("url", "")
                        title = s.get("title", "")
                        if url and url in seen_urls:
                            continue
                        if not url and title in seen_titles:
                            continue
                        if url:
                            seen_urls.add(url)
                        seen_titles.add(title)
                        all_sources.append(AgentSource(**s))
            footer = _format_sources_footer(all_sources)

            inp = AgentInput(
                query=state["query"],
                session_id=state["session_id"],
                context={
                    "raw_results": raw_results,
                    "has_dataviz": bool(state.get("dataviz")),
                    "has_geojson": bool(state.get("geojson")),
                    "has_ogc_layers": bool(state.get("ogc_layers")),
                },
            )

            has_dataviz = bool(state.get("dataviz"))
            has_geojson = bool(state.get("geojson"))
            has_ogc_layers = bool(state.get("ogc_layers"))

            # ── Discovery / listing bypass ────────────────────────────────
            # When there is no structured output (no dataviz, no geojson, no ogc),
            # the sub-agent answer is already the final answer.
            if not has_dataviz and not has_geojson and not has_ogc_layers and successful:
                import re as _re
                # Strip "[agent_name]: " prefixes produced by the merge step
                clean = raw_results
                for name, _ in successful:
                    clean = _re.sub(rf"^\[{_re.escape(name)}\]:\s*", "", clean, flags=_re.MULTILINE)
                clean = clean.strip()
                if footer:
                    clean = clean.rstrip("\n") + "\n\n" + footer
                return {"final_answer": clean}

            try:
                output = await agent.run(inp)
                synthesised = output.answer
                if footer:
                    synthesised = synthesised.rstrip("\n") + "\n\n" + footer
            except Exception:
                logger.exception("synthesis_node: agent raised, falling back to raw results")
                synthesised = state.get("final_answer", "")

            return {"final_answer": synthesised}

        return synthesis_node
