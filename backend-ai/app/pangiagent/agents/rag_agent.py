# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""RAG agent — retrieves context from ChromaDB and generates a grounded answer."""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.pangiagent.agents.base_agents.base_agent import BaseAgent
from app.pangiagent.model_config import build_llm, get_agent_model_config
from app.models import AgentInput, AgentOutput
from libs.client.chroma_client import similarity_search

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = (
    "You are a knowledgeable assistant. Use the provided context documents to "
    "answer questions accurately and concisely. When the context is relevant, "
    "base your answer on it. When it is not, answer from your general knowledge "
    "and clearly indicate that. Answer in the same language as the question."
)


class RAGAgent(BaseAgent):
    name = "rag_agent"

    def __init__(self, **kwargs) -> None:
        super().__init__(name="rag_agent", **kwargs)
        self._llm = build_llm(get_agent_model_config(self.name))
        self._system_prompt = self.get_prompt(_DEFAULT_PROMPT)

    def get_capabilities(self) -> str:
        return (
            "Retrieval-Augmented Generation: retrieves relevant documents from a "
            "ChromaDB vector store and uses them as context to answer questions accurately."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        # Step 1 — retrieve context from ChromaDB
        try:
            retrieved = await similarity_search(inp.query, n_results=5)
        except Exception as exc:
            logger.warning("RAGAgent: ChromaDB retrieval failed — %s", exc)
            retrieved = ""

        # Also include any long-term facts from memory
        long_term = inp.context.get("long_term_facts", [])
        facts_str = "\n".join(f"- {f['fact']}" for f in long_term)

        context_block = ""
        if retrieved:
            context_block += f"Retrieved documents:\n{retrieved}\n\n"
        if facts_str:
            context_block += f"Context facts:\n{facts_str}\n\n"

        user_content = (
            f"{context_block}Question: {inp.query}"
            if context_block
            else f"Question: {inp.query}"
        )

        # Step 2 — generate answer
        try:
            response = await self._llm.ainvoke([
                SystemMessage(content=self.get_prompt_for_request(inp, _DEFAULT_PROMPT)),
                HumanMessage(content=user_content),
            ])
            return AgentOutput(
                agent_name=self.name,
                answer=str(response.content),
                confidence=0.85,
            )
        except Exception as exc:
            logger.exception("RAGAgent: generation failed")
            return AgentOutput(agent_name=self.name, answer="", confidence=0.0, error=str(exc))
