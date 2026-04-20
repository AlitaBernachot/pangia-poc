# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""RDF agent — answers questions by generating and executing SPARQL queries against GraphDB."""
from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.pangiagent.agents.base_agents.base_agent import BaseAgent
from app.pangiagent.model_config import build_llm, get_agent_model_config
from app.models import AgentInput, AgentOutput
from libs.client.graphdb_client import run_sparql_select

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = (
    "You are a SPARQL and Linked Data expert. Output ONLY the raw SPARQL SELECT "
    "query with no explanation, no markdown, and no code fences. "
    "Use standard prefixes (rdf:, rdfs:, owl:, geo:, schema:) where applicable. "
    "Limit results to 20 rows with LIMIT 20 unless the question requires more."
)



def _extract_sparql(text: str) -> str:
    match = re.search(r"```(?:sparql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


class RDFAgent(BaseAgent):
    name = "rdf_agent"

    def __init__(self, **kwargs) -> None:
        super().__init__(name=self.name, **kwargs)
        self._llm = build_llm(get_agent_model_config(self.name))
        self._system_prompt = self.get_prompt(_DEFAULT_PROMPT)

    def get_capabilities(self) -> str:
        return (
            "RDF/Linked Data queries: generates and executes SPARQL SELECT queries "
            "against a GraphDB triplestore to answer questions about semantically "
            "modelled geographic and thematic data."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        context_facts = inp.context.get("long_term_facts", [])
        context_str = "\n".join(f"- {fact['fact']}" for fact in context_facts)
        question = (
            f"Context facts:\n{context_str}\n\nQuestion: {inp.query}"
            if context_str
            else inp.query
        )

        # Step 1 — generate SPARQL
        try:
            gen_response = await self._llm.ainvoke([
                SystemMessage(content=self._system_prompt),
                HumanMessage(content=question),
            ])
            sparql = _extract_sparql(str(gen_response.content))
        except Exception as exc:
            logger.exception("RDFAgent: SPARQL generation failed")
            return AgentOutput(agent_name=self.name, answer="", confidence=0.0, error=str(exc))

        # Step 2 — execute SPARQL
        try:
            results = await run_sparql_select(sparql)
        except Exception as exc:
            logger.warning("RDFAgent: query execution failed — %s\nSPARQL: %s", exc, sparql)
            return AgentOutput(
                agent_name=self.name,
                answer=f"The generated SPARQL query could not be executed: {exc}\n\nGenerated SPARQL:\n```sparql\n{sparql}\n```",
                confidence=0.3,
                error=str(exc),
            )

        return AgentOutput(
            agent_name=self.name,
            answer=f"SPARQL query:\n```sparql\n{sparql}\n```\n\nResults (JSON):\n{results}",
            confidence=0.85,
        )
