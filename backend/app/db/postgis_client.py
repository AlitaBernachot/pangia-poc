"""
PostGIS (PostgreSQL) async client.

Uses asyncpg with a connection pool.  All queries are executed inside
read-only transactions to prevent any mutations.

`asyncpg` is imported lazily (inside each function) so the rest of the
application starts up even when the package is not yet installed.
"""
import json
from decimal import Decimal

from app.config import get_settings

_pool = None


def _asyncpg():
    """Lazy import of the asyncpg package."""
    try:
        import asyncpg  # noqa: PLC0415
        return asyncpg
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The 'asyncpg' package is required for the PostGIS agent. "
            "Add it to requirements.txt and rebuild the Docker image."
        ) from exc


async def get_pool():
    global _pool
    if _pool is None:
        asyncpg = _asyncpg()
        settings = get_settings()
        _pool = await asyncpg.create_pool(
            dsn=settings.postgis_dsn,
            min_size=1,
            max_size=5,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _serialize(value):
    """JSON-serialise asyncpg-specific types.

    asyncpg may return Decimal (for NUMERIC columns) or custom geometry
    objects (for PostGIS columns).  Decimal is cast to float; everything
    else falls back to str so the caller always receives valid JSON.
    """
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


async def run_spatial_query(sql: str, params: list | None = None) -> str:
    """Execute a read-only spatial SQL query and return JSON results.

    The query runs inside a read-only transaction; any attempt to mutate data
    will raise an error at the database level.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            rows = await conn.fetch(sql, *(params or []))

    if not rows:
        return "PostGIS query returned no rows."

    records = [dict(row) for row in rows]
    return json.dumps(records, default=_serialize, indent=2, ensure_ascii=False)
