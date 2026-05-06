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

_PHRASE_PROMPT = """\
Write a short sentence (15 words maximum) in the first person that describes \
what you are going to do to answer the user's request. Use the same language \
as the user's question. The sentence should start with "Je vais" (French) or \
"I will" (English) or the equivalent in the detected language, and end with \
"pour vous" / "for you" or similar. Be concrete and specific — mention the \
subject and the location or filter if present. Return ONLY the sentence, \
without a period at the end, no quotes, no preamble.

Examples:
User: "Affiche les stations Vélib à Paris"
→ Je vais localiser les stations Vélib disponibles à Paris pour vous.

User: "Où se trouvent les webcams dans Orléans ?"
→ Je vais localiser les webcams dans Orléans pour vous.

User: "parmi ces webcams, affiche seulement celles qui sont à Ingré"
→ Je vais filtrer les webcams pour afficher uniquement celles situées à Ingré.

User: "Quels sont les risques d'inondation en Bretagne ?"
→ Je vais analyser les zones à risque d'inondation en Bretagne pour vous.

User: "Show air quality data for Lyon"
→ I will retrieve air quality data across Lyon for you.

User: "How many bike lanes are in Bordeaux?"
→ I will count the bike lanes available in Bordeaux for you.
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

    async def generate_phrase(self, query: str) -> str:
        """Return a descriptive sentence summarising *query*, or '' on error."""
        try:
            llm = build_llm(get_agent_model_config(_AGENT_NAME))
            messages = [
                SystemMessage(content=_PHRASE_PROMPT),
                HumanMessage(content=query),
            ]
            response = await llm.ainvoke(messages)
            phrase = (response.content or "").strip().strip('"').strip("'").rstrip(".")
            return phrase[:160]
        except Exception:
            logger.exception("TitleAgent: failed to generate phrase")
            return ""
