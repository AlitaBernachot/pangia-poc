"""
GraphDB (Ontotext) SPARQL client.

Uses httpx for async HTTP requests to the SPARQL endpoint.
"""
import json

import httpx

from app.config import get_settings


def _sparql_url() -> str:
    """Return the SPARQL endpoint URL for the configured GraphDB repository.

    Both SELECT and CONSTRUCT queries are served by the same endpoint;
    the query type is conveyed in the request body.
    """
    settings = get_settings()
    repo = settings.graphdb_repository
    base = settings.graphdb_url.rstrip("/")
    return f"{base}/repositories/{repo}"


async def run_sparql_select(sparql: str) -> str:
    """Execute a SPARQL SELECT query; returns JSON-formatted bindings."""
    url = _sparql_url()
    headers = {"Accept": "application/sparql-results+json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            data={"query": sparql},
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

    bindings = data.get("results", {}).get("bindings", [])
    if not bindings:
        return "SPARQL SELECT returned no results."

    # Flatten bindings to plain dicts
    rows = [
        {k: v.get("value", "") for k, v in row.items()}
        for row in bindings
    ]
    return json.dumps(rows, indent=2, ensure_ascii=False)


async def run_sparql_construct(sparql: str) -> str:
    """Execute a SPARQL CONSTRUCT query; returns Turtle-formatted triples."""
    url = _sparql_url()
    headers = {"Accept": "text/turtle"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            data={"query": sparql},
            headers=headers,
        )
        response.raise_for_status()
        text = response.text

    return text if text.strip() else "SPARQL CONSTRUCT returned no triples."
