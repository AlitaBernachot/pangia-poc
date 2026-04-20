# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.pangiagent.agents.base_agent import BaseAgent
from app.pangiagent.model_config import build_llm, get_agent_model_config
from app.models import AgentInput, AgentOutput

logger = logging.getLogger(__name__)


class RAGAgent(BaseAgent):
    name = "rag_agent"
    _DEFAULT_PROMPT = (
        "You are a knowledgeable assistant. Answer questions using the provided "
        "context when available. Be concise and accurate."
    )

    def __init__(self, **kwargs) -> None:
        super().__init__(name="rag_agent", **kwargs)
        self._llm = build_llm(get_agent_model_config(self.name))
        self._system_prompt = self.get_prompt(self._DEFAULT_PROMPT)

    def get_capabilities(self) -> str:
        return (
            "Retrieval-Augmented Generation: answers questions using context "
            "retrieved from a knowledge base or provided in the input."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        context_str = "\n".join(
            f"- {fact['fact']}" for fact in inp.context.get("long_term_facts", [])
        )
        user_content = (
            f"Context:\n{context_str}\n\nQuestion: {inp.query}\n\nAnswer concisely."
            if context_str
            else f"Question: {inp.query}\n\nAnswer concisely."
        )
        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=user_content),
        ]
        response = await self._llm.ainvoke(messages)
        return AgentOutput(
            agent_name=self.name,
            answer=str(response.content),
            confidence=0.85,
        )
