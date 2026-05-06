# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Neo4j agent — answers questions by generating and executing Cypher queries."""
from __future__ import annotations

import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.pangiagent.agents.base_agents.base_agent import BaseAgent
from app.pangiagent.model_config import build_llm, get_agent_model_config
from app.models import AgentInput, AgentOutput
from libs.clients.neo4j_client import run_readonly_query

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = (
    "You are a Neo4j Cypher expert. Output ONLY the raw Cypher query with no "
    "explanation, no markdown, and no code fences. The query must be read-only "
    "(MATCH, RETURN — no MERGE, CREATE, DELETE, SET). "
    "Use meaningful aliases and limit results to 20 rows by default."
)



def _extract_cypher(text: str) -> str:
    match = re.search(r"```(?:cypher)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


class Neo4jAgent(BaseAgent):
    name = "neo4j_agent"

    def __init__(self, **kwargs) -> None:
        super().__init__(name=self.name, **kwargs)
        self._llm = build_llm(get_agent_model_config(self.name))
        self._system_prompt = self.get_prompt(_DEFAULT_PROMPT)

    def get_capabilities(self) -> str:
        return (
            "Knowledge graph queries: generates and executes Cypher queries against "
            "a Neo4j graph database to answer questions about geographic entities "
            "and their relationships."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        context_facts = inp.context.get("long_term_facts", [])
        context_str = "\n".join(f"- {fact['fact']}" for fact in context_facts)
        question = (
            f"Context facts:\n{context_str}\n\nQuestion: {inp.query}"
            if context_str
            else inp.query
        )

        # Step 1 — generate Cypher
        try:
            gen_response = await self._llm.ainvoke([
                SystemMessage(content=self._system_prompt),
                HumanMessage(content=question),
            ])
            cypher = _extract_cypher(str(gen_response.content))
        except Exception as exc:
            logger.exception("Neo4jAgent: Cypher generation failed")
            return AgentOutput(agent_name=self.name, answer="", confidence=0.0, error=str(exc))

        # Step 2 — execute Cypher
        try:
            records = await run_readonly_query(cypher)
            results = json.dumps(records, indent=2, ensure_ascii=False, default=str)
        except Exception as exc:
            logger.warning("Neo4jAgent: query execution failed — %s\nCypher: %s", exc, cypher)
            return AgentOutput(
                agent_name=self.name,
                answer=f"The generated Cypher query could not be executed: {exc}\n\nGenerated Cypher:\n```cypher\n{cypher}\n```",
                confidence=0.3,
                error=str(exc),
            )

        return AgentOutput(
            agent_name=self.name,
            answer=f"Cypher query:\n```cypher\n{cypher}\n```\n\nResults (JSON):\n{results}",
            confidence=0.85,
        )
