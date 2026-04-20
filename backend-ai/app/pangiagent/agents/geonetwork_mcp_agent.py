# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""GeoNetwork MCP agent — answers questions by querying a GeoNetwork metadata catalogue."""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.pangiagent.agents.base_agents.base_agent import BaseAgent
from app.pangiagent.model_config import build_llm, get_agent_model_config
from app.models import AgentInput, AgentOutput

logger = logging.getLogger(__name__)


class GeoNetworkMCPAgent(BaseAgent):
    name = "geonetwork_mcp_agent"
    _DEFAULT_PROMPT = (
        "You are a geospatial metadata specialist with expertise in GeoNetwork, "
        "an open-source catalogue application for managing geospatial resources. "
        "You help users find, describe, and interpret geographic datasets, services, "
        "and maps published in a GeoNetwork catalogue using ISO 19115/19139 metadata "
        "standards. Identify relevant geospatial resources, describe their spatial "
        "extent, resolution, and intended use. "
        "Note: live MCP connectivity will be enabled in a future iteration; "
        "for now, answer from your knowledge of GeoNetwork catalogues."
    )

    def __init__(self, mcp_url: str = "", **kwargs) -> None:
        super().__init__(name=self.name, **kwargs)
        self._mcp_url = mcp_url
        self._llm = build_llm(get_agent_model_config(self.name))
        self._system_prompt = self.get_prompt(self._DEFAULT_PROMPT)

    def get_capabilities(self) -> str:
        return (
            "GeoNetwork metadata catalogue: finds and describes geospatial datasets "
            "and services from a GeoNetwork instance using ISO 19115/19139 metadata."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        url_hint = (
            f" The GeoNetwork instance URL is: {self._mcp_url}."
            if self._mcp_url
            else ""
        )
        user_content = (
            f"Find and describe relevant geospatial resources in the GeoNetwork "
            f"catalogue for the following question or topic:{url_hint}\n\n{inp.query}"
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
            logger.exception("GeoNetworkMCPAgent failed")
            return AgentOutput(
                agent_name=self.name,
                answer="",
                confidence=0.0,
                error=str(exc),
            )
