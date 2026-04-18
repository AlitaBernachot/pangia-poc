# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""RDF agent — answers questions via SPARQL queries against a GraphDB/Ontotext triplestore."""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.pangiagent.agents.base_agent import BaseAgent
from app.config import get_settings
from app.models import AgentInput, AgentOutput

logger = logging.getLogger(__name__)


class RDFAgent(BaseAgent):
    name = "rdf_agent"
    _DEFAULT_PROMPT = (
        "You are a Linked Data and Semantic Web specialist with deep knowledge of "
        "RDF, OWL, and SPARQL. You answer questions by generating SPARQL queries "
        "for a GraphDB (Ontotext) triplestore containing geographic and thematic "
        "RDF data. Produce a clear SPARQL query and a concise explanation of what "
        "it retrieves. If context facts are provided, incorporate them."
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
            "RDF/Linked Data queries: generates SPARQL queries for a GraphDB "
            "triplestore to answer questions about semantically modelled geographic "
            "and thematic data."
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
            logger.exception("RDFAgent failed")
            return AgentOutput(
                agent_name=self.name,
                answer="",
                confidence=0.0,
                error=str(exc),
            )
