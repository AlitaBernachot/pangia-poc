# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Vector/ChromaDB agent — retrieves documents via semantic search and synthesizes an answer."""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.pangiagent.agents.base_agents.base_agent import BaseAgent
from app.pangiagent.model_config import build_llm, get_agent_model_config
from app.models import AgentInput, AgentOutput
from libs.clients.chroma_client import similarity_search

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = (
    "You are a semantic search specialist. Given retrieved document excerpts and a "
    "user query, provide a concise, accurate answer grounded in those documents. "
    "Cite the document index (e.g. [1], [2]) when referencing specific content. "
    "If no relevant documents were found, say so clearly. "
    "Answer in the same language as the query."
)


class VectorChromaAgent(BaseAgent):
    name = "vector_chroma_agent"

    def __init__(self, **kwargs) -> None:
        super().__init__(name=self.name, **kwargs)
        self._llm = build_llm(get_agent_model_config(self.name))
        self._system_prompt = self.get_prompt(_DEFAULT_PROMPT)

    def get_capabilities(self) -> str:
        return (
            "Semantic vector search: retrieves and synthesises answers from a "
            "ChromaDB collection using embedding-based similarity search."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        # Step 1 — retrieve documents from ChromaDB
        try:
            raw_results = await similarity_search(inp.query, n_results=5)
        except Exception as exc:
            logger.warning("VectorChromaAgent: ChromaDB search failed — %s", exc)
            raw_results = "No documents could be retrieved from the vector store."

        # Step 2 — synthesize an answer
        try:
            response = await self._llm.ainvoke([
                SystemMessage(content=self._system_prompt),
                HumanMessage(content=(
                    f"Retrieved documents (JSON):\n{raw_results}\n\n"
                    f"Query: {inp.query}"
                )),
            ])
            return AgentOutput(
                agent_name=self.name,
                answer=str(response.content),
                confidence=0.8,
            )
        except Exception as exc:
            logger.exception("VectorChromaAgent: synthesis failed")
            return AgentOutput(agent_name=self.name, answer="", confidence=0.0, error=str(exc))
