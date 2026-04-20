# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import Optional

from app.models import AgentInput, AgentOutput

_TOXIC_WORDS = frozenset(["kill", "murder", "hack", "exploit", "porn", "bomb"])


def check_toxic_input(inp: AgentInput) -> Optional[str]:
    query_lower = inp.query.lower()
    for word in _TOXIC_WORDS:
        if word in query_lower:
            return f"Guardrail violation: toxic keyword '{word}' detected in input."
    return None


def check_ambiguous_intent(inp: AgentInput) -> Optional[str]:
    """Block queries that are too short to be meaningful.

    Uncertainty-word detection is intentionally omitted here — that
    responsibility belongs to the LLM-based ``AmbiguityAgent`` in the
    orchestrator graph, which triggers HITL when needed.
    """
    if len(inp.query.strip()) < 5:
        return "Guardrail violation: query is too short and ambiguous."
    return None


def check_output_length(out: AgentOutput) -> Optional[str]:
    if len(out.answer) > 10_000:
        return f"Guardrail violation: output too long ({len(out.answer)} chars, max 10000)."
    return None
