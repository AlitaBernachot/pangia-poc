"""
GraphDB (Ontotext) SPARQL client.

Uses httpx for async HTTP requests to the SPARQL endpoint.
"""
import json
from urllib.parse import quote

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


async def ensure_repository() -> None:
    """Create the GraphDB repository if it does not already exist."""
    settings = get_settings()
    base = settings.graphdb_url.rstrip("/")
    repo = settings.graphdb_repository

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{base}/rest/repositories/{repo}")
        if r.status_code == 200:
            return  # Repository already exists

        # Repository not found – create it with a minimal Turtle config.
        ttl_config = (
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
            "@prefix rep: <http://www.openrdf.org/config/repository#> .\n"
            "@prefix sr: <http://www.openrdf.org/config/repository/sail#> .\n"
            "@prefix sail: <http://www.openrdf.org/config/sail#> .\n"
            "@prefix graphdb: <http://www.ontotext.com/config/graphdb#> .\n\n"
            "[] a rep:Repository ;\n"
            f'   rep:repositoryID "{repo}" ;\n'
            '   rdfs:label "Pangia GeoIA" ;\n'
            "   rep:repositoryImpl [\n"
            '       rep:repositoryType "graphdb:FreeSailRepository" ;\n'
            "       sr:sailImpl [\n"
            '           sail:sailType "graphdb:FreeSail" ;\n'
            '           graphdb:ruleset "rdfsplus-optimized"\n'
            "       ]\n"
            "   ] .\n"
        )
        response = await client.post(
            f"{base}/rest/repositories",
            content=ttl_config.encode(),
            headers={"Content-Type": "text/turtle"},
        )
        response.raise_for_status()


async def load_turtle_into_graph(turtle_content: str, named_graph: str) -> None:
    """Replace a named graph with the provided Turtle RDF content.

    Uses a PUT request to the GraphDB statements endpoint, which atomically
    replaces all existing triples in the named graph (idempotent).
    """
    settings = get_settings()
    base = settings.graphdb_url.rstrip("/")
    repo = settings.graphdb_repository

    # GraphDB expects the context URI wrapped in angle brackets, URL-encoded.
    encoded_ctx = quote(f"<{named_graph}>", safe="")
    url = f"{base}/repositories/{repo}/statements?context={encoded_ctx}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.put(
            url,
            content=turtle_content.encode("utf-8"),
            headers={"Content-Type": "text/turtle"},
        )
        response.raise_for_status()


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
