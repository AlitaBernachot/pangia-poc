# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.agents.base_agent import BaseAgent
from app.config import get_settings
from app.models import AgentInput, AgentOutput

logger = logging.getLogger(__name__)


class RAGAgent(BaseAgent):
    def __init__(self, **kwargs) -> None:
        super().__init__(name="rag_agent", **kwargs)
        settings = get_settings()
        self._llm = ChatOpenAI(
            model=settings.model_name,
            api_key=settings.openai_api_key,
            temperature=settings.openai_temperature,
        )

    def get_capabilities(self) -> str:
        return (
            "Retrieval-Augmented Generation: answers questions using context "
            "retrieved from a knowledge base or provided in the input."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        context_str = "\n".join(
            f"- {fact['fact']}" for fact in inp.context.get("long_term_facts", [])
        )
        prompt = (
            f"Context:\n{context_str}\n\nQuestion: {inp.query}\n\nAnswer concisely."
            if context_str
            else f"Question: {inp.query}\n\nAnswer concisely."
        )
        response = await self._llm.ainvoke([HumanMessage(content=prompt)])
        return AgentOutput(
            agent_name=self.name,
            answer=str(response.content),
            confidence=0.85,
        )
