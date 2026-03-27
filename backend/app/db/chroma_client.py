"""
ChromaDB vector store client.

Uses the official chromadb async HTTP client to connect to a running
Chroma server (configured via CHROMA_HOST / CHROMA_PORT).

`chromadb` is imported lazily (inside each function) so the rest of the
application starts up even when the package is not yet installed.
"""
import json
import os
from typing import Optional

# Disable chromadb telemetry before any chromadb import to avoid the
# "capture() takes 1 positional argument but 3 were given" bug in 0.5.x.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY", "False")

from app.config import get_settings

_client = None
_COLLECTION_NAME = "pangia_geo"


def _chroma():
    """Lazy import of the chromadb package."""
    try:
        import chromadb  # noqa: PLC0415
        return chromadb
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The 'chromadb' package is required for the Vector agent. "
            "Add it to requirements.txt and rebuild the Docker image."
        ) from exc


async def _get_client():
    global _client
    if _client is None:
        chroma = _chroma()
        from chromadb.config import Settings as ChromaSettings  # noqa: PLC0415
        settings = get_settings()
        _client = await chroma.AsyncHttpClient(
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
    import hashlib  # noqa: PLC0415
    collection = await _get_collection()
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
