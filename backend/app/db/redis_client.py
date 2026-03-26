import json
import redis.asyncio as aioredis
from app.config import get_settings

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = await aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def load_session(session_id: str) -> list[dict]:
    """Load conversation history from Redis."""
    redis = await get_redis()
    raw = await redis.get(f"session:{session_id}")
    if raw is None:
        return []
    return json.loads(raw)


async def save_session(session_id: str, messages: list[dict]) -> None:
    """Persist conversation history in Redis with TTL."""
    settings = get_settings()
    redis = await get_redis()
    await redis.setex(
        f"session:{session_id}",
        settings.session_ttl_seconds,
        json.dumps(messages),
    )
