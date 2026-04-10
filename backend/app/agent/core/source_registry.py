"""
Source Registry – metadata declarations for all data-source connectors.

Each connector declares its capabilities, topics, entity types, geographic
scope, and example questions in a structured entry.  At application startup
these entries are embedded into a dedicated ChromaDB collection
(``pangia_source_registry``) so the Smart Dispatcher can perform semantic
similarity search on them at query time.

Adding a new source
-------------------
1. Append a :class:`SourceEntry` to :data:`SOURCE_REGISTRY`.
2. Make sure the ``connector`` value is a valid key in the orchestrator's
   ``_AGENT_NODES`` dict (i.e. a routable agent key such as ``"postgis"``).
3. Restart the application — the bootstrap will automatically index the new
   entry if it is not already present.

Capability vocabulary (used by the Smart Dispatcher for hard-rule scoring)
--------------------------------------------------------------------------
Spatial     : "spatial_query", "buffer", "intersection", "area", "distance",
              "coordinates", "geometry"
Graph       : "relationship", "graph_traversal", "entity_search",
              "co-occurrence", "hierarchy"
Semantic    : "semantic_search", "similarity", "document_retrieval", "embedding"
RDF/Linked  : "ontology", "linked_data", "sparql", "semantic_reasoning",
              "geosparql"
Open data   : "open_data", "official_statistics", "government_data",
              "french_datasets"
Geo analysis: "geocoding", "routing", "isochrone", "elevation", "viewshed",
              "hotspot", "temporal_analysis", "proximity"
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_REGISTRY_COLLECTION = "pangia_source_registry"


# ─── Data model ──────────────────────────────────────────────────────────────


class SourceEntry(BaseModel):
    """Metadata declaration for a single data-source connector."""

    id: str
    """Unique identifier — must match the connector's agent key (e.g. ``"postgis"``)."""

    connector: str
    """Agent key used in ``agents_to_call`` routing (e.g. ``"postgis"``, ``"neo4j"``)."""

    description: str
    """Human-readable description of what this source contains."""

    topics: list[str] = Field(default_factory=list)
    """Domain topics covered (e.g. ``["foncier", "urbanisme"]``)."""

    entity_types: list[str] = Field(default_factory=list)
    """Named entity types stored in this source (e.g. ``["parcelle", "bâtiment"]``)."""

    capabilities: list[str] = Field(default_factory=list)
    """Capability tags — see module docstring for the vocabulary."""

    geo_scope: str | None = None
    """Named geographic scope (e.g. ``"france"``, ``"commune_X"``).
    ``None`` means globally applicable (no spatial restriction)."""

    example_questions: list[str] = Field(default_factory=list)
    """Canonical example questions this source can answer."""


# ─── Default registry ─────────────────────────────────────────────────────────

SOURCE_REGISTRY: list[SourceEntry] = [
    SourceEntry(
        id="neo4j",
        connector="neo4j",
        description=(
            "Graphe de connaissances stockant les entités, leurs relations, "
            "les faits géographiques et les données historiques. Requêtes Cypher "
            "sur Neo4j. Idéal pour explorer des chaînes de relations complexes, "
            "des co-occurrences, des hiérarchies et des migrations d'entités."
        ),
        topics=["entités", "relations", "graphe", "connaissances", "faits", "hiérarchie"],
        entity_types=["entité", "lieu", "organisation", "événement", "personne", "territoire"],
        capabilities=["relationship", "graph_traversal", "entity_search", "co-occurrence", "hierarchy"],
        geo_scope=None,
        example_questions=[
            "Quels acteurs sont impliqués dans ce projet ?",
            "Qui finance cette initiative ?",
            "Quelles sont les relations entre ces entités ?",
            "Montrez-moi la chaîne de relations entre X et Y.",
        ],
    ),
    SourceEntry(
        id="rdf",
        connector="rdf",
        description=(
            "Triplestore RDF (GraphDB / Ontotext) contenant des ontologies "
            "géospatiales et des données liées. Requêtes SPARQL et GeoSPARQL. "
            "Idéal pour le raisonnement sémantique, les données liées et les "
            "relations ontologiques."
        ),
        topics=["ontologie", "données liées", "sémantique", "RDF", "linked data"],
        entity_types=["concept", "classe", "instance", "propriété"],
        capabilities=["ontology", "linked_data", "sparql", "semantic_reasoning", "geosparql"],
        geo_scope=None,
        example_questions=[
            "Quels sont les types d'occupation du sol dans cette région ?",
            "Définissez la relation entre ces deux concepts géographiques.",
            "Listez toutes les instances de la classe 'Zone protégée'.",
        ],
    ),
    SourceEntry(
        id="vector",
        connector="vector",
        description=(
            "Base de données vectorielle ChromaDB contenant des documents "
            "géographiques, des descriptions et des faits sous forme d'embeddings. "
            "Recherche par similarité sémantique. Idéal pour les questions ouvertes, "
            "la recherche documentaire et les questions descriptives générales."
        ),
        topics=["documents", "texte", "descriptions", "géographie", "sémantique"],
        entity_types=["document", "fragment", "description", "fiche"],
        capabilities=["semantic_search", "similarity", "document_retrieval", "embedding"],
        geo_scope=None,
        example_questions=[
            "Parlez-moi de cette espèce.",
            "Quels documents parlent de la biodiversité en Bretagne ?",
            "Qu'est-ce que je dois savoir sur ce territoire ?",
        ],
    ),
    SourceEntry(
        id="postgis",
        connector="postgis",
        description=(
            "Base de données spatiale PostgreSQL/PostGIS contenant les données "
            "géométriques, les coordonnées, les zones et les requêtes spatiales SQL. "
            "Idéal pour les calculs géométriques, les intersections, le calcul de "
            "surfaces, les distances et la récupération de coordonnées précises."
        ),
        topics=["géométrie", "coordonnées", "spatial", "zones", "surfaces", "distances"],
        entity_types=["point", "polygone", "ligne", "zone", "parcelle", "bâtiment"],
        capabilities=["spatial_query", "buffer", "intersection", "area", "distance", "coordinates", "geometry"],
        geo_scope=None,
        example_questions=[
            "Quelles entités se trouvent dans un rayon de 500 m ?",
            "Quelle est la surface de cette zone ?",
            "Où se trouvent les coordonnées de ce lieu ?",
            "Quelles parcelles intersectent cette zone ?",
        ],
    ),
    SourceEntry(
        id="data_gouv",
        connector="data_gouv",
        description=(
            "Catalogue open data du gouvernement français (data.gouv.fr) accessible "
            "via MCP. Contient des jeux de données officiels : statistiques "
            "publiques, données administratives, limites territoriales, "
            "données environnementales et tout ce qui est en open data français."
        ),
        topics=["open data", "statistiques", "gouvernement", "données publiques", "France", "officiel"],
        entity_types=["jeu de données", "ressource", "organisation", "thème"],
        capabilities=["open_data", "official_statistics", "government_data", "french_datasets"],
        geo_scope="france",
        example_questions=[
            "Quelles sont les données officielles sur la population de cette commune ?",
            "Trouvez des jeux de données sur la qualité de l'air en France.",
            "Quelles statistiques environnementales sont disponibles ?",
        ],
    ),
    SourceEntry(
        id="geo",
        connector="geo",
        description=(
            "Orchestrateur d'analyse géospatiale avancée. Regroupe le géocodage "
            "d'adresses, le calcul de distances, les zones tampon, les isochrones "
            "(zones d'accessibilité), la recherche de proximité, les intersections, "
            "le calcul de surfaces, la détection de clusters (hotspots), "
            "l'optimisation d'itinéraires, les profils d'élévation, les opérations "
            "sur les géométries GeoJSON, l'analyse spatio-temporelle et les calculs "
            "de co-visibilité (viewshed)."
        ),
        topics=["géocodage", "distance", "buffer", "isochrone", "proximité", "itinéraire", "altitude"],
        entity_types=["adresse", "coordonnées", "zone tampon", "isochrone", "itinéraire"],
        capabilities=[
            "geocoding", "routing", "isochrone", "elevation", "viewshed",
            "hotspot", "temporal_analysis", "proximity", "buffer", "area",
            "distance", "coordinates",
        ],
        geo_scope=None,
        example_questions=[
            "Géocodez cette adresse.",
            "Quelle est la distance entre ces deux points ?",
            "Calculez l'isochrone de 15 minutes à pied depuis ce lieu.",
            "Quel est l'itinéraire le plus court entre ces points ?",
            "Quelle est l'altitude de ce sommet ?",
        ],
    ),
]


# ─── ChromaDB bootstrap ───────────────────────────────────────────────────────


def _doc_for_entry(entry: SourceEntry) -> str:
    """Build the text document to embed for a source entry."""
    parts = [entry.description]
    if entry.topics:
        parts.append("Topics : " + ", ".join(entry.topics))
    if entry.entity_types:
        parts.append("Entités : " + ", ".join(entry.entity_types))
    if entry.capabilities:
        parts.append("Capacités : " + ", ".join(entry.capabilities))
    if entry.example_questions:
        parts.append("Exemples : " + " | ".join(entry.example_questions))
    return "\n".join(parts)


async def bootstrap_registry_embeddings() -> None:
    """Embed all source entries into the dedicated ChromaDB collection.

    This is idempotent: entries whose SHA-256 content hash has not changed
    since the last run are skipped.  New or modified entries are upserted.
    Call this once at application startup.
    """
    try:
        from app.db.chroma_client import get_chroma_client  # noqa: PLC0415
        client = await get_chroma_client()
        collection = await client.get_or_create_collection(
            name=_REGISTRY_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict[str, Any]] = []

        for entry in SOURCE_REGISTRY:
            doc = _doc_for_entry(entry)
            doc_hash = hashlib.sha256(doc.encode()).hexdigest()
            ids.append(entry.id)
            docs.append(doc)
            metas.append({
                "connector": entry.connector,
                "topics": json.dumps(entry.topics),
                "capabilities": json.dumps(entry.capabilities),
                "entity_types": json.dumps(entry.entity_types),
                "geo_scope": entry.geo_scope or "",
                "hash": doc_hash,
            })

        # Upsert all (ChromaDB deduplicates by id+content internally)
        await collection.upsert(documents=docs, ids=ids, metadatas=metas)
        logger.info(
            "Source registry bootstrapped: %d entries in '%s'.",
            len(SOURCE_REGISTRY),
            _REGISTRY_COLLECTION,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Source registry bootstrap failed (%s) — dispatcher will use hard rules only.", exc)


# ─── Semantic search ─────────────────────────────────────────────────────────


async def semantic_search_sources(query: str, n: int | None = None) -> dict[str, float]:
    """Return a dict mapping source id → semantic similarity score [0.0–1.0].

    Uses cosine similarity against the embedded source descriptions.
    Falls back to an empty dict if ChromaDB is unavailable.

    Parameters
    ----------
    query:
        The user query or intent.intention text to match against.
    n:
        Maximum number of results.  Defaults to ``len(SOURCE_REGISTRY)``.
    """
    if n is None:
        n = len(SOURCE_REGISTRY)

    try:
        from app.db.chroma_client import get_chroma_client  # noqa: PLC0415
        client = await get_chroma_client()
        collection = await client.get_or_create_collection(
            name=_REGISTRY_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        results = await collection.query(
            query_texts=[query],
            n_results=min(n, len(SOURCE_REGISTRY)),
            include=["distances"],
        )
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        # cosine distance ∈ [0, 2] with Chroma; convert to similarity ∈ [0, 1]
        return {sid: max(0.0, 1.0 - dist) for sid, dist in zip(ids, distances)}
    except Exception as exc:  # noqa: BLE001
        logger.debug("Source registry semantic search failed (%s).", exc)
        return {}


# ─── Helpers ─────────────────────────────────────────────────────────────────


def get_registry() -> list[SourceEntry]:
    """Return the current source registry (safe copy)."""
    return list(SOURCE_REGISTRY)


def get_entry(source_id: str) -> SourceEntry | None:
    """Return the registry entry for *source_id*, or None if not found."""
    return next((e for e in SOURCE_REGISTRY if e.id == source_id), None)
