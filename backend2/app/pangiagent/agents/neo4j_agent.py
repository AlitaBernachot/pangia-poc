# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Neo4j agent — answers questions via Cypher queries against a Neo4j knowledge graph."""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.pangiagent.agents.base_agent import BaseAgent
from app.config import get_settings
from app.models import AgentInput, AgentOutput

logger = logging.getLogger(__name__)


class Neo4jAgent(BaseAgent):
    name = "neo4j_agent"
    _DEFAULT_PROMPT = (
        "You are a specialist in geographic knowledge graphs powered by Neo4j. "
        "You generate and explain Cypher queries to answer spatial and relational "
        "questions about geographic entities, their relationships, and properties. "
        "When given a question, produce a clear Cypher query and a concise explanation "
        "of what it retrieves. If context facts are provided, incorporate them."
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
            "Knowledge graph queries: generates Cypher queries for Neo4j to answer "
            "questions about geographic entities and their relationships."
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
            logger.exception("Neo4jAgent failed")
            return AgentOutput(
                agent_name=self.name,
                answer="",
                confidence=0.0,
                error=str(exc),
            )
