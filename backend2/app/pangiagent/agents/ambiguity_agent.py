# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""
LLM-based ambiguity scorer used by the orchestrator's ``ambiguity_node``.

``AmbiguityAgent`` is deliberately *not* a ``BaseAgent`` subgraph — it is a
utility called directly inside a LangGraph node rather than being fanned-out
as an independent sub-agent.  It lives in ``agents/`` because it encapsulates
LLM interaction and is closely related to the agent layer.
"""
from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.pangiagent.agents.base_agent import load_prompts
from app.config import get_settings

logger = logging.getLogger(__name__)


class AmbiguityAgent:
    """LLM-based ambiguity scorer for HITL triggering.

    Scores a query on a 0–1 scale and returns clarifying questions when
    the query is considered ambiguous.
    """

    _DEFAULT_PROMPT = (
        "Evaluate if the following query is ambiguous "
        "(score 0=clear, 1=very ambiguous).\n"
        'Return JSON only: {"score": 0.0, "questions": ["clarifying question 1", ...]}'
    )

    def __init__(self) -> None:
        settings = get_settings()
        self._llm = ChatOpenAI(
            model=settings.model_name,
            api_key=settings.openai_api_key,
            temperature=0.0,
        )
        self._threshold = settings.hitl_ambiguity_threshold
        self._system_prompt = load_prompts().get("ambiguity_agent", self._DEFAULT_PROMPT)

    async def detect(self, query: str) -> tuple[float, list[str]]:
        """Score *query* for ambiguity.

        Returns
        -------
        tuple[float, list[str]]
            ``(score, clarifying_questions)`` where *score* is in [0, 1]
            (0 = clear, 1 = very ambiguous).  *clarifying_questions* is
            empty when the score is below the threshold or on parse error.
        """
        try:
            messages = [
                SystemMessage(content=self._system_prompt),
                HumanMessage(content=f"Query: {query}\n\nReturn ONLY the JSON."),
            ]
            response = await self._llm.ainvoke(messages)
            content = str(response.content).strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            data = json.loads(content)
            return float(data.get("score", 0.0)), list(data.get("questions", []))
        except Exception:
            logger.exception("AmbiguityAgent: failed to parse LLM response")
            return 0.0, []

    @property
    def threshold(self) -> float:
        return self._threshold
