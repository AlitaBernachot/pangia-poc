# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import text

from app.config import get_settings
from app.db import get_session_factory

logger = logging.getLogger(__name__)

_EMBEDDING_DIM = 1536  # text-embedding-3-small output dimension

_redis_pool: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        settings = get_settings()
        _redis_pool = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_pool


async def close_redis() -> None:
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


# ── Short-term memory (Redis) ─────────────────────────────────────────────────

class ShortTermMemory:
    HISTORY_KEY = "conversation_history"
    MAX_TURNS = 3

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._key = f"session:{session_id}:short_memory"
        self._settings = get_settings()

    async def load(self) -> dict[str, Any]:
        r = get_redis()
        raw = await r.get(self._key)
        if raw:
            return json.loads(raw)
        return {}

    async def save(self, data: dict[str, Any]) -> None:
        r = get_redis()
        await r.set(self._key, json.dumps(data), ex=self._settings.session_ttl_seconds)

    async def update(self, key: str, value: Any) -> None:
        data = await self.load()
        data[key] = value
        await self.save(data)

    async def append_turn(self, query: str, answer: str) -> None:
        """Append a (query, answer) pair to the rolling conversation history.

        Keeps only the last :attr:`MAX_TURNS` turns.
        """
        data = await self.load()
        history: list[dict[str, str]] = data.get(self.HISTORY_KEY) or []
        history.append({"query": query, "answer": answer[:1200]})
        data[self.HISTORY_KEY] = history[-self.MAX_TURNS:]
        # Keep legacy keys in sync so older code doesn't break
        if history:
            data["last_query"] = history[-1]["query"]
            data["last_answer"] = history[-1]["answer"]
        await self.save(data)


# ── Long-term memory (PostgreSQL + pgvector) ──────────────────────────────────

class LongTermMemory:
    def __init__(self) -> None:
        self._settings = get_settings()

    async def add_fact(
        self, session_id: str, fact_text: str, metadata: dict[str, Any] | None = None
    ) -> None:
        embedding = await self._embed(fact_text)
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO long_term_memory (session_id, fact_text, embedding, metadata)
                    VALUES (:session_id, :fact_text, CAST(:embedding AS vector), CAST(:metadata AS jsonb))
                    """
                ),
                {
                    "session_id": session_id,
                    "fact_text": fact_text,
                    "embedding": str(embedding),
                    "metadata": json.dumps(metadata or {}),
                },
            )
            await session.commit()

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        embedding = await self._embed(query)
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT fact_text, metadata, 1 - (embedding <=> CAST(:embedding AS vector)) AS score
                    FROM long_term_memory
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT :top_k
                    """
                ),
                {"embedding": str(embedding), "top_k": top_k},
            )
            rows = result.fetchall()
        return [
            {"fact": row[0], "metadata": row[1], "score": float(row[2])}
            for row in rows
        ]

    async def _embed(self, text_: str) -> list[float]:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self._settings.openai_api_key)
            resp = await client.embeddings.create(
                model="text-embedding-3-small", input=text_
            )
            return resp.data[0].embedding
        except Exception:
            logger.exception("LongTermMemory: embedding failed, using zero vector")
            return [0.0] * _EMBEDDING_DIM
