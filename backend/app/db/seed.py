"""
Database seeding for dev / demo mode.

Activate by setting the environment variable  SEED_DB=true  (or 1 / yes).
In production leave SEED_DB unset (defaults to false) so the seeding is
never executed.

All statements use MERGE so the seeding is idempotent: running it a second
time does not create duplicates.
"""
import logging

from app.db.neo4j_client import run_query

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Neo4j – Knowledge-graph seed (Cypher)
# Each entry is a self-contained Cypher statement executed independently.
# ---------------------------------------------------------------------------

_NEO4J_STATEMENTS: list[str] = [
    # ── Dinosaur nodes ──────────────────────────────────────────────────────
    """
    MERGE (n:Dinosaur {name: 'Tyrannosaurus rex'})
    SET n.period    = 'Crétacé supérieur',
        n.diet      = 'carnivore',
        n.length_m  = 12.3,
        n.weight_kg = 8000,
        n.era_start = -68,
        n.era_end   = -66
    """,
    """
    MERGE (n:Dinosaur {name: 'Brachiosaurus'})
    SET n.period    = 'Jurassique supérieur',
        n.diet      = 'herbivore',
        n.length_m  = 22,
        n.weight_kg = 56000,
        n.era_start = -154,
        n.era_end   = -150
    """,
    """
    MERGE (n:Dinosaur {name: 'Velociraptor'})
    SET n.period    = 'Crétacé supérieur',
        n.diet      = 'carnivore',
        n.length_m  = 2,
        n.weight_kg = 15,
        n.era_start = -75,
        n.era_end   = -71
    """,
    """
    MERGE (n:Dinosaur {name: 'Archaeopteryx'})
    SET n.period    = 'Jurassique supérieur',
        n.diet      = 'carnivore',
        n.length_m  = 0.5,
        n.weight_kg = 1,
        n.era_start = -150,
        n.era_end   = -148
    """,
    """
    MERGE (n:Dinosaur {name: 'Diplodocus'})
    SET n.period    = 'Jurassique supérieur',
        n.diet      = 'herbivore',
        n.length_m  = 27,
        n.weight_kg = 15000,
        n.era_start = -154,
        n.era_end   = -152
    """,
    # ── Continent nodes ──────────────────────────────────────────────────────
    """
    MERGE (n:Continent {name: 'Pangée'})
    SET n.period_start = -335, n.period_end = -175
    """,
    """
    MERGE (n:Continent {name: 'Laurasia'})
    SET n.period_start = -175, n.period_end = -66
    """,
    """
    MERGE (n:Continent {name: 'Gondwana'})
    SET n.period_start = -175, n.period_end = -66
    """,
    """
    MERGE (n:Continent {name: 'Amérique du Nord'})
    SET n.period_start = -66, n.period_end = 0
    """,
    """
    MERGE (n:Continent {name: 'Europe'})
    SET n.period_start = -66, n.period_end = 0
    """,
    """
    MERGE (n:Continent {name: 'Afrique'})
    SET n.period_start = -66, n.period_end = 0
    """,
    """
    MERGE (n:Continent {name: 'Amérique du Sud'})
    SET n.period_start = -66, n.period_end = 0
    """,
    """
    MERGE (n:Continent {name: 'Asie'})
    SET n.period_start = -66, n.period_end = 0
    """,
    # ── Fossil-discovery site nodes ──────────────────────────────────────────
    """
    MERGE (n:Site {name: 'Hell Creek'})
    SET n.country = 'USA', n.lat = 46.9, n.lon = -101.5
    """,
    """
    MERGE (n:Site {name: 'Tendaguru'})
    SET n.country = 'Tanzanie', n.lat = -9.5, n.lon = 35.3
    """,
    """
    MERGE (n:Site {name: 'Djadokhta'})
    SET n.country = 'Mongolie', n.lat = 43.5, n.lon = 104.5
    """,
    """
    MERGE (n:Site {name: 'Solnhofen'})
    SET n.country = 'Allemagne', n.lat = 48.9, n.lon = 11.0
    """,
    # ── LOCATED_IN relations ─────────────────────────────────────────────────
    """
    MATCH (dino:Dinosaur {name: 'Tyrannosaurus rex'}),
          (cont:Continent {name: 'Amérique du Nord'})
    MERGE (dino)-[:LOCATED_IN {period: 'Crétacé supérieur'}]->(cont)
    """,
    """
    MATCH (dino:Dinosaur {name: 'Brachiosaurus'}),
          (cont:Continent {name: 'Gondwana'})
    MERGE (dino)-[:LOCATED_IN {period: 'Jurassique supérieur'}]->(cont)
    """,
    """
    MATCH (dino:Dinosaur {name: 'Velociraptor'}),
          (cont:Continent {name: 'Asie'})
    MERGE (dino)-[:LOCATED_IN {period: 'Crétacé supérieur'}]->(cont)
    """,
    """
    MATCH (dino:Dinosaur {name: 'Archaeopteryx'}),
          (cont:Continent {name: 'Europe'})
    MERGE (dino)-[:LOCATED_IN {period: 'Jurassique supérieur'}]->(cont)
    """,
    """
    MATCH (dino:Dinosaur {name: 'Diplodocus'}),
          (cont:Continent {name: 'Amérique du Nord'})
    MERGE (dino)-[:LOCATED_IN {period: 'Jurassique supérieur'}]->(cont)
    """,
    # ── MIGRATION relations ──────────────────────────────────────────────────
    """
    MATCH (dino:Dinosaur {name: 'Brachiosaurus'}),
          (cont:Continent {name: 'Gondwana'})
    MERGE (dino)-[:MIGRATED_FROM {period: 'Jurassique supérieur'}]->(cont)
    """,
    """
    MATCH (dino:Dinosaur {name: 'Brachiosaurus'}),
          (cont:Continent {name: 'Amérique du Nord'})
    MERGE (dino)-[:MIGRATED_TO {period: 'Jurassique supérieur'}]->(cont)
    """,
    # ── PREDATION relations ──────────────────────────────────────────────────
    """
    MATCH (pred:Dinosaur {name: 'Tyrannosaurus rex'}),
          (prey:Dinosaur {name: 'Brachiosaurus'})
    MERGE (pred)-[:PREYS_ON]->(prey)
    """,
    """
    MATCH (pred:Dinosaur {name: 'Velociraptor'}),
          (prey:Dinosaur {name: 'Archaeopteryx'})
    MERGE (pred)-[:PREYS_ON]->(prey)
    """,
    # ── COEXISTS_WITH relations ──────────────────────────────────────────────
    """
    MATCH (a:Dinosaur {name: 'Brachiosaurus'}),
          (b:Dinosaur {name: 'Diplodocus'})
    MERGE (a)-[:COEXISTS_WITH {period: 'Jurassique supérieur'}]->(b)
    """,
    """
    MATCH (a:Dinosaur {name: 'Tyrannosaurus rex'}),
          (b:Dinosaur {name: 'Velociraptor'})
    MERGE (a)-[:COEXISTS_WITH {period: 'Crétacé supérieur'}]->(b)
    """,
    # ── FOSSIL_DISCOVERED_IN relations ───────────────────────────────────────
    """
    MATCH (dino:Dinosaur {name: 'Tyrannosaurus rex'}),
          (site:Site {name: 'Hell Creek'})
    MERGE (dino)-[:FOSSIL_DISCOVERED_IN]->(site)
    """,
    """
    MATCH (dino:Dinosaur {name: 'Brachiosaurus'}),
          (site:Site {name: 'Tendaguru'})
    MERGE (dino)-[:FOSSIL_DISCOVERED_IN]->(site)
    """,
    """
    MATCH (dino:Dinosaur {name: 'Velociraptor'}),
          (site:Site {name: 'Djadokhta'})
    MERGE (dino)-[:FOSSIL_DISCOVERED_IN]->(site)
    """,
    """
    MATCH (dino:Dinosaur {name: 'Archaeopteryx'}),
          (site:Site {name: 'Solnhofen'})
    MERGE (dino)-[:FOSSIL_DISCOVERED_IN]->(site)
    """,
]


async def seed_neo4j() -> None:
    """Seed the Neo4j knowledge graph with sample dinosaur data."""
    logger.info("Seeding Neo4j knowledge graph …")
    for statement in _NEO4J_STATEMENTS:
        await run_query(statement)
    logger.info("Neo4j knowledge graph seeded successfully.")


async def seed_all() -> None:
    """Run all database seeds.  Called at startup when SEED_DB=true."""
    await seed_neo4j()
