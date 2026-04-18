# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""data.gouv.fr MCP agent — answers questions by querying the French open-data catalogue."""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.pangiagent.agents.base_agent import BaseAgent
from app.pangiagent.model_config import build_llm, get_agent_model_config
from app.models import AgentInput, AgentOutput

logger = logging.getLogger(__name__)


class DataGouvMCPAgent(BaseAgent):
    name = "datagouv_mcp_agent"
    _DEFAULT_PROMPT = (
        "You are a specialist in French open government data available on "
        "data.gouv.fr, the official French open-data catalogue. You help users "
        "discover, describe, and interpret public datasets published by French "
        "government agencies, local authorities, and public organisations. "
        "When answering, identify relevant datasets, explain their content and "
        "format, and suggest how they can be used. "
        "Note: live MCP connectivity will be enabled in a future iteration; "
        "for now, answer from your knowledge of the catalogue."
    )

    def __init__(self, **kwargs) -> None:
        super().__init__(name=self.name, **kwargs)
        self._llm = build_llm(get_agent_model_config(self.name))
        self._system_prompt = self.get_prompt(self._DEFAULT_PROMPT)

    def get_capabilities(self) -> str:
        return (
            "French open-data catalogue: finds and describes datasets from "
            "data.gouv.fr for a given query or topic."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        user_content = (
            f"Find and describe relevant datasets on data.gouv.fr for the "
            f"following question or topic:\n\n{inp.query}"
        )

        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=user_content),
        ]
        try:
            response = await self._llm.ainvoke(messages)
            return AgentOutput(
                agent_name=self.name,
                answer=str(response.content),
                confidence=0.75,
            )
        except Exception as exc:
            logger.exception("DataGouvMCPAgent failed")
            return AgentOutput(
                agent_name=self.name,
                answer="",
                confidence=0.0,
                error=str(exc),
            )
