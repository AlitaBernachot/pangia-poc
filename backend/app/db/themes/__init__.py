"""
Seed themes package.

Each sub-module defines a single ``SeedTheme`` instance named ``theme``
that carries all Neo4j, PostGIS and GraphDB seed data for that topic.

Available themes (value of the ``SEED_THEME`` env variable):
  - ``dinosaurs``  – Mesozoic palaeontology / Pangaea (default)

To add a new theme create ``themes/<name>.py`` with a ``theme`` attribute
of type :class:`SeedTheme`.
"""
from dataclasses import dataclass, field


@dataclass
class SeedTheme:
    """Container for all seed data belonging to a single theme.

    Attributes
    ----------
    name:
        Short identifier used in log messages (e.g. ``"dinosaurs"``).
    neo4j_statements:
        List of idempotent Cypher statements to run against Neo4j.
    postgis_statements:
        List of idempotent SQL statements (DDL + DML) to run against PostGIS.
    graphdb_named_graph:
        URI of the named graph that will receive the RDF triples.
    graphdb_turtle:
        Turtle-encoded RDF content loaded into *graphdb_named_graph*.
    """

    name: str
    neo4j_statements: list[str] = field(default_factory=list)
    postgis_statements: list[str] = field(default_factory=list)
    graphdb_named_graph: str = ""
    graphdb_turtle: str = ""
    neo4j_schema_prompt: str = ""
    postgis_schema_prompt: str = ""
    rdf_schema_prompt: str = ""


import importlib


def get_active_theme() -> "SeedTheme":
    """Load and return the SeedTheme for the currently configured SEED_THEME."""
    from app.config import get_settings  # local import to avoid circular dep

    settings = get_settings()
    module_path = f"app.db.themes.{settings.seed_theme}"
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        raise ValueError(
            f"Unknown seed theme '{settings.seed_theme}'. "
            f"Create app/db/themes/{settings.seed_theme}.py to add it."
        ) from exc
    theme = getattr(module, "theme", None)
    if not isinstance(theme, SeedTheme):
        raise ValueError(
            f"Module '{module_path}' must expose a 'theme' attribute "
            f"of type SeedTheme."
        )
    return theme
