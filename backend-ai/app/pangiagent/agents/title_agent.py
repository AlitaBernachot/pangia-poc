# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Title agent — generates a short conversation title from the user's first query.

This is a **utility agent**: it is called directly inside ``title_node`` in the
orchestrator graph and is *not* fanned out as a sub-agent.  It does not appear
in ``AGENTS``, is not routed to by the SmartDispatcher, and does not inherit
from ``BaseAgent`` (no guardrails needed for a 4-word title call).
"""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.pangiagent.model_config import build_llm, get_agent_model_config

logger = logging.getLogger(__name__)

_AGENT_NAME = "title_agent"

_DEFAULT_PROMPT = """\
Generate an ultra-short title (4–6 words maximum) that summarises the user's \
question in the language of that question. Return ONLY the title — no \
punctuation at the end, no quotes, no preamble, no explanation.

Examples:
User: "Affiche les stations Vélib à Paris"  → Stations Vélib Paris
User: "Show air quality data for Lyon"       → Air Quality Data Lyon
User: "Quels sont les risques d'inondation?" → Risques d'inondation France
"""


class TitleAgent:
    """Lightweight LLM call that produces a 4-6 word session title.

    Not a BaseAgent subclass — no guardrails, no subgraph, no fan-out.
    Called once per session from ``title_node`` in the orchestrator.
    """

    async def generate(self, query: str) -> str:
        """Return a short title string for *query*, or '' on error."""
        try:
            llm = build_llm(get_agent_model_config(_AGENT_NAME))
            messages = [
                SystemMessage(content=_DEFAULT_PROMPT),
                HumanMessage(content=query),
            ]
            response = await llm.ainvoke(messages)
            title = (response.content or "").strip().strip('"').strip("'")
            # Truncate defensively
            return title[:80]
        except Exception:
            logger.exception("TitleAgent: failed to generate title")
            return ""
