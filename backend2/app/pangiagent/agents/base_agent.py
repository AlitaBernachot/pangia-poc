# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

import yaml
from langgraph.graph import END, StateGraph

from app.models import AgentInput, AgentOutput, ChoiceItem, ChoiceRequest, ChoiceResponse
from app.pangiagent.model_config import get_agent_max_iterations
from app.pangiagent.state import SubAgentState

logger = logging.getLogger(__name__)

# Resolve path: backend2/app/pangiagent/agents/base_agent.py
#   → parent.parent.parent.parent = backend2/
_PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "config" / "prompts"


@lru_cache(maxsize=None)
def _load_prompt_file(agent_name: str) -> str | None:
    """Load the prompt for *agent_name* from ``config/prompts/<agent_name>.yaml``.

    Returns the prompt string, or ``None`` if the file does not exist or
    the ``prompt`` key is missing.
    """
    path = _PROMPTS_DIR / f"{agent_name}.yaml"
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        value = data.get("prompt")
        if value:
            logger.debug("BaseAgent: loaded prompt for '%s' from %s", agent_name, path)
            return str(value).strip()
    except Exception:
        logger.exception("BaseAgent: failed to load %s", path)
    return None


@dataclass
class ChoiceResult:
    """Outcome of a ``BaseAgent.request_choice()`` call.

    Attributes
    ----------
    resolved:
        ``True`` if the user picked an item; ``False`` on timeout.
    chosen_id:
        The ``id`` of the ``ChoiceItem`` the user selected (empty on timeout).
    chosen_query:
        The query rewritten to target the chosen item (empty on timeout).
    request_id:
        The unique ID of the ``ChoiceRequest`` that was issued.
    """
    resolved: bool
    chosen_id: str = ""
    chosen_query: str = ""
    request_id: str = ""


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
        self.max_iterations: int = get_agent_max_iterations(name)

    # ── Choice / disambiguation helper ────────────────────────────────────────

    async def request_choice(
        self,
        session_id: str,
        original_query: str,
        items: list[ChoiceItem],
        total: int | None = None,
    ) -> ChoiceResult:
        """Suspend the agent and ask the user to pick one item from *items*.

        This is the reusable building block for any agent that needs human
        disambiguation.  It registers a :class:`ChoiceRequest` with the
        :class:`~app.pangiagent.hitl.HITLManager`, signals the orchestrator
        via ``AgentOutput.state["pending_choice_request_id"]``, and then
        **awaits** the future resolved by :meth:`HITLManager.resolve_choice`.

        Parameters
        ----------
        session_id:
            The current session identifier.
        original_query:
            The user's original query (used for context in the frontend).
        items:
            List of :class:`ChoiceItem` instances to present to the user.
        total:
            Optional total number of matching items when *items* is a
            truncated subset of a larger result set.

        Returns
        -------
        ChoiceResult
            ``resolved=True`` with ``chosen_id`` and ``chosen_query`` when
            the user picks an item; ``resolved=False`` on timeout.
        """
        from app.pangiagent.hitl import get_hitl_manager
        import uuid

        request_id = str(uuid.uuid4())
        choice_request = ChoiceRequest(
            request_id=request_id,
            session_id=session_id,
            agent_name=self.name,
            original_query=original_query,
            items=items,
            total=total,
        )
        manager = get_hitl_manager()
        await manager.create_choice_request(choice_request)
        result: ChoiceResponse | None = await manager.wait_for_choice(request_id)
        if result is None:
            return ChoiceResult(resolved=False, request_id=request_id)
        return ChoiceResult(
            resolved=True,
            chosen_id=result.chosen_id,
            chosen_query=result.chosen_query,
            request_id=request_id,
        )

    def get_prompt(self, default: str) -> str:
        """Return the system prompt for this agent.

        Resolution order:
        1. ``config/prompts/<agent_name>.yaml`` (``prompt`` key).
        2. *default* — hardcoded ``_DEFAULT_PROMPT`` on the subclass.

        Parameters
        ----------
        default:
            Hardcoded fallback string — document it as ``_DEFAULT_PROMPT``
            on the subclass so the intended behaviour is always visible in
            source.
        """
        return _load_prompt_file(self.name) or default

    # ── Intent helpers (populated by IntentParserAgent before fan-out) ────────

    def get_intent(self, inp: AgentInput) -> dict:
        """Extract and normalise the structured intent from ``inp.context["intent"]``.

        Returns a dict with guaranteed keys: ``action``, ``dataset_concept``,
        ``filters``, ``geo_scope``.  Populated by ``IntentParserAgent`` in
        ``intent_node`` before the agent fan-out; returns sensible defaults
        when no intent was parsed.

        Usage::

            intent = self.get_intent(inp)
            action = intent["action"]        # "display" | "filter" | "search" | "preview" | "compare"
            concept = intent["dataset_concept"]
            filters = intent["filters"]      # list[{"column", "value", "op"}]
            geo = intent["geo_scope"]
        """
        raw: dict = inp.context.get("intent") or {}
        return {
            "action": str(raw.get("action", "display")).lower().strip(),
            "dataset_concept": str(raw.get("dataset_concept", "")).strip(),
            "filters": list(raw.get("filters") or []),
            "geo_scope": str(raw.get("geo_scope", "")).strip(),
        }

    async def _run_by_action(self, inp: AgentInput) -> AgentOutput:
        """Dispatch to the appropriate ``_run_<action>`` handler.

        Use this as the body of ``_run()`` in intent-aware sub-agents::

            async def _run(self, inp: AgentInput) -> AgentOutput:
                return await self._run_by_action(inp)

        Then override one or more of :meth:`_run_display`, :meth:`_run_filter`,
        :meth:`_run_search`, :meth:`_run_preview`, :meth:`_run_compare`.
        Unknown action values fall back to :meth:`_run_display`.
        """
        intent = self.get_intent(inp)
        action = intent["action"]
        dispatch = {
            "display": self._run_display,
            "filter": self._run_filter,
            "search": self._run_search,
            "preview": self._run_preview,
            "compare": self._run_compare,
        }
        handler = dispatch.get(action)
        if handler is None:
            logger.warning(
                "%s: unknown intent action %r — falling back to _run_display",
                self.name,
                action,
            )
            handler = self._run_display
        return await handler(inp, intent)

    async def _run_display(self, inp: AgentInput, intent: dict) -> AgentOutput:
        """Handle ``action=display``: show / visualise all data.

        Override in sub-agents that support intent-based dispatch.
        Agents that do not need action dispatch should override :meth:`_run` directly.
        """
        raise NotImplementedError(
            f"Agent '{self.name}' must implement _run_display() "
            "or override _run() directly."
        )

    async def _run_filter(self, inp: AgentInput, intent: dict) -> AgentOutput:
        """Handle ``action=filter``: records matching a condition.

        Default: delegates to :meth:`_run_display`.
        """
        return await self._run_display(inp, intent)

    async def _run_search(self, inp: AgentInput, intent: dict) -> AgentOutput:
        """Handle ``action=search``: discover what datasets exist on a topic.

        Default: delegates to :meth:`_run_display`.
        """
        return await self._run_display(inp, intent)

    async def _run_preview(self, inp: AgentInput, intent: dict) -> AgentOutput:
        """Handle ``action=preview``: sample / overview of data.

        Default: delegates to :meth:`_run_display`.
        """
        return await self._run_display(inp, intent)

    async def _run_compare(self, inp: AgentInput, intent: dict) -> AgentOutput:
        """Handle ``action=compare``: compare two or more datasets.

        Default: delegates to :meth:`_run_display`.
        """
        return await self._run_display(inp, intent)

    @abstractmethod
    def get_capabilities(self) -> str:
        """Return a description of what this agent can do."""

    @abstractmethod
    async def _run(self, inp: AgentInput) -> AgentOutput:
        """Core agent logic."""

    def make_node(self):
        """Return a callable suitable for ``workflow.add_node()``.

        The default implementation delegates to :meth:`as_subgraph`, which
        wraps this agent in a single-node LangGraph subgraph and merges its
        result into ``sub_results``.

        Override in subclasses that need to interact directly with
        ``OrchestratorState`` (e.g. post-processing agents such as
        ``HumanOutputAgent``, ``DataVizAgent``, ``MapVizAgent``).
        In those overrides, the returned callable must be an ``async`` function
        accepting an ``OrchestratorState`` dict and returning a partial state
        update dict.
        """
        return self.as_subgraph()

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

        Builds a single-node ``StateGraph`` (``execute_node → __end__``) that
        delegates entirely to ``self.run()``.  The subgraph shares ``query``,
        ``session_id``, ``context``, and ``sub_results`` with the parent
        ``OrchestratorState``; only ``sub_results`` is merged back via the
        ``_merge_dicts`` reducer.

        Override in a subclass to define a custom multi-node graph (e.g.
        retrieve → rerank → generate for RAG agents).

        Returns
        -------
        CompiledStateGraph
            Ready to be added as a node in the orchestrator StateGraph.
        """
        agent_name = self.name
        agent = self

        async def execute_node(state: SubAgentState) -> dict:
            inp = AgentInput(
                query=state["query"],
                session_id=state["session_id"],
                context=state.get("context", {}),  # type: ignore[arg-type]
            )
            output = await agent.run(inp)
            entry: dict = {
                "answer": output.answer,
                "confidence": output.confidence,
                "error": output.error,
                "duration_ms": output.state.get("duration_ms", 0),
                "violations": output.state.get("post_guardrail_violations", []),
            }
            # Forward any rich-data extras produced by the agent
            # (dataviz, geojson, etc.) so the SSE layer can emit the appropriate
            # frontend events.
            for key in ("dataviz", "geojson"):
                if key in output.state:
                    value = output.state[key]
                    # Normalise dataviz table keys: LLM sometimes uses tool
                    # param names (columns_json / rows_json) instead of the
                    # expected output keys (columns / rows).
                    if key == "dataviz" and isinstance(value, dict):
                        for tbl in value.get("tables") or []:
                            if "columns_json" in tbl and "columns" not in tbl:
                                tbl["columns"] = tbl.pop("columns_json")
                            if "rows_json" in tbl and "rows" not in tbl:
                                tbl["rows"] = tbl.pop("rows_json")
                    entry[key] = value
            return {
                "sub_results": {
                    agent_name: entry
                }
            }

        workflow = StateGraph(SubAgentState)
        workflow.add_node("execute_node", execute_node)
        workflow.set_entry_point("execute_node")
        workflow.add_edge("execute_node", END)
        return workflow.compile()
