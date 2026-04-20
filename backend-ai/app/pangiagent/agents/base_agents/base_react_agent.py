# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Intermediate base class for agents that use a ReAct (Reasoning + Acting) loop."""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from app.pangiagent.agents.base_agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class BaseReActAgent(BaseAgent):
    """Base class for agents that interact with external tools via a ReAct loop.

    Provides :meth:`_react_loop` — a reusable LLM → tools → LLM iteration
    that subclasses can call from their :meth:`_run` implementation, and
    :meth:`_invoke_tool` — an overridable single-call hook for custom dispatch
    (e.g. caching, guards, or pre/post-processing).

    Subclasses whose loops are too specialised to use :meth:`_react_loop`
    directly (e.g. because they need inline guards or disambiguation) may
    simply inherit from this class and implement their own loop, using
    :meth:`_invoke_tool` as a dispatch helper.
    """

    async def _react_loop(
        self,
        messages: list,
        llm: Any,
        tool_map: dict[str, Any],
    ) -> list:
        """Run the ReAct loop and return the updated messages list.

        Iterates up to ``self.max_iterations`` times:

        1. Invoke *llm* with the current *messages*.
        2. Stop if the response contains no tool calls.
        3. For each tool call, delegate to :meth:`_invoke_tool` and append a
           ``ToolMessage`` with the result.

        Parameters
        ----------
        messages:
            Initial message list (``[SystemMessage, HumanMessage, ...]``).
            Mutated in-place and returned.
        llm:
            A bound LangChain chat model (already has tools bound via
            ``bind_tools``).
        tool_map:
            Mapping from tool name to callable tool object.
        """
        for _ in range(self.max_iterations):
            response: AIMessage = await llm.ainvoke(messages)
            messages.append(response)
            if not getattr(response, "tool_calls", None):
                break
            for tc in response.tool_calls:
                result = await self._invoke_tool(tc, tool_map)
                messages.append(ToolMessage(
                    content=result,
                    tool_call_id=tc.get("id", ""),
                ))
        return messages

    async def _invoke_tool(self, tc: dict, tool_map: dict[str, Any]) -> str:
        """Invoke a single tool call and return the result as a string.

        Override in subclasses to add per-call behaviour such as result
        caching, URL guards, or disambiguation logic.

        Parameters
        ----------
        tc:
            The tool call dict with keys ``name``, ``args``, and ``id``.
        tool_map:
            Mapping from tool name to callable tool object.
        """
        tool_fn = tool_map.get(tc["name"])
        if tool_fn is None:
            return f"Unknown tool: {tc['name']}. Available: {list(tool_map)}"
        try:
            result = await tool_fn.ainvoke(tc["args"])
            return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
        except Exception as exc:
            return f"Tool error: {exc}"
