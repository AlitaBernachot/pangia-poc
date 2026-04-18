# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Callable, Optional

from app.models import AgentInput, AgentOutput

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    def __init__(
        self,
        name: str,
        pre_guardrails: Optional[list[Callable[[AgentInput], Optional[str]]]] = None,
        post_guardrails: Optional[list[Callable[[AgentOutput], Optional[str]]]] = None,
    ) -> None:
        self.name = name
        self.pre_guardrails = pre_guardrails or []
        self.post_guardrails = post_guardrails or []

    @abstractmethod
    def get_capabilities(self) -> str:
        """Return a description of what this agent can do."""

    @abstractmethod
    async def _run(self, inp: AgentInput) -> AgentOutput:
        """Core agent logic."""

    async def run(self, inp: AgentInput) -> AgentOutput:
        # Pre-guardrails
        for guardrail in self.pre_guardrails:
            violation = guardrail(inp)
            if violation:
                logger.warning("Pre-guardrail blocked [%s]: %s", self.name, violation)
                return AgentOutput(
                    agent_name=self.name,
                    answer="",
                    confidence=0.0,
                    error=violation,
                )

        start = time.monotonic()
        try:
            output = await self._run(inp)
        except Exception as exc:
            logger.exception("Agent [%s] raised an exception", self.name)
            return AgentOutput(
                agent_name=self.name,
                answer="",
                confidence=0.0,
                error=str(exc),
            )

        output.state["duration_ms"] = int((time.monotonic() - start) * 1000)

        # Post-guardrails
        violations = []
        for guardrail in self.post_guardrails:
            violation = guardrail(output)
            if violation:
                logger.warning("Post-guardrail [%s]: %s", self.name, violation)
                violations.append(violation)
                output.confidence = max(0.0, output.confidence - 0.2)

        if violations:
            output.state["post_guardrail_violations"] = violations

        return output

    def as_subgraph(self):
        """Return a compiled LangGraph subgraph for this agent.

        By default wraps the agent in a single-node subgraph via
        ``make_subgraph()``.  Override in a subclass to define a custom
        multi-node graph (e.g. retrieve → rerank → generate for RAG agents).

        Returns
        -------
        CompiledStateGraph
            Ready to be added as a node in the orchestrator StateGraph.
        """
        from app.agents.subgraph import make_subgraph

        return make_subgraph(self)
