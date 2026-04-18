# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

import yaml

from app.models import AgentInput, AgentOutput

logger = logging.getLogger(__name__)

_PROMPTS_FILE = Path(__file__).parent / "prompts.yml"


@lru_cache(maxsize=1)
def load_prompts() -> dict[str, str]:
    """Load and cache all agent system prompts from ``agents/prompts.yml``.

    Returns an empty dict (and logs a warning) if the file is missing or
    malformed so that agents can fall back to their hardcoded defaults
    without crashing.

    Call ``load_prompts.cache_clear()`` in tests that need to inject a
    different prompt mapping.
    """
    if not _PROMPTS_FILE.exists():
        logger.warning(
            "BaseAgent: %s not found — all agents will use default prompts",
            _PROMPTS_FILE,
        )
        return {}
    try:
        with _PROMPTS_FILE.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise TypeError(f"Expected a YAML mapping, got {type(data)}")
        logger.debug("BaseAgent: loaded %d prompt(s) from %s", len(data), _PROMPTS_FILE)
        return {k: str(v).strip() for k, v in data.items()}
    except Exception:
        logger.exception("BaseAgent: failed to load %s — using defaults", _PROMPTS_FILE)
        return {}


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

    def get_prompt(self, default: str) -> str:
        """Return the system prompt for this agent from ``prompts.yml``.

        Looks up the agent's ``name`` in the YAML file loaded by
        ``load_prompts()``.  Falls back to *default* when the key is absent.

        Parameters
        ----------
        default:
            Hardcoded fallback string — document it as ``_DEFAULT_PROMPT``
            on the subclass so the intended behaviour is always visible in
            source.
        """
        return load_prompts().get(self.name, default)

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
