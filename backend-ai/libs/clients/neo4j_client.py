# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""
Neo4j async client.

Uses the official neo4j Python driver with an async session.
All read-only queries are executed inside a read transaction to prevent mutations.
"""
from neo4j import AsyncGraphDatabase, AsyncDriver

from app.config import get_settings

_driver: AsyncDriver | None = None


async def get_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
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


async def run_query(cypher: str, parameters: dict | None = None) -> list[dict]:
    """Execute a Cypher query (read/write) and return a list of record dicts."""
    driver = await get_driver()
    async with driver.session() as session:
        result = await session.run(cypher, parameters or {})
        return await result.data()


async def run_readonly_query(cypher: str, parameters: dict | None = None) -> list[dict]:
    """Execute a Cypher query inside a read-only transaction to prevent mutations."""
    driver = await get_driver()
    async with driver.session() as session:
        async def _work(tx):
            result = await tx.run(cypher, parameters or {})
            return await result.data()

        return await session.execute_read(_work)
