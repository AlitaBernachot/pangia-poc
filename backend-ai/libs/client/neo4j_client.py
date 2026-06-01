# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""
Neo4j async client.

Uses the official neo4j Python driver with an async session.
All read-only queries are executed inside a read transaction to prevent mutations.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from neo4j import AsyncGraphDatabase, AsyncDriver

if TYPE_CHECKING:
    from app.config import Settings

_driver: AsyncDriver | None = None


async def get_driver(settings: "Settings | None" = None) -> AsyncDriver:
    """Return the shared async Neo4j driver, creating it on first call.

    Parameters
    ----------
    settings:
        Optional :class:`~app.config.Settings` instance.  When ``None``
        (default) :func:`~app.config.get_settings` is called so credentials
        are resolved from environment variables / ``.env``.  Pass an explicit
        ``Settings(...)`` to bypass env vars — useful in notebooks or tests.
    """
    global _driver
    if _driver is None:
        if settings is None:
            from app.config import get_settings  # noqa: PLC0415
            settings = get_settings()
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )
    return _driver


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def run_query(
    cypher: str,
    parameters: dict | None = None,
    settings: "Settings | None" = None,
) -> list[dict]:
    """Execute a Cypher query (read/write) and return a list of record dicts."""
    driver = await get_driver(settings)
    async with driver.session() as session:
        result = await session.run(cypher, parameters or {})
        return await result.data()


async def run_readonly_query(
    cypher: str,
    parameters: dict | None = None,
    settings: "Settings | None" = None,
) -> list[dict]:
    """Execute a Cypher query inside a read-only transaction to prevent mutations."""
    driver = await get_driver(settings)
    async with driver.session() as session:
        async def _work(tx):
            result = await tx.run(cypher, parameters or {})
            return await result.data()

        return await session.execute_read(_work)
