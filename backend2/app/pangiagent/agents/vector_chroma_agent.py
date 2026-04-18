# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Vector/ChromaDB agent — answers questions via semantic search over a ChromaDB collection."""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.pangiagent.agents.base_agent import BaseAgent
from app.pangiagent.model_config import build_llm, get_agent_model_config
from app.models import AgentInput, AgentOutput

logger = logging.getLogger(__name__)


class VectorChromaAgent(BaseAgent):
    name = "vector_chroma_agent"
    _DEFAULT_PROMPT = (
        "You are a semantic search specialist using ChromaDB vector embeddings. "
        "You answer questions by synthesising information retrieved from a semantic "
        "similarity search over a document collection. Use the context documents "
        "provided to formulate a concise, accurate answer. If no relevant documents "
        "are found, say so clearly."
    )

    def __init__(self, **kwargs) -> None:
        super().__init__(name=self.name, **kwargs)
        self._llm = build_llm(get_agent_model_config(self.name))
        self._system_prompt = self.get_prompt(self._DEFAULT_PROMPT)

    def get_capabilities(self) -> str:
        return (
            "Semantic vector search: retrieves and synthesises answers from a "
            "ChromaDB collection using embedding-based similarity search."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        # Context may contain documents retrieved upstream by a retrieval step.
        retrieved_docs = inp.context.get("retrieved_documents", [])
        docs_str = "\n".join(
            f"[{i + 1}] {doc}" for i, doc in enumerate(retrieved_docs)
        )

        user_content = (
            f"Retrieved documents:\n{docs_str}\n\nQuery: {inp.query}\n\nAnswer concisely."
            if docs_str
            else f"Query: {inp.query}\n\nAnswer concisely based on your knowledge."
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
                confidence=0.8,
            )
        except Exception as exc:
            logger.exception("VectorChromaAgent failed")
            return AgentOutput(
                agent_name=self.name,
                answer="",
                confidence=0.0,
                error=str(exc),
            )
