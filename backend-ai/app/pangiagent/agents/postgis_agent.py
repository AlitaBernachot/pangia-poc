# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""PostGIS agent — answers spatial questions by generating and executing PostGIS SQL."""
from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.pangiagent.agents.base_agents.base_agent import BaseAgent
from app.pangiagent.model_config import build_llm, get_agent_model_config
from app.models import AgentInput, AgentOutput
from libs.client.postgis_client import run_spatial_query

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = (
    "You are a PostGIS SQL expert. Output ONLY the raw SQL query with no explanation, "
    "no markdown, and no code fences. The query must be read-only (SELECT). "
    "Use ST_SetSRID / ST_Transform when mixing SRIDs. "
    "Use ST_DWithin for distance queries. Return coordinates as SRID 4326. "
    "Use ST_AsGeoJSON when the question asks for a map."
)



def _extract_sql(text: str) -> str:
    """Extract a SQL statement from an LLM response.

    Strips markdown code fences if present, otherwise returns the raw text.
    """
    # Match ```sql ... ``` or ``` ... ```
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


class PostGISAgent(BaseAgent):
    name = "postgis_agent"

    def __init__(self, **kwargs) -> None:
        super().__init__(name=self.name, **kwargs)
        self._llm = build_llm(get_agent_model_config(self.name))
        self._system_prompt = self.get_prompt(_DEFAULT_PROMPT)

    def get_capabilities(self) -> str:
        return (
            "Spatial SQL queries: generates and executes PostGIS SQL "
            "(ST_Contains, ST_Distance, ST_Intersects, …) to answer geographic "
            "and spatial analysis questions against a live PostGIS database."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        context_facts = inp.context.get("long_term_facts", [])
        context_str = "\n".join(f"- {fact['fact']}" for fact in context_facts)
        question = (
            f"Context facts:\n{context_str}\n\nQuestion: {inp.query}"
            if context_str
            else inp.query
        )

        # Step 1 — generate SQL
        try:
            gen_response = await self._llm.ainvoke([
                SystemMessage(content=self._system_prompt),
                HumanMessage(content=question),
            ])
            sql = _extract_sql(str(gen_response.content))
        except Exception as exc:
            logger.exception("PostGISAgent: SQL generation failed")
            return AgentOutput(agent_name=self.name, answer="", confidence=0.0, error=str(exc))

        # Step 2 — execute SQL
        try:
            results = await run_spatial_query(sql)
        except Exception as exc:
            logger.warning("PostGISAgent: query execution failed — %s\nSQL: %s", exc, sql)
            return AgentOutput(
                agent_name=self.name,
                answer=f"The generated SQL query could not be executed: {exc}\n\nGenerated SQL:\n```sql\n{sql}\n```",
                confidence=0.3,
                error=str(exc),
            )

        return AgentOutput(
            agent_name=self.name,
            answer=f"SQL query:\n```sql\n{sql}\n```\n\nResults (JSON):\n{results}",
            confidence=0.85,
        )
