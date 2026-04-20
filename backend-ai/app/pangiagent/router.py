# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage

from app.pangiagent.model_config import build_llm, get_agent_model_config
from app.models import ExecutionPlan, ExecutionStep

logger = logging.getLogger(__name__)


class DynamicRouter:
    def __init__(self, agents: dict[str, "BaseAgent"]) -> None:  # noqa: F821
        self._agents = agents
        self._llm = build_llm(get_agent_model_config("router"))

    async def plan(self, query: str) -> ExecutionPlan:
        capabilities = "\n".join(
            f"- {name}: {agent.get_capabilities()}"
            for name, agent in self._agents.items()
        )
        prompt = f"""You are a routing planner. Given a user query and a list of available agents, 
produce a JSON execution plan.

Available agents:
{capabilities}

User query: {query}

Return ONLY valid JSON with this structure:
{{
  "steps": [
    {{"agent_name": "<name>", "parallel_group": 0}},
    ...
  ],
  "reasoning": "<brief explanation>"
}}

Rules:
- Steps with the same parallel_group number run in parallel.
- Use parallel_group 0 for the first group, 1 for the second, etc.
- Only include agents that are relevant to the query.
- If the query needs both RAG and calculation, assign them the same parallel_group.
"""
        response = await self._llm.ainvoke([HumanMessage(content=prompt)])
        content = str(response.content).strip()
        # Strip markdown fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        try:
            data = json.loads(content)
            return ExecutionPlan(
                steps=[ExecutionStep(**s) for s in data.get("steps", [])],
                reasoning=data.get("reasoning", ""),
            )
        except Exception:
            logger.exception("DynamicRouter: failed to parse plan, using all agents sequentially")
            return ExecutionPlan(
                steps=[
                    ExecutionStep(agent_name=name, parallel_group=i)
                    for i, name in enumerate(self._agents)
                ],
                reasoning="Fallback: sequential execution of all agents.",
            )
