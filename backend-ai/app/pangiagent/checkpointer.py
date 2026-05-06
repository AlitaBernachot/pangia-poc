# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""LangGraph PostgreSQL checkpointer lifecycle management.

The checkpointer persists the full orchestrator graph state between turns,
enabling multi-turn conversations without any custom Redis-based STM.

Usage
-----
- Call ``await init_checkpointer()`` once at application startup.
- Call ``await close_checkpointer()`` at application shutdown.
- Call ``get_checkpointer()`` (sync) anywhere to retrieve the singleton.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_pool: Any = None
_checkpointer: Any = None


def get_checkpointer() -> Any:
    """Return the initialised :class:`AsyncPostgresSaver` instance.

    Raises ``RuntimeError`` when called before ``init_checkpointer()``.
    """
    if _checkpointer is None:
        raise RuntimeError(
            "Checkpointer not initialised — call await init_checkpointer() at startup."
        )
    return _checkpointer


async def init_checkpointer() -> None:
    """Create the connection pool, checkpointer, and run DDL setup once."""
    global _pool, _checkpointer
    if _checkpointer is not None:
        return  # already initialised

    from psycopg_pool import AsyncConnectionPool
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from app.config import get_settings

    settings = get_settings()
    # Convert asyncpg DSN → psycopg3 format
    dsn = settings.postgres_dsn.replace("postgresql+asyncpg://", "postgresql://")

    logger.info("Checkpointer: opening PostgreSQL connection pool…")
    _pool = AsyncConnectionPool(
        conninfo=dsn,
        min_size=1,
        max_size=10,
        kwargs={"autocommit": True, "prepare_threshold": 0},
        open=False,
    )
    await _pool.open()

    _checkpointer = AsyncPostgresSaver(_pool)
    # Creates checkpoint_* tables if they don't already exist.
    await _checkpointer.setup()
    logger.info("Checkpointer: ready (PostgreSQL-backed LangGraph state persistence)")


async def close_checkpointer() -> None:
    """Close the connection pool on application shutdown."""
    global _pool, _checkpointer
    if _pool is not None:
        logger.info("Checkpointer: closing connection pool…")
        await _pool.close()
        _pool = None
        _checkpointer = None
