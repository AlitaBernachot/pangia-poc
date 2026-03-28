"""Input Guardrail – orchestrator that wires all security checks and exposes
LangGraph nodes for the master agent pipeline.

Architecture
------------
The guardrail is split across two layers:

HTTP layer (``app.api.routes``)
    • Rate limiting  – checked before the graph is even started.
    • Authentication – checked before the graph is even started.

LangGraph layer (``guardrail_node`` / ``blocked_output_node`` in master.py)
    • Content filtering – PII detection (regex) + toxicity classification (LLM).
    • Intent validation – malicious-intent detection (LLM).

Both layers write their verdict to the same :class:`GuardrailResult` dataclass
so callers share a consistent interface regardless of the check type.

LangGraph integration
---------------------
``guardrail_node``
    Reads the latest human message from the state, runs content-filter and
    intent-validation checks, and sets ``state["guardrail_blocked"]`` /
    ``state["guardrail_message"]``.

``blocked_output_node``
    Converts the guardrail message into an ``AIMessage`` so the SSE stream
    delivers a human-readable rejection to the frontend.

``guardrail_dispatch``
    Conditional edge: routes to ``router`` when the message passed, or to
    ``blocked_output`` when it was rejected.
"""

import logging
from dataclasses import dataclass

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.model_config import build_llm, get_agent_model_config
from app.agent.state import AgentState
from app.config import get_settings
from app.security.content_filter import filter_content
from app.security.intent_validator import validate_intent

logger = logging.getLogger(__name__)

# ─── Result dataclass ──────────────────────────────────────────────────────────


@dataclass
class GuardrailResult:
    """Unified result returned by every guardrail check."""

    blocked: bool
    check: str | None = None       # which check triggered the block
    reason: str | None = None      # human-readable reason


# ─── LangGraph nodes ───────────────────────────────────────────────────────────


async def guardrail_node(state: AgentState) -> dict:
    """LangGraph node: content-filter + intent-validation guardrail.

    Reads the latest human message from the conversation state, runs all
    enabled LLM-based checks, and returns state updates::

        guardrail_blocked  – True when the request should be rejected.
        guardrail_message  – Human-readable rejection reason (or None).
    """
    settings = get_settings()

    # Extract the latest human message
    query = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        "",
    )

    if not query:
        return {"guardrail_blocked": False, "guardrail_message": None}

    # Build the LLM used for toxicity / intent checks (re-uses router model)
    llm = build_llm(get_agent_model_config("router"))

    # ── 1. Content filtering (PII + toxicity) ─────────────────────────────────
    if settings.guardrail_content_filter_enabled:
        content_result = await filter_content(
            query,
            pii_enabled=settings.guardrail_pii_filter_enabled,
            toxicity_enabled=settings.guardrail_toxicity_filter_enabled,
            llm=llm,
        )
        if content_result.blocked:
            logger.warning("Guardrail blocked request [content_filter]: %s", content_result.reason)
            return {
                "guardrail_blocked": True,
                "guardrail_message": content_result.reason,
            }

    # ── 2. Intent validation ───────────────────────────────────────────────────
    if settings.guardrail_intent_validation_enabled:
        intent_result = await validate_intent(query, llm)
        if intent_result.blocked:
            logger.warning("Guardrail blocked request [intent_validator]: %s", intent_result.reason)
            return {
                "guardrail_blocked": True,
                "guardrail_message": intent_result.reason,
            }

    return {"guardrail_blocked": False, "guardrail_message": None}


def blocked_output_node(state: AgentState) -> dict:
    """LangGraph node: convert the guardrail rejection into an AI message.

    This node is reached only when ``guardrail_blocked`` is ``True``.  It
    produces an ``AIMessage`` so the SSE stream can deliver the rejection
    reason to the frontend exactly like a normal agent response.
    """
    message = state.get("guardrail_message") or "Your request was blocked by the security guardrail."
    return {"messages": [AIMessage(content=message)]}


def guardrail_dispatch(state: AgentState):
    """Conditional edge: route to ``router`` or ``blocked_output``."""
    if state.get("guardrail_blocked"):
        return "blocked_output"
    return "router"
