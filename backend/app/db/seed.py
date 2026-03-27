"""
Database seeding for dev / demo mode.

Activate by setting the environment variable  SEED_DB=true  (or 1 / yes).
The seeding theme is controlled by  SEED_THEME  (default: ``pandemic``).
In production leave SEED_DB unset (defaults to false) so the seeding is
never executed.

Each theme lives in its own module under ``app/db/themes/``.  Adding a new
theme requires only creating a new module that exposes a ``theme`` attribute
of type :class:`app.db.themes.SeedTheme`.
"""
import importlib
import logging

from app.config import get_settings
from app.db.chroma_client import add_documents
from app.db.graphdb_client import ensure_repository, load_turtle_into_graph
from app.db.neo4j_client import run_query
from app.db.postgis_client import run_write_query
from app.db.themes import SeedTheme

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Theme loader
# ---------------------------------------------------------------------------

def _load_theme(name: str) -> SeedTheme:
    """Import ``app.db.themes.<name>`` and return its ``theme`` object.

    Raises
    ------
    ValueError
        When the module does not exist or does not expose a ``theme``
        attribute of the expected type.
    """
    module_path = f"app.db.themes.{name}"
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        raise ValueError(
            f"Unknown seed theme '{name}'. "
            f"Create app/db/themes/{name}.py to add it."
        ) from exc

    theme = getattr(module, "theme", None)
    if not isinstance(theme, SeedTheme):
        raise ValueError(
            f"Module '{module_path}' must expose a 'theme' attribute "
            f"of type SeedTheme."
        )
    return theme


# ---------------------------------------------------------------------------
# Per-datastore seeders
# ---------------------------------------------------------------------------

async def _seed_neo4j(theme: SeedTheme) -> None:
    logger.info("Seeding Neo4j (%s) …", theme.name)
    for statement in theme.neo4j_statements:
        await run_query(statement)
    logger.info("Neo4j seeded (%s).", theme.name)


async def _seed_postgis(theme: SeedTheme) -> None:
    logger.info("Seeding PostGIS (%s) …", theme.name)
    for statement in theme.postgis_statements:
        await run_write_query(statement)
    logger.info("PostGIS seeded (%s).", theme.name)


async def _seed_graphdb(theme: SeedTheme) -> None:
    if not theme.graphdb_turtle:
        logger.debug("Theme '%s' has no GraphDB data – skipping.", theme.name)
        return
    logger.info("Seeding GraphDB (%s) …", theme.name)
    await ensure_repository()
    await load_turtle_into_graph(theme.graphdb_turtle, theme.graphdb_named_graph)
    logger.info("GraphDB seeded (%s).", theme.name)


async def _seed_chroma(theme: SeedTheme) -> None:
    if not theme.chroma_documents:
        logger.debug("Theme '%s' has no ChromaDB documents – skipping.", theme.name)
        return
    logger.info("Seeding ChromaDB (%s) …", theme.name)
    texts = [doc["text"] for doc in theme.chroma_documents]
    metadatas = [doc.get("metadata", {}) for doc in theme.chroma_documents]
    await add_documents(texts, metadatas)
    logger.info("ChromaDB seeded (%s, %d documents).", theme.name, len(texts))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def seed_all() -> None:
    """Load the configured theme and seed all datastores.

    Called at startup when ``SEED_DB=true``.  The active theme is read from
    ``SEED_THEME`` (default: ``pandemic``).
    """
    settings = get_settings()
    theme_name = settings.seed_theme
    logger.info("Loading seed theme '%s' …", theme_name)
    theme = _load_theme(theme_name)

    await _seed_neo4j(theme)
    await _seed_postgis(theme)
    await _seed_graphdb(theme)
    await _seed_chroma(theme)

    logger.info("All datastores seeded successfully (theme: '%s').", theme_name)
