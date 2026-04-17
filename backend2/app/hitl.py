# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import asyncio
import json
import logging

from app.config import get_settings
from app.memory import get_redis
from app.models import HITLRequest

logger = logging.getLogger(__name__)


class HITLManager:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._futures: dict[str, asyncio.Future] = {}

    async def create_request(self, request: HITLRequest) -> None:
        r = get_redis()
        await r.set(
            f"hitl:{request.request_id}",
            request.model_dump_json(),
            ex=self._settings.hitl_timeout_seconds + 60,
        )
        self._futures[request.request_id] = asyncio.get_event_loop().create_future()

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


_hitl_manager: HITLManager | None = None


def get_hitl_manager() -> HITLManager:
    global _hitl_manager
    if _hitl_manager is None:
        _hitl_manager = HITLManager()
    return _hitl_manager
