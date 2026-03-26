"""
GraphDB (Ontotext) SPARQL client.

Uses httpx for async HTTP requests to the SPARQL endpoint.
"""
import asyncio
import json
import logging
from urllib.parse import quote

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# Maximum number of attempts when creating the GraphDB repository.
# Covers transient 500 errors that GraphDB emits while its internal state
# is still warming up even after the health-check passes.
_REPO_CREATE_MAX_ATTEMPTS = 5
_REPO_CREATE_RETRY_DELAY_S = 3


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
    """Create the GraphDB repository if it does not already exist.

    Retries up to ``_REPO_CREATE_MAX_ATTEMPTS`` times with a fixed delay
    between attempts to tolerate the transient HTTP 500 errors that GraphDB
    emits while its internal state finishes initialising even after its
    health-check endpoint reports ``200 OK``.

    Raises
    ------
    httpx.HTTPStatusError
        When all retry attempts are exhausted and GraphDB keeps returning a
        non-2xx response for the repository-creation request.
    RuntimeError
        When all retry attempts are exhausted but no HTTP response was
        received at all (e.g. connection refused on every attempt).
    """
    settings = get_settings()
    base = settings.graphdb_url.rstrip("/")
    repo = settings.graphdb_repository

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

    last_response: httpx.Response | None = None

    for attempt in range(1, _REPO_CREATE_MAX_ATTEMPTS + 1):
        async with httpx.AsyncClient(timeout=30.0) as client:
            # ── 1. Check whether the repository already exists ──────────────
            r = await client.get(f"{base}/rest/repositories/{repo}")
            if r.status_code == 200:
                return  # Repository already exists

            # ── 2. Try to create it ─────────────────────────────────────────
            response = await client.post(
                f"{base}/rest/repositories",
                content=ttl_config.encode(),
                headers={"Content-Type": "text/turtle"},
            )

            if response.is_success:
                logger.info(
                    "GraphDB repository '%s' created successfully (attempt %d/%d).",
                    repo,
                    attempt,
                    _REPO_CREATE_MAX_ATTEMPTS,
                )
                return

            # ── 3. Re-verify: GraphDB sometimes returns 500 even when the
            #       repository was actually created (race in its own code).
            verify = await client.get(f"{base}/rest/repositories/{repo}")
            if verify.status_code == 200:
                logger.warning(
                    "GraphDB returned HTTP %s when creating repository '%s' "
                    "(attempt %d/%d), but the repository is now accessible -- "
                    "continuing.",
                    response.status_code,
                    repo,
                    attempt,
                    _REPO_CREATE_MAX_ATTEMPTS,
                )
                return

            last_response = response

        # ── 4. Not yet ready; back off and retry ────────────────────────────
        if attempt < _REPO_CREATE_MAX_ATTEMPTS:
            logger.warning(
                "GraphDB repository creation failed "
                "(attempt %d/%d, HTTP %s) -- retrying in %ds ...\n"
                "Response body: %s",
                attempt,
                _REPO_CREATE_MAX_ATTEMPTS,
                last_response.status_code if last_response else "N/A",
                _REPO_CREATE_RETRY_DELAY_S,
                last_response.text if last_response else "",
            )
            await asyncio.sleep(_REPO_CREATE_RETRY_DELAY_S)

    # ── All attempts exhausted ───────────────────────────────────────────────
    logger.error(
        "GraphDB repository '%s' could not be created after %d attempts.\n"
        "Final response (HTTP %s): %s",
        repo,
        _REPO_CREATE_MAX_ATTEMPTS,
        last_response.status_code if last_response else "N/A",
        last_response.text if last_response else "N/A",
    )
    if last_response is not None:
        last_response.raise_for_status()
    raise RuntimeError(
        f"GraphDB repository '{repo}' could not be created after "
        f"{_REPO_CREATE_MAX_ATTEMPTS} attempts."
    )


async def load_turtle_into_graph(turtle_content: str, named_graph: str) -> None:
    """Replace a named graph with the provided Turtle RDF content.

    Uses a PUT request to the GraphDB statements endpoint, which atomically
    replaces all existing triples in the named graph (idempotent).

    Parameters
    ----------
    turtle_content:
        Valid Turtle-formatted RDF data to load into the graph.
    named_graph:
        The named-graph URI (e.g. ``"http://example.org/my-graph"``).
        The URI is automatically wrapped in angle brackets and URL-encoded
        before being sent to GraphDB.

    Raises
    ------
    httpx.HTTPStatusError
        When GraphDB returns a non-2xx response.
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
