# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import asyncio
import json
import logging

from app.config import get_settings
from app.pangiagent.memory import get_redis
from app.models import HITLRequest, ChoiceRequest, ChoiceResponse

logger = logging.getLogger(__name__)


class HITLManager:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._futures: dict[str, asyncio.Future] = {}
        # Per-session queues: SSE layer subscribes to receive choice_request events
        # that are fired from inside a sub-agent during fan-out execution.
        self._session_queues: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        """Register *queue* to receive choice notifications for *session_id*."""
        self._session_queues.setdefault(session_id, []).append(queue)

    def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        queues = self._session_queues.get(session_id, [])
        if queue in queues:
            queues.remove(queue)

    async def create_request(self, request: HITLRequest) -> None:
        r = get_redis()
        await r.set(
            f"hitl:{request.request_id}",
            request.model_dump_json(),
            ex=self._settings.hitl_timeout_seconds + 60,
        )
        self._futures[request.request_id] = asyncio.get_running_loop().create_future()

    async def wait_for_response(self, request_id: str) -> str | None:
        future = self._futures.get(request_id)
        if future is None:
            return None
        try:
            result = await asyncio.wait_for(
                asyncio.shield(future),
                timeout=self._settings.hitl_timeout_seconds,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning("HITL timeout for request %s", request_id)
            return None
        finally:
            self._futures.pop(request_id, None)

    async def respond(self, request_id: str, clarified_query: str) -> bool:
        r = get_redis()
        raw = await r.get(f"hitl:{request_id}")
        if not raw:
            return False
        data = json.loads(raw)
        data["status"] = "answered"
        data["clarified_query"] = clarified_query
        await r.set(f"hitl:{request_id}", json.dumps(data), ex=300)
        future = self._futures.get(request_id)
        if future and not future.done():
            future.set_result(clarified_query)
        return True

    # ── Choice requests (agent-level disambiguation) ───────────────────────────

    async def create_choice_request(self, request: ChoiceRequest) -> None:
        r = get_redis()
        await r.set(
            f"choice:{request.request_id}",
            request.model_dump_json(),
            ex=self._settings.hitl_timeout_seconds + 60,
        )
        self._futures[request.request_id] = asyncio.get_running_loop().create_future()
        # Notify any SSE streams watching this session
        for q in self._session_queues.get(request.session_id, []):
            await q.put(("choice_request", request))

    async def wait_for_choice(self, request_id: str) -> ChoiceResponse | None:
        future = self._futures.get(request_id)
        if future is None:
            return None
        try:
            result = await asyncio.wait_for(
                asyncio.shield(future),
                timeout=self._settings.hitl_timeout_seconds,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning("Choice timeout for request %s", request_id)
            return None
        finally:
            self._futures.pop(request_id, None)

    async def resolve_choice(self, response: ChoiceResponse) -> bool:
        r = get_redis()
        raw = await r.get(f"choice:{response.request_id}")
        if not raw:
            return False
        data = json.loads(raw)
        data["status"] = "answered"
        data["chosen_id"] = response.chosen_id
        data["chosen_query"] = response.chosen_query
        await r.set(f"choice:{response.request_id}", json.dumps(data), ex=300)
        future = self._futures.get(response.request_id)
        if future and not future.done():
            future.set_result(response)
        return True


_hitl_manager: HITLManager | None = None


def get_hitl_manager() -> HITLManager:
    global _hitl_manager
    if _hitl_manager is None:
        _hitl_manager = HITLManager()
    return _hitl_manager
