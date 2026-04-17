# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import AsyncGenerator, Any

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.audit import get_audit
from app.config import get_settings
from app.hitl import get_hitl_manager
from app.memory import LongTermMemory, ShortTermMemory
from app.models import AgentInput, AgentOutput, ExecutionPlan, HITLRequest
from app.router import DynamicRouter

logger = logging.getLogger(__name__)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


class AmbiguityDetector:
    def __init__(self) -> None:
        settings = get_settings()
        self._llm = ChatOpenAI(
            model=settings.model_name,
            api_key=settings.openai_api_key,
            temperature=0.0,
        )
        self._threshold = settings.hitl_ambiguity_threshold

    async def detect(self, query: str) -> tuple[float, list[str]]:
        prompt = f"""Evaluate if the following query is ambiguous (score 0=clear, 1=very ambiguous).
Return JSON: {{"score": 0.0, "questions": ["clarifying question 1", ...]}}

Query: {query}

Return ONLY the JSON."""
        try:
            response = await self._llm.ainvoke([HumanMessage(content=prompt)])
            content = str(response.content).strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            data = json.loads(content)
            return float(data.get("score", 0.0)), list(data.get("questions", []))
        except Exception:
            logger.exception("AmbiguityDetector: failed to parse response")
            return 0.0, []

    @property
    def threshold(self) -> float:
        return self._threshold


class Orchestrator:
    def __init__(self, agents: dict[str, "BaseAgent"]) -> None:  # noqa: F821
        self._agents = agents
        self._router = DynamicRouter(agents)
        self._ltm = LongTermMemory()
        self._ambiguity = AmbiguityDetector()

    async def run(
        self, query: str, session_id: str
    ) -> AsyncGenerator[str, None]:
        audit = get_audit()
        stm = ShortTermMemory(session_id)
        hitl_manager = get_hitl_manager()

        await audit.log(session_id, "request_start", {"query": query})
        yield _sse({"type": "status", "message": "Processing your request..."})

        # Long-term memory retrieval
        try:
            facts = await self._ltm.search(query, top_k=5)
            if facts:
                yield _sse({"type": "memory_access", "facts": facts, "memory_type": "long_term"})
                await audit.log(session_id, "memory_access", {"facts": facts, "type": "long_term"})
        except Exception:
            logger.exception("LTM search failed")
            facts = []

        # Short-term memory
        stm_data = await stm.load()
        if stm_data:
            yield _sse({"type": "memory_access", "data": stm_data, "memory_type": "short_term"})

        context: dict[str, Any] = {"long_term_facts": facts, "short_term": stm_data}

        # Ambiguity detection → HITL
        ambiguity_score, questions = await self._ambiguity.detect(query)
        if ambiguity_score >= self._ambiguity.threshold and questions:
            hitl_req = HITLRequest(
                session_id=session_id,
                original_query=query,
                context=context,
                clarifying_questions=questions,
            )
            await hitl_manager.create_request(hitl_req)
            await audit.log(
                session_id, "hitl_ambiguity_detected",
                {"score": ambiguity_score, "request_id": hitl_req.request_id}
            )
            yield _sse({
                "type": "hitl_request",
                "request_id": hitl_req.request_id,
                "questions": questions,
                "original_query": query,
            })

            clarified = await hitl_manager.wait_for_response(hitl_req.request_id)
            if clarified:
                await audit.log(session_id, "hitl_response_received", {"clarified_query": clarified})
                yield _sse({"type": "hitl_resolved", "clarified_query": clarified})
                query = clarified
            else:
                await audit.log(session_id, "hitl_timeout", {"request_id": hitl_req.request_id})
                yield _sse({"type": "hitl_timeout", "message": "No response received within timeout."})
                yield _sse({"type": "final_answer", "answer": "Request timed out waiting for clarification."})
                yield _sse({"type": "done"})
                return

        # Dynamic routing
        plan: ExecutionPlan = await self._router.plan(query)
        await audit.log(session_id, "routing", {"plan": plan.model_dump()})
        yield _sse({
            "type": "routing_plan",
            "steps": [s.model_dump() for s in plan.steps],
            "reasoning": plan.reasoning,
        })

        # Group steps by parallel_group
        groups: dict[int, list[str]] = defaultdict(list)
        for step in plan.steps:
            groups[step.parallel_group].append(step.agent_name)

        all_outputs: list[AgentOutput] = []
        agent_input = AgentInput(query=query, session_id=session_id, context=context)

        for group_id in sorted(groups):
            agent_names = groups[group_id]
            yield _sse({"type": "parallel_group_start", "group": group_id, "agents": agent_names})

            tasks = []
            for name in agent_names:
                agent = self._agents.get(name)
                if agent:
                    tasks.append(self._run_agent(agent, agent_input, session_id))
                else:
                    logger.warning("Unknown agent: %s", name)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for name, result in zip(agent_names, results):
                if isinstance(result, Exception):
                    err_output = AgentOutput(
                        agent_name=name, answer="", confidence=0.0, error=str(result)
                    )
                    all_outputs.append(err_output)
                    yield _sse({"type": "agent_end", "agent": name, "error": str(result)})
                else:
                    all_outputs.append(result)
                    yield _sse({
                        "type": "agent_end",
                        "agent": result.agent_name,
                        "answer": result.answer[:500],
                        "confidence": result.confidence,
                        "duration_ms": result.state.get("duration_ms", 0),
                        "violations": result.state.get("post_guardrail_violations", []),
                    })

        # Merge results
        successful = [o for o in all_outputs if not o.error]
        combined_answer = "\n\n".join(
            f"[{o.agent_name}]: {o.answer}" for o in successful
        ) if successful else "No agents produced a valid answer."

        avg_confidence = (
            sum(o.confidence for o in successful) / len(successful)
            if successful else 0.0
        )

        # Store result in short-term memory
        await stm.update("last_answer", combined_answer[:2000])
        await stm.update("last_query", query)

        await audit.log(
            session_id, "request_end",
            {"answer_length": len(combined_answer), "confidence": avg_confidence}
        )

        yield _sse({
            "type": "final_answer",
            "answer": combined_answer,
            "confidence": avg_confidence,
        })
        yield _sse({"type": "done"})

    async def _run_agent(
        self, agent: "BaseAgent", inp: AgentInput, session_id: str  # noqa: F821
    ) -> AgentOutput:
        audit = get_audit()
        await audit.log(
            session_id, "agent_start", {"query": inp.query}, agent_name=agent.name
        )
        output = await agent.run(inp)
        await audit.log(
            session_id, "agent_end",
            {
                "answer_length": len(output.answer),
                "confidence": output.confidence,
                "error": output.error,
            },
            agent_name=agent.name,
        )
        return output
