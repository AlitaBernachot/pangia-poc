import json
from langchain_core.tools import tool
from app.db.neo4j_client import run_query, run_readonly_query


@tool
async def search_knowledge_graph(query: str) -> str:
    """
    Search the Neo4j knowledge graph using a natural-language query.
    The query is converted to a full-text or pattern search.
    Returns relevant nodes and relationships as JSON.
    """
    cypher = """
    CALL db.index.fulltext.queryNodes('entityIndex', $query)
    YIELD node, score
    WHERE score > 0.5
    OPTIONAL MATCH (node)-[r]->(related)
    RETURN
        labels(node)  AS nodeLabels,
        node          AS nodeProps,
        type(r)       AS relType,
        related       AS relatedProps
    LIMIT 10
    """
    try:
        records = await run_query(cypher, {"query": query})
        if not records:
            return "No relevant information found in the knowledge graph."
        return json.dumps(records, default=str)
    except Exception as exc:
        return f"Knowledge graph query failed: {exc}"


@tool
async def run_cypher_query(cypher: str) -> str:
    """
    Execute a read-only Cypher query against the Neo4j knowledge graph.
    Use this when you need precise structured data.
    Only MATCH/RETURN queries are executed; mutations are blocked at the
    driver level by using a read-only transaction.
    """
    try:
        records = await run_readonly_query(cypher)
        if not records:
            return "Query returned no results."
        return json.dumps(records, default=str)
    except Exception as exc:
        return f"Cypher query failed: {exc}"


TOOLS = [search_knowledge_graph, run_cypher_query]
