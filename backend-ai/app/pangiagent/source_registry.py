# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Source Registry — declarative agent capability manifest + ChromaDB bootstrap.

This module:
1. Loads ``backend-ai/config/source_registry.yml`` into a list of
   :class:`SourceEntry` objects (``SOURCE_REGISTRY``).
2. Bootstraps a dedicated ChromaDB collection (``pangiagent_source_registry``)
   by upserting one document per registry entry at startup.
3. Exposes an async ``semantic_search_sources(query)`` function that queries
   the collection and returns ``{source_id: cosine_similarity_score}`` dicts.

Design constraints
------------------
* This module **must not** import from ``app.pangiagent.agents`` to avoid
  circular imports (agents import from source_registry, not the other way).
* ChromaDB may be unavailable at startup — all ChromaDB calls are wrapped in
  try/except so that a missing/unreachable ChromaDB does not crash the process.
* The ChromaDB client is lazily initialised on first use (lazy singleton
  pattern matching ``get_redis()`` in ``app.pangiagent.memory``).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from app.config import get_settings

logger = logging.getLogger(__name__)

# Resolves to backend-ai/config/source_registry.yml
# Path: backend-ai/app/pangiagent/source_registry.py
#   → parent.parent.parent.parent = backend-ai/
_REGISTRY_FILE = Path(__file__).parent.parent.parent / "config" / "source_registry.yml"

_COLLECTION_NAME = "pangiagent_source_registry"

# Lazy ChromaDB async client singleton
_chroma_client: Any | None = None


# ── Pydantic model ─────────────────────────────────────────────────────────────

class SourceEntry(BaseModel):
    """One entry in the source registry."""

    id: str
    connector: str
    active: bool = True
    label: str
    description: str
    topics: list[str] = Field(default_factory=list)
    entity_types: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    geo_scope: str | None = None
    example_questions: list[str] = Field(default_factory=list)


# ── YAML loader ────────────────────────────────────────────────────────────────

def _load_registry() -> list[SourceEntry]:
    """Read ``config/source_registry.yml`` and return a list of :class:`SourceEntry`.

    Returns an empty list (with a warning) when the file is missing or
    malformed so the service can still start without ChromaDB-backed routing.
    """
    if not _REGISTRY_FILE.exists():
        logger.warning(
            "source_registry: %s not found — SmartDispatcherAgent will have no entries",
            _REGISTRY_FILE,
        )
        return []
    try:
        with _REGISTRY_FILE.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        raw_sources = data.get("sources", [])
        entries = [SourceEntry(**s) for s in raw_sources]
        logger.debug("source_registry: loaded %d entries from %s", len(entries), _REGISTRY_FILE)
        return entries
    except Exception:
        logger.exception("source_registry: failed to load %s — using empty registry", _REGISTRY_FILE)
        return []


def _load_suggestions() -> list[str]:
    """Read the top-level ``suggestions`` list from ``config/source_registry.yml``."""
    if not _REGISTRY_FILE.exists():
        return []
    try:
        with _REGISTRY_FILE.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return [str(s) for s in data.get("suggestions", [])]
    except Exception:
        logger.exception("source_registry: failed to load suggestions from %s", _REGISTRY_FILE)
        return []


# ── Module-level registry (populated at import time) ──────────────────────────

SOURCE_REGISTRY: list[SourceEntry] = _load_registry()
_SUGGESTIONS: list[str] = _load_suggestions()


# ── ChromaDB client helpers ───────────────────────────────────────────────────

async def _get_chroma_client() -> Any:
    """Return a lazily-initialised async ChromaDB HTTP client.

    Returns ``chromadb.AsyncClientAPI`` but typed as ``Any`` to avoid a hard
    import of ``chromadb`` at module load time (ChromaDB is an optional
    runtime dependency that may fail to import before the container is ready).
    """
    global _chroma_client
    if _chroma_client is None:
        import chromadb  # noqa: PLC0415 (local import to avoid hard dependency at module load)
        settings = get_settings()
        _chroma_client = await chromadb.AsyncHttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
    return _chroma_client


def _build_document(entry: SourceEntry) -> str:
    """Concatenate all textual fields into a single embeddable document."""
    parts = [entry.description.strip()]
    if entry.topics:
        parts.append("Topics: " + ", ".join(entry.topics))
    if entry.entity_types:
        parts.append("Entity types: " + ", ".join(entry.entity_types))
    if entry.capabilities:
        parts.append("Capabilities: " + ", ".join(entry.capabilities))
    if entry.example_questions:
        parts.append("Example questions:\n" + "\n".join(f"- {q}" for q in entry.example_questions))
    return "\n".join(parts)


# ── Public API ────────────────────────────────────────────────────────────────

async def bootstrap_registry_embeddings() -> None:
    """Upsert all registry entries into the ChromaDB source-registry collection.

    This function is idempotent — calling it multiple times is safe because
    it uses ``upsert`` (insert or replace by ``id``).  It is intended to be
    called once during application startup (``lifespan`` in ``main.py``).

    Failures are silenced: a warning is logged and execution continues so
    that a missing ChromaDB does not prevent the application from starting.
    """
    if not SOURCE_REGISTRY:
        logger.warning("source_registry: empty registry — skipping ChromaDB bootstrap")
        return
    try:
        client = await _get_chroma_client()
        collection = await client.get_or_create_collection(name=_COLLECTION_NAME)
        active_entries = [e for e in SOURCE_REGISTRY if e.active]
        ids = [entry.id for entry in active_entries]
        documents = [_build_document(entry) for entry in active_entries]
        await collection.upsert(ids=ids, documents=documents)
        logger.info(
            "source_registry: bootstrapped %d entries into ChromaDB collection '%s'",
            len(active_entries),
            _COLLECTION_NAME,
        )
    except Exception:
        logger.warning(
            "source_registry: ChromaDB bootstrap failed (ChromaDB may be unavailable) — "
            "SmartDispatcherAgent will fall back to keyword-only scoring",
            exc_info=True,
        )


async def semantic_search_sources(query: str) -> dict[str, float]:
    """Query the ChromaDB collection and return ``{source_id: similarity_score}``.

    Similarity scores are cosine similarities in ``[0, 1]``
    (computed as ``1 - cosine_distance``).

    Returns an empty dict on any failure so that SmartDispatcherAgent can
    continue with keyword-only scoring.
    """
    try:
        client = await _get_chroma_client()
        collection = await client.get_or_create_collection(name=_COLLECTION_NAME)
        n_results = min(len(SOURCE_REGISTRY), 10) if SOURCE_REGISTRY else 1
        results = await collection.query(
            query_texts=[query],
            n_results=n_results,
            include=["distances"],
        )
        ids: list[str] = results["ids"][0] if results.get("ids") else []
        distances: list[float] = results["distances"][0] if results.get("distances") else []
        # ChromaDB cosine distance is in [0, 1] (0 = identical, 1 = orthogonal)
        return {source_id: max(0.0, 1.0 - dist) for source_id, dist in zip(ids, distances)}
    except Exception:
        logger.debug(
            "source_registry: semantic_search_sources failed — returning empty scores",
            exc_info=True,
        )
        return {}


def get_registry() -> list[SourceEntry]:
    """Return only the active source registry entries."""
    return [e for e in SOURCE_REGISTRY if e.active]


def get_suggestions() -> list[str]:
    """Return the suggestion chips defined in ``config/source_registry.yml``."""
    return _SUGGESTIONS


def get_entry(source_id: str) -> SourceEntry | None:
    """Look up a single registry entry by its ``id`` field."""
    for entry in SOURCE_REGISTRY:
        if entry.id == source_id:
            return entry
    return None
