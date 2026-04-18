# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""PostGIS agent — answers spatial questions via SQL PostGIS queries."""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.pangiagent.agents.base_agent import BaseAgent
from app.config import get_settings
from app.models import AgentInput, AgentOutput

logger = logging.getLogger(__name__)


class PostGISAgent(BaseAgent):
    name = "postgis_agent"
    _DEFAULT_PROMPT = (
        "You are a spatial SQL specialist with expertise in PostgreSQL and PostGIS. "
        "You answer geographic questions by generating SQL queries that use PostGIS "
        "functions such as ST_Contains, ST_Distance, ST_Intersects, ST_Within, "
        "ST_Buffer, and ST_Area. Produce a clear SQL query and explain what it does. "
        "If context facts are provided, incorporate them into your answer."
    )

    def __init__(self, **kwargs) -> None:
        super().__init__(name=self.name, **kwargs)
        settings = get_settings()
        self._llm = ChatOpenAI(
            model=settings.model_name,
            api_key=settings.openai_api_key,
            temperature=settings.openai_temperature,
        )
        self._system_prompt = self.get_prompt(self._DEFAULT_PROMPT)

    def get_capabilities(self) -> str:
        return (
            "Spatial SQL queries: generates PostGIS SQL (ST_Contains, ST_Distance, "
            "ST_Intersects, …) to answer geographic and spatial analysis questions."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        context_facts = inp.context.get("long_term_facts", [])
        context_str = "\n".join(f"- {fact['fact']}" for fact in context_facts)

        user_content = (
            f"Context facts:\n{context_str}\n\nQuestion: {inp.query}"
            if context_str
            else f"Question: {inp.query}"
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
                confidence=0.7,
            )
        except Exception as exc:
            logger.exception("PostGISAgent failed")
            return AgentOutput(
                agent_name=self.name,
                answer="",
                confidence=0.0,
                error=str(exc),
            )
