"""
ChromaDB vector store client.

Uses the official chromadb async HTTP client to connect to a running
Chroma server (configured via CHROMA_HOST / CHROMA_PORT).
"""
import json
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings

_client: chromadb.AsyncHttpClient | None = None
_COLLECTION_NAME = "pangia_geo"


async def _get_client() -> chromadb.AsyncHttpClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = await chromadb.AsyncHttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


async def _get_collection():
    client = await _get_client()
    return await client.get_or_create_collection(
        name=_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


async def similarity_search(query: str, n_results: int = 5) -> str:
    """Return the top-n documents most similar to *query*."""
    collection = await _get_collection()
    results = await collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    if not docs:
        return "No similar documents found in the vector store."

    hits = []
    for doc, meta, dist in zip(docs, metas, dists):
        hits.append({"document": doc, "metadata": meta, "distance": round(dist, 4)})
    return json.dumps(hits, indent=2, ensure_ascii=False)


async def add_documents(
    texts: list[str],
    metadatas: Optional[list[dict]] = None,
) -> str:
    """Add *texts* to the Chroma collection."""
    if not texts:
        return "No texts provided."
    collection = await _get_collection()
    import hashlib

    ids = [hashlib.sha256(t.encode()).hexdigest() for t in texts]
    await collection.add(
        documents=texts,
        ids=ids,
        metadatas=metadatas or [{} for _ in texts],
    )
    return f"Successfully added {len(texts)} document(s) to the vector store."


async def close_client() -> None:
    global _client
    _client = None
