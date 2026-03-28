"""
Seed theme: dinosaurs.

Mesozoic palaeontology data covering key fossil sites, dinosaur species,
paleo-geographic continents, and their spatial relationships across all
three supported datastores (Neo4j, PostGIS, GraphDB).
"""
from app.db.themes import SeedTheme

theme = SeedTheme(
    name="dinosaurs",

    neo4j_schema_prompt="""\
Node labels:
- Dinosaur   — properties: name, period, diet, length_m, weight_kg, era_start, era_end
- Site        — properties: name, country, lat, lon
- Continent   — properties: name, period_start, period_end

Relationship types:
- (Dinosaur)-[:FOSSIL_DISCOVERED_IN]->(Site)
- (Dinosaur)-[:LOCATED_IN {period}]->(Continent)
- (Dinosaur)-[:MIGRATED_FROM {period}]->(Continent)
- (Dinosaur)-[:MIGRATED_TO {period}]->(Continent)
- (Dinosaur)-[:PREYS_ON]->(Dinosaur)
- (Dinosaur)-[:COEXISTS_WITH {period}]->(Dinosaur)
""",

    postgis_schema_prompt="""\
Schema: dinosaures

Tables:
- dinosaures.fossil_sites(id, name, country, era, location_modern GEOMETRY(POINT,4326),
                          location_pangaea GEOMETRY(POINT,4326), dinosaurs_found TEXT[],
                          period_start INTEGER, period_end INTEGER)
- dinosaures.paleo_continents(id, name, period, geometry GEOMETRY(POLYGON,4326),
                               parent_continent VARCHAR)

Use PostGIS functions such as ST_Distance, ST_Contains, ST_Within, ST_Intersects,
ST_DWithin, ST_AsText, ST_X/ST_Y to answer spatial questions.
Distances are in metres (use /1000 to convert to km).
Always qualify table names with the schema: dinosaures.<table>.
""",

    rdf_schema_prompt="""\
Prefix: PREFIX : <http://pangia.io/ontology#>

Classes:
- :Dinosaur        — rdfs:label (string)
- :FossilSite      — rdfs:label (string)
- :PaleoContinent  — rdfs:label (string)

Object properties:
- :foundAtSite     (:Dinosaur → :FossilSite)
- :locatedIn       (:Dinosaur → :PaleoContinent)
- :subContinentOf  (:PaleoContinent → :PaleoContinent)
- :preysOn         (:Dinosaur → :Dinosaur)
- :coexistsWith    (:Dinosaur → :Dinosaur)

Data properties (all on :Dinosaur unless noted):
- :period (xsd:string), :diet (xsd:string),
  :lengthM (xsd:decimal), :weightKg (xsd:decimal),
  :eraStart (xsd:integer), :eraEnd (xsd:integer)
- :country (xsd:string) — on :FossilSite
- :modernLat, :modernLon, :pangaeaLat, :pangaeaLon (xsd:decimal) — on :FossilSite

Named graph: <http://pangia.io/graphs/dinosaurs>
Always add GRAPH <http://pangia.io/graphs/dinosaurs> { ... } in queries.
""",

    # ── Neo4j – Cypher statements ────────────────────────────────────────────
    neo4j_statements=[
        # Dinosaur nodes
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
        # Continent nodes
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
        # Fossil-discovery site nodes
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
        # LOCATED_IN relations
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
        # MIGRATION relations
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
        # PREDATION relations
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
        # COEXISTS_WITH relations
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
        # FOSSIL_DISCOVERED_IN relations
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

        # ── Additional dinosaur nodes ─────────────────────────────────────
        """
        MERGE (n:Dinosaur {name: 'Allosaurus'})
        SET n.period    = 'Jurassique supérieur',
            n.diet      = 'carnivore',
            n.length_m  = 9.0,
            n.weight_kg = 2300,
            n.era_start = -156,
            n.era_end   = -150
        """,
        """
        MERGE (n:Dinosaur {name: 'Stegosaurus'})
        SET n.period    = 'Jurassique supérieur',
            n.diet      = 'herbivore',
            n.length_m  = 9.0,
            n.weight_kg = 3500,
            n.era_start = -156,
            n.era_end   = -150
        """,
        """
        MERGE (n:Dinosaur {name: 'Triceratops'})
        SET n.period    = 'Crétacé supérieur',
            n.diet      = 'herbivore',
            n.length_m  = 9.0,
            n.weight_kg = 12000,
            n.era_start = -68,
            n.era_end   = -66
        """,
        """
        MERGE (n:Dinosaur {name: 'Ankylosaurus'})
        SET n.period    = 'Crétacé supérieur',
            n.diet      = 'herbivore',
            n.length_m  = 6.25,
            n.weight_kg = 6000,
            n.era_start = -68,
            n.era_end   = -66
        """,
        """
        MERGE (n:Dinosaur {name: 'Spinosaurus'})
        SET n.period    = 'Crétacé moyen',
            n.diet      = 'piscivore',
            n.length_m  = 15.0,
            n.weight_kg = 7000,
            n.era_start = -112,
            n.era_end   = -93
        """,
        """
        MERGE (n:Dinosaur {name: 'Protoceratops'})
        SET n.period    = 'Crétacé supérieur',
            n.diet      = 'herbivore',
            n.length_m  = 1.8,
            n.weight_kg = 177,
            n.era_start = -83,
            n.era_end   = -70
        """,
        """
        MERGE (n:Dinosaur {name: 'Iguanodon'})
        SET n.period    = 'Crétacé inférieur',
            n.diet      = 'herbivore',
            n.length_m  = 10.0,
            n.weight_kg = 3000,
            n.era_start = -140,
            n.era_end   = -100
        """,
        """
        MERGE (n:Dinosaur {name: 'Carnotaurus'})
        SET n.period    = 'Crétacé supérieur',
            n.diet      = 'carnivore',
            n.length_m  = 8.0,
            n.weight_kg = 1500,
            n.era_start = -72,
            n.era_end   = -69
        """,
        """
        MERGE (n:Dinosaur {name: 'Argentinosaurus'})
        SET n.period    = 'Crétacé supérieur',
            n.diet      = 'herbivore',
            n.length_m  = 35.0,
            n.weight_kg = 70000,
            n.era_start = -96,
            n.era_end   = -90
        """,
        """
        MERGE (n:Dinosaur {name: 'Parasaurolophus'})
        SET n.period    = 'Crétacé supérieur',
            n.diet      = 'herbivore',
            n.length_m  = 9.5,
            n.weight_kg = 2500,
            n.era_start = -76,
            n.era_end   = -73
        """,

        # Additional site nodes
        """
        MERGE (n:Site {name: 'Kem Kem Beds'})
        SET n.country = 'Maroc', n.lat = 30.5, n.lon = -4.5
        """,
        """
        MERGE (n:Site {name: 'Bernissart'})
        SET n.country = 'Belgique', n.lat = 50.5, n.lon = 3.7
        """,
        """
        MERGE (n:Site {name: 'Neuquén'})
        SET n.country = 'Argentine', n.lat = -38.9, n.lon = -68.1
        """,
        """
        MERGE (n:Site {name: 'Two Medicine Formation'})
        SET n.country = 'USA', n.lat = 48.3, n.lon = -112.5
        """,

        # LOCATED_IN – new dinosaurs
        """
        MATCH (dino:Dinosaur {name: 'Allosaurus'}),
              (cont:Continent {name: 'Amérique du Nord'})
        MERGE (dino)-[:LOCATED_IN {period: 'Jurassique supérieur'}]->(cont)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Stegosaurus'}),
              (cont:Continent {name: 'Amérique du Nord'})
        MERGE (dino)-[:LOCATED_IN {period: 'Jurassique supérieur'}]->(cont)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Triceratops'}),
              (cont:Continent {name: 'Amérique du Nord'})
        MERGE (dino)-[:LOCATED_IN {period: 'Crétacé supérieur'}]->(cont)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Ankylosaurus'}),
              (cont:Continent {name: 'Amérique du Nord'})
        MERGE (dino)-[:LOCATED_IN {period: 'Crétacé supérieur'}]->(cont)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Spinosaurus'}),
              (cont:Continent {name: 'Afrique'})
        MERGE (dino)-[:LOCATED_IN {period: 'Crétacé moyen'}]->(cont)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Protoceratops'}),
              (cont:Continent {name: 'Asie'})
        MERGE (dino)-[:LOCATED_IN {period: 'Crétacé supérieur'}]->(cont)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Iguanodon'}),
              (cont:Continent {name: 'Europe'})
        MERGE (dino)-[:LOCATED_IN {period: 'Crétacé inférieur'}]->(cont)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Carnotaurus'}),
              (cont:Continent {name: 'Amérique du Sud'})
        MERGE (dino)-[:LOCATED_IN {period: 'Crétacé supérieur'}]->(cont)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Argentinosaurus'}),
              (cont:Continent {name: 'Amérique du Sud'})
        MERGE (dino)-[:LOCATED_IN {period: 'Crétacé supérieur'}]->(cont)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Parasaurolophus'}),
              (cont:Continent {name: 'Amérique du Nord'})
        MERGE (dino)-[:LOCATED_IN {period: 'Crétacé supérieur'}]->(cont)
        """,

        # FOSSIL_DISCOVERED_IN – new dinosaurs
        """
        MATCH (dino:Dinosaur {name: 'Allosaurus'}),
              (site:Site {name: 'Morrison Formation'})
        MERGE (dino)-[:FOSSIL_DISCOVERED_IN]->(site)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Stegosaurus'}),
              (site:Site {name: 'Morrison Formation'})
        MERGE (dino)-[:FOSSIL_DISCOVERED_IN]->(site)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Triceratops'}),
              (site:Site {name: 'Hell Creek'})
        MERGE (dino)-[:FOSSIL_DISCOVERED_IN]->(site)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Ankylosaurus'}),
              (site:Site {name: 'Hell Creek'})
        MERGE (dino)-[:FOSSIL_DISCOVERED_IN]->(site)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Spinosaurus'}),
              (site:Site {name: 'Kem Kem Beds'})
        MERGE (dino)-[:FOSSIL_DISCOVERED_IN]->(site)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Protoceratops'}),
              (site:Site {name: 'Djadokhta'})
        MERGE (dino)-[:FOSSIL_DISCOVERED_IN]->(site)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Iguanodon'}),
              (site:Site {name: 'Bernissart'})
        MERGE (dino)-[:FOSSIL_DISCOVERED_IN]->(site)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Carnotaurus'}),
              (site:Site {name: 'Neuquén'})
        MERGE (dino)-[:FOSSIL_DISCOVERED_IN]->(site)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Argentinosaurus'}),
              (site:Site {name: 'Neuquén'})
        MERGE (dino)-[:FOSSIL_DISCOVERED_IN]->(site)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Parasaurolophus'}),
              (site:Site {name: 'Two Medicine Formation'})
        MERGE (dino)-[:FOSSIL_DISCOVERED_IN]->(site)
        """,
        """
        MATCH (dino:Dinosaur {name: 'Diplodocus'}),
              (site:Site {name: 'Morrison Formation'})
        MERGE (dino)-[:FOSSIL_DISCOVERED_IN]->(site)
        """,

        # PREYS_ON – extended
        """
        MATCH (pred:Dinosaur {name: 'Tyrannosaurus rex'}),
              (prey:Dinosaur {name: 'Triceratops'})
        MERGE (pred)-[:PREYS_ON]->(prey)
        """,
        """
        MATCH (pred:Dinosaur {name: 'Tyrannosaurus rex'}),
              (prey:Dinosaur {name: 'Ankylosaurus'})
        MERGE (pred)-[:PREYS_ON]->(prey)
        """,
        """
        MATCH (pred:Dinosaur {name: 'Tyrannosaurus rex'}),
              (prey:Dinosaur {name: 'Parasaurolophus'})
        MERGE (pred)-[:PREYS_ON]->(prey)
        """,
        """
        MATCH (pred:Dinosaur {name: 'Allosaurus'}),
              (prey:Dinosaur {name: 'Stegosaurus'})
        MERGE (pred)-[:PREYS_ON]->(prey)
        """,
        """
        MATCH (pred:Dinosaur {name: 'Allosaurus'}),
              (prey:Dinosaur {name: 'Diplodocus'})
        MERGE (pred)-[:PREYS_ON]->(prey)
        """,
        """
        MATCH (pred:Dinosaur {name: 'Allosaurus'}),
              (prey:Dinosaur {name: 'Brachiosaurus'})
        MERGE (pred)-[:PREYS_ON]->(prey)
        """,
        """
        MATCH (pred:Dinosaur {name: 'Velociraptor'}),
              (prey:Dinosaur {name: 'Protoceratops'})
        MERGE (pred)-[:PREYS_ON]->(prey)
        """,
        """
        MATCH (pred:Dinosaur {name: 'Carnotaurus'}),
              (prey:Dinosaur {name: 'Argentinosaurus'})
        MERGE (pred)-[:PREYS_ON]->(prey)
        """,

        # COEXISTS_WITH – extended
        """
        MATCH (a:Dinosaur {name: 'Allosaurus'}),
              (b:Dinosaur {name: 'Stegosaurus'})
        MERGE (a)-[:COEXISTS_WITH {period: 'Jurassique supérieur'}]->(b)
        """,
        """
        MATCH (a:Dinosaur {name: 'Allosaurus'}),
              (b:Dinosaur {name: 'Diplodocus'})
        MERGE (a)-[:COEXISTS_WITH {period: 'Jurassique supérieur'}]->(b)
        """,
        """
        MATCH (a:Dinosaur {name: 'Allosaurus'}),
              (b:Dinosaur {name: 'Brachiosaurus'})
        MERGE (a)-[:COEXISTS_WITH {period: 'Jurassique supérieur'}]->(b)
        """,
        """
        MATCH (a:Dinosaur {name: 'Triceratops'}),
              (b:Dinosaur {name: 'Tyrannosaurus rex'})
        MERGE (a)-[:COEXISTS_WITH {period: 'Crétacé supérieur'}]->(b)
        """,
        """
        MATCH (a:Dinosaur {name: 'Ankylosaurus'}),
              (b:Dinosaur {name: 'Tyrannosaurus rex'})
        MERGE (a)-[:COEXISTS_WITH {period: 'Crétacé supérieur'}]->(b)
        """,
        """
        MATCH (a:Dinosaur {name: 'Ankylosaurus'}),
              (b:Dinosaur {name: 'Triceratops'})
        MERGE (a)-[:COEXISTS_WITH {period: 'Crétacé supérieur'}]->(b)
        """,
        """
        MATCH (a:Dinosaur {name: 'Parasaurolophus'}),
              (b:Dinosaur {name: 'Triceratops'})
        MERGE (a)-[:COEXISTS_WITH {period: 'Crétacé supérieur'}]->(b)
        """,
        """
        MATCH (a:Dinosaur {name: 'Protoceratops'}),
              (b:Dinosaur {name: 'Velociraptor'})
        MERGE (a)-[:COEXISTS_WITH {period: 'Crétacé supérieur'}]->(b)
        """,
        """
        MATCH (a:Dinosaur {name: 'Carnotaurus'}),
              (b:Dinosaur {name: 'Argentinosaurus'})
        MERGE (a)-[:COEXISTS_WITH {period: 'Crétacé supérieur'}]->(b)
        """,
    ],

    # ── PostGIS – SQL statements ─────────────────────────────────────────────
    postgis_statements=[
        # Ensure the PostGIS extension is available
        "CREATE EXTENSION IF NOT EXISTS postgis",

        # Ensure the dinosaures schema exists
        "CREATE SCHEMA IF NOT EXISTS dinosaures",

        # fossil_sites table
        """
        CREATE TABLE IF NOT EXISTS dinosaures.fossil_sites (
            id               SERIAL PRIMARY KEY,
            name             VARCHAR(100) UNIQUE,
            country          VARCHAR(50),
            era              VARCHAR(50),
            location_modern  GEOMETRY(POINT, 4326),
            location_pangaea GEOMETRY(POINT, 4326),
            dinosaurs_found  TEXT[],
            period_start     INTEGER,
            period_end       INTEGER
        )
        """,

        # paleo_continents table
        """
        CREATE TABLE IF NOT EXISTS dinosaures.paleo_continents (
            id               SERIAL PRIMARY KEY,
            name             VARCHAR(50) UNIQUE,
            period           VARCHAR(50),
            geometry         GEOMETRY(POLYGON, 4326),
            parent_continent VARCHAR(50)
        )
        """,

        # fossil_sites rows
        """
        INSERT INTO dinosaures.fossil_sites
            (name, country, era, location_modern, location_pangaea,
             dinosaurs_found, period_start, period_end)
        VALUES
            ('Hell Creek', 'USA', 'Crétacé supérieur',
             ST_SetSRID(ST_MakePoint(-101.5, 46.9), 4326),
             ST_SetSRID(ST_MakePoint(-45.2, 35.0), 4326),
             ARRAY['Tyrannosaurus rex', 'Triceratops', 'Ankylosaurus'],
             -68, -66)
        ON CONFLICT (name) DO NOTHING
        """,
        """
        INSERT INTO dinosaures.fossil_sites
            (name, country, era, location_modern, location_pangaea,
             dinosaurs_found, period_start, period_end)
        VALUES
            ('Tendaguru', 'Tanzanie', 'Jurassique supérieur',
             ST_SetSRID(ST_MakePoint(35.3, -9.5), 4326),
             ST_SetSRID(ST_MakePoint(25.0, -25.0), 4326),
             ARRAY['Brachiosaurus', 'Giraffatitan', 'Kentrosaurus'],
             -154, -150)
        ON CONFLICT (name) DO NOTHING
        """,
        """
        INSERT INTO dinosaures.fossil_sites
            (name, country, era, location_modern, location_pangaea,
             dinosaurs_found, period_start, period_end)
        VALUES
            ('Djadokhta', 'Mongolie', 'Crétacé supérieur',
             ST_SetSRID(ST_MakePoint(104.5, 43.5), 4326),
             ST_SetSRID(ST_MakePoint(80.0, 35.0), 4326),
             ARRAY['Velociraptor', 'Protoceratops', 'Oviraptor'],
             -75, -71)
        ON CONFLICT (name) DO NOTHING
        """,
        """
        INSERT INTO dinosaures.fossil_sites
            (name, country, era, location_modern, location_pangaea,
             dinosaurs_found, period_start, period_end)
        VALUES
            ('Solnhofen', 'Allemagne', 'Jurassique supérieur',
             ST_SetSRID(ST_MakePoint(11.0, 48.9), 4326),
             ST_SetSRID(ST_MakePoint(20.0, 40.0), 4326),
             ARRAY['Archaeopteryx', 'Compsognathus', 'Pterodactylus'],
             -150, -148)
        ON CONFLICT (name) DO NOTHING
        """,
        """
        INSERT INTO dinosaures.fossil_sites
            (name, country, era, location_modern, location_pangaea,
             dinosaurs_found, period_start, period_end)
        VALUES
            ('Morrison Formation', 'USA', 'Jurassique supérieur',
             ST_SetSRID(ST_MakePoint(-108.0, 38.0), 4326),
             ST_SetSRID(ST_MakePoint(-50.0, 35.0), 4326),
             ARRAY['Diplodocus', 'Allosaurus', 'Stegosaurus'],
             -154, -152)
        ON CONFLICT (name) DO NOTHING
        """,
        """
        INSERT INTO dinosaures.fossil_sites
            (name, country, era, location_modern, location_pangaea,
             dinosaurs_found, period_start, period_end)
        VALUES
            ('Kem Kem Beds', 'Maroc', 'Crétacé moyen',
             ST_SetSRID(ST_MakePoint(-4.5, 30.5), 4326),
             ST_SetSRID(ST_MakePoint(10.0, 5.0), 4326),
             ARRAY['Spinosaurus', 'Carcharodontosaurus', 'Deltadromeus'],
             -112, -93)
        ON CONFLICT (name) DO NOTHING
        """,
        """
        INSERT INTO dinosaures.fossil_sites
            (name, country, era, location_modern, location_pangaea,
             dinosaurs_found, period_start, period_end)
        VALUES
            ('Bernissart', 'Belgique', 'Crétacé inférieur',
             ST_SetSRID(ST_MakePoint(3.7, 50.5), 4326),
             ST_SetSRID(ST_MakePoint(15.0, 42.0), 4326),
             ARRAY['Iguanodon'],
             -140, -100)
        ON CONFLICT (name) DO NOTHING
        """,
        """
        INSERT INTO dinosaures.fossil_sites
            (name, country, era, location_modern, location_pangaea,
             dinosaurs_found, period_start, period_end)
        VALUES
            ('Neuquén', 'Argentine', 'Crétacé supérieur',
             ST_SetSRID(ST_MakePoint(-68.1, -38.9), 4326),
             ST_SetSRID(ST_MakePoint(-55.0, -45.0), 4326),
             ARRAY['Argentinosaurus', 'Carnotaurus', 'Giganotosaurus'],
             -96, -69)
        ON CONFLICT (name) DO NOTHING
        """,
        """
        INSERT INTO dinosaures.fossil_sites
            (name, country, era, location_modern, location_pangaea,
             dinosaurs_found, period_start, period_end)
        VALUES
            ('Two Medicine Formation', 'USA', 'Crétacé supérieur',
             ST_SetSRID(ST_MakePoint(-112.5, 48.3), 4326),
             ST_SetSRID(ST_MakePoint(-48.0, 36.0), 4326),
             ARRAY['Parasaurolophus', 'Maiasaura', 'Troodon'],
             -83, -70)
        ON CONFLICT (name) DO NOTHING
        """,

        # paleo_continents rows
        """
        INSERT INTO dinosaures.paleo_continents (name, period, geometry, parent_continent)
        VALUES
            ('Pangée', 'Trias',
             ST_GeomFromText(
                 'POLYGON(( -80 80, -40 80, 20 60, 40 20, 30 -40, 0 -60, -40 -50, -60 -20, -80 80 ))',
                 4326),
             NULL)
        ON CONFLICT (name) DO NOTHING
        """,
        """
        INSERT INTO dinosaures.paleo_continents (name, period, geometry, parent_continent)
        VALUES
            ('Laurasia', 'Jurassique',
             ST_GeomFromText(
                 'POLYGON(( -80 80, -40 80, 20 60, 10 30, -20 30, -60 40, -80 80 ))',
                 4326),
             'Pangée')
        ON CONFLICT (name) DO NOTHING
        """,
        """
        INSERT INTO dinosaures.paleo_continents (name, period, geometry, parent_continent)
        VALUES
            ('Gondwana', 'Jurassique',
             ST_GeomFromText(
                 'POLYGON(( -30 30, 40 20, 30 -40, 0 -60, -40 -50, -30 30 ))',
                 4326),
             'Pangée')
        ON CONFLICT (name) DO NOTHING
        """,

        # Spatial helper function
        """
        CREATE OR REPLACE FUNCTION find_sites_within_radius(
            center_lon FLOAT,
            center_lat FLOAT,
            radius_km  FLOAT
        )
        RETURNS TABLE(name VARCHAR, distance_km FLOAT) AS $$
        BEGIN
            RETURN QUERY
            SELECT fs.name,
                   ST_Distance(
                       fs.location_modern::geography,
                       ST_SetSRID(ST_MakePoint(center_lon, center_lat), 4326)::geography
                   ) / 1000 AS distance_km
            FROM fossil_sites fs
            WHERE ST_DWithin(
                fs.location_modern::geography,
                ST_SetSRID(ST_MakePoint(center_lon, center_lat), 4326)::geography,
                radius_km * 1000
            )
            ORDER BY distance_km;
        END;
        $$ LANGUAGE plpgsql
        """,
    ],

    # ── GraphDB – RDF/Turtle ─────────────────────────────────────────────────
    graphdb_named_graph="http://pangia.io/data/dinosaurs",
    graphdb_turtle="""\
@prefix :       <http://pangia.io/ontology#> .
@prefix rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:   <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:    <http://www.w3.org/2002/07/owl#> .
@prefix xsd:    <http://www.w3.org/2001/XMLSchema#> .
@prefix geo:    <http://www.w3.org/2003/01/geo/wgs84_pos#> .

# ── Ontology declaration ────────────────────────────────────────────────────
<http://pangia.io/ontology> a owl:Ontology ;
    rdfs:label "PangIA Paléogéographie Ontologie"@fr .

# ── Classes ─────────────────────────────────────────────────────────────────
:Dinosaur a owl:Class ;
    rdfs:label "Dinosaure"@fr .

:FossilSite a owl:Class ;
    rdfs:label "Site fossilifère"@fr .

:PaleoContinent a owl:Class ;
    rdfs:label "Continent paléogéographique"@fr .

# ── Object properties ───────────────────────────────────────────────────────
:foundAtSite a owl:ObjectProperty ;
    rdfs:domain :Dinosaur ;
    rdfs:range  :FossilSite ;
    rdfs:label  "découvert sur le site"@fr .

:locatedIn a owl:ObjectProperty ;
    rdfs:domain :Dinosaur ;
    rdfs:range  :PaleoContinent ;
    rdfs:label  "localisé dans"@fr .

:subContinentOf a owl:ObjectProperty ;
    rdfs:domain :PaleoContinent ;
    rdfs:range  :PaleoContinent ;
    rdfs:label  "sous-continent de"@fr .

:preysOn a owl:ObjectProperty ;
    rdfs:domain :Dinosaur ;
    rdfs:range  :Dinosaur ;
    rdfs:label  "chasse"@fr .

:coexistsWith a owl:ObjectProperty ;
    rdfs:domain :Dinosaur ;
    rdfs:range  :Dinosaur ;
    rdfs:label  "coexiste avec"@fr .

# ── Data properties ─────────────────────────────────────────────────────────
:period     a owl:DatatypeProperty ; rdfs:range xsd:string  ; rdfs:label "période"@fr .
:diet       a owl:DatatypeProperty ; rdfs:range xsd:string  ; rdfs:label "régime"@fr .
:lengthM    a owl:DatatypeProperty ; rdfs:range xsd:decimal ; rdfs:label "longueur (m)"@fr .
:weightKg   a owl:DatatypeProperty ; rdfs:range xsd:decimal ; rdfs:label "poids (kg)"@fr .
:eraStart   a owl:DatatypeProperty ; rdfs:range xsd:integer ; rdfs:label "début de l'ère (Ma)"@fr .
:eraEnd     a owl:DatatypeProperty ; rdfs:range xsd:integer ; rdfs:label "fin de l'ère (Ma)"@fr .
:country    a owl:DatatypeProperty ; rdfs:range xsd:string  ; rdfs:label "pays"@fr .
:modernLat  a owl:DatatypeProperty ; rdfs:range xsd:decimal ; rdfs:label "latitude moderne"@fr .
:modernLon  a owl:DatatypeProperty ; rdfs:range xsd:decimal ; rdfs:label "longitude moderne"@fr .
:pangaeaLat a owl:DatatypeProperty ; rdfs:range xsd:decimal ; rdfs:label "latitude Pangée"@fr .
:pangaeaLon a owl:DatatypeProperty ; rdfs:range xsd:decimal ; rdfs:label "longitude Pangée"@fr .

# ── Individuals – Dinosaurs ─────────────────────────────────────────────────
:TyrannosaurusRex a :Dinosaur ;
    rdfs:label   "Tyrannosaurus rex" ;
    :period      "Crétacé supérieur" ;
    :diet        "carnivore" ;
    :lengthM     "12.3"^^xsd:decimal ;
    :weightKg    "8000"^^xsd:decimal ;
    :eraStart    "-68"^^xsd:integer ;
    :eraEnd      "-66"^^xsd:integer ;
    :locatedIn   :AmeriqueduNord ;
    :foundAtSite :HellCreek ;
    :preysOn     :Triceratops, :Ankylosaurus, :Parasaurolophus ;
    :coexistsWith :Triceratops, :Ankylosaurus, :Parasaurolophus, :Velociraptor .

:Brachiosaurus a :Dinosaur ;
    rdfs:label   "Brachiosaurus" ;
    :period      "Jurassique supérieur" ;
    :diet        "herbivore" ;
    :lengthM     "22"^^xsd:decimal ;
    :weightKg    "56000"^^xsd:decimal ;
    :eraStart    "-154"^^xsd:integer ;
    :eraEnd      "-150"^^xsd:integer ;
    :locatedIn   :Gondwana ;
    :foundAtSite :Tendaguru ;
    :coexistsWith :Diplodocus .

:Velociraptor a :Dinosaur ;
    rdfs:label   "Velociraptor" ;
    :period      "Crétacé supérieur" ;
    :diet        "carnivore" ;
    :lengthM     "2"^^xsd:decimal ;
    :weightKg    "15"^^xsd:decimal ;
    :eraStart    "-75"^^xsd:integer ;
    :eraEnd      "-71"^^xsd:integer ;
    :locatedIn   :Asie ;
    :foundAtSite :Djadokhta ;
    :preysOn     :Protoceratops ;
    :coexistsWith :Protoceratops, :TyrannosaurusRex .

:Archaeopteryx a :Dinosaur ;
    rdfs:label   "Archaeopteryx" ;
    :period      "Jurassique supérieur" ;
    :diet        "carnivore" ;
    :lengthM     "0.5"^^xsd:decimal ;
    :weightKg    "1"^^xsd:decimal ;
    :eraStart    "-150"^^xsd:integer ;
    :eraEnd      "-148"^^xsd:integer ;
    :locatedIn   :Europe ;
    :foundAtSite :Solnhofen .

:Diplodocus a :Dinosaur ;
    rdfs:label   "Diplodocus" ;
    :period      "Jurassique supérieur" ;
    :diet        "herbivore" ;
    :lengthM     "27"^^xsd:decimal ;
    :weightKg    "15000"^^xsd:decimal ;
    :eraStart    "-154"^^xsd:integer ;
    :eraEnd      "-152"^^xsd:integer ;
    :locatedIn   :AmeriqueduNord ;
    :foundAtSite :MorrisonFormation ;
    :coexistsWith :Brachiosaurus, :Allosaurus, :Stegosaurus .

:Allosaurus a :Dinosaur ;
    rdfs:label   "Allosaurus" ;
    :period      "Jurassique supérieur" ;
    :diet        "carnivore" ;
    :lengthM     "9.0"^^xsd:decimal ;
    :weightKg    "2300"^^xsd:decimal ;
    :eraStart    "-156"^^xsd:integer ;
    :eraEnd      "-150"^^xsd:integer ;
    :locatedIn   :AmeriqueduNord ;
    :foundAtSite :MorrisonFormation ;
    :preysOn     :Stegosaurus, :Diplodocus, :Brachiosaurus ;
    :coexistsWith :Stegosaurus, :Diplodocus, :Brachiosaurus .

:Stegosaurus a :Dinosaur ;
    rdfs:label   "Stegosaurus" ;
    :period      "Jurassique supérieur" ;
    :diet        "herbivore" ;
    :lengthM     "9.0"^^xsd:decimal ;
    :weightKg    "3500"^^xsd:decimal ;
    :eraStart    "-156"^^xsd:integer ;
    :eraEnd      "-150"^^xsd:integer ;
    :locatedIn   :AmeriqueduNord ;
    :foundAtSite :MorrisonFormation ;
    :coexistsWith :Allosaurus, :Diplodocus .

:Triceratops a :Dinosaur ;
    rdfs:label   "Triceratops" ;
    :period      "Crétacé supérieur" ;
    :diet        "herbivore" ;
    :lengthM     "9.0"^^xsd:decimal ;
    :weightKg    "12000"^^xsd:decimal ;
    :eraStart    "-68"^^xsd:integer ;
    :eraEnd      "-66"^^xsd:integer ;
    :locatedIn   :AmeriqueduNord ;
    :foundAtSite :HellCreek ;
    :coexistsWith :TyrannosaurusRex, :Ankylosaurus, :Parasaurolophus .

:Ankylosaurus a :Dinosaur ;
    rdfs:label   "Ankylosaurus" ;
    :period      "Crétacé supérieur" ;
    :diet        "herbivore" ;
    :lengthM     "6.25"^^xsd:decimal ;
    :weightKg    "6000"^^xsd:decimal ;
    :eraStart    "-68"^^xsd:integer ;
    :eraEnd      "-66"^^xsd:integer ;
    :locatedIn   :AmeriqueduNord ;
    :foundAtSite :HellCreek ;
    :coexistsWith :TyrannosaurusRex, :Triceratops, :Parasaurolophus .

:Spinosaurus a :Dinosaur ;
    rdfs:label   "Spinosaurus" ;
    :period      "Crétacé moyen" ;
    :diet        "piscivore" ;
    :lengthM     "15.0"^^xsd:decimal ;
    :weightKg    "7000"^^xsd:decimal ;
    :eraStart    "-112"^^xsd:integer ;
    :eraEnd      "-93"^^xsd:integer ;
    :locatedIn   :Afrique ;
    :foundAtSite :KemKemBeds .

:Protoceratops a :Dinosaur ;
    rdfs:label   "Protoceratops" ;
    :period      "Crétacé supérieur" ;
    :diet        "herbivore" ;
    :lengthM     "1.8"^^xsd:decimal ;
    :weightKg    "177"^^xsd:decimal ;
    :eraStart    "-83"^^xsd:integer ;
    :eraEnd      "-70"^^xsd:integer ;
    :locatedIn   :Asie ;
    :foundAtSite :Djadokhta ;
    :coexistsWith :Velociraptor .

:Iguanodon a :Dinosaur ;
    rdfs:label   "Iguanodon" ;
    :period      "Crétacé inférieur" ;
    :diet        "herbivore" ;
    :lengthM     "10.0"^^xsd:decimal ;
    :weightKg    "3000"^^xsd:decimal ;
    :eraStart    "-140"^^xsd:integer ;
    :eraEnd      "-100"^^xsd:integer ;
    :locatedIn   :Europe ;
    :foundAtSite :Bernissart .

:Carnotaurus a :Dinosaur ;
    rdfs:label   "Carnotaurus" ;
    :period      "Crétacé supérieur" ;
    :diet        "carnivore" ;
    :lengthM     "8.0"^^xsd:decimal ;
    :weightKg    "1500"^^xsd:decimal ;
    :eraStart    "-72"^^xsd:integer ;
    :eraEnd      "-69"^^xsd:integer ;
    :locatedIn   :AmeriqueduSud ;
    :foundAtSite :Neuquen ;
    :preysOn     :Argentinosaurus ;
    :coexistsWith :Argentinosaurus .

:Argentinosaurus a :Dinosaur ;
    rdfs:label   "Argentinosaurus" ;
    :period      "Crétacé supérieur" ;
    :diet        "herbivore" ;
    :lengthM     "35.0"^^xsd:decimal ;
    :weightKg    "70000"^^xsd:decimal ;
    :eraStart    "-96"^^xsd:integer ;
    :eraEnd      "-90"^^xsd:integer ;
    :locatedIn   :AmeriqueduSud ;
    :foundAtSite :Neuquen ;
    :coexistsWith :Carnotaurus .

:Parasaurolophus a :Dinosaur ;
    rdfs:label   "Parasaurolophus" ;
    :period      "Crétacé supérieur" ;
    :diet        "herbivore" ;
    :lengthM     "9.5"^^xsd:decimal ;
    :weightKg    "2500"^^xsd:decimal ;
    :eraStart    "-76"^^xsd:integer ;
    :eraEnd      "-73"^^xsd:integer ;
    :locatedIn   :AmeriqueduNord ;
    :foundAtSite :TwoMedicineFormation ;
    :coexistsWith :Triceratops, :Ankylosaurus .

# ── Individuals – Fossil sites ──────────────────────────────────────────────
:HellCreek a :FossilSite ;
    rdfs:label  "Hell Creek" ;
    :country    "USA" ;
    :eraStart   "-68"^^xsd:integer ;
    :eraEnd     "-66"^^xsd:integer ;
    :modernLat  "46.9"^^xsd:decimal ;
    :modernLon  "-101.5"^^xsd:decimal ;
    :pangaeaLat "35.0"^^xsd:decimal ;
    :pangaeaLon "-45.2"^^xsd:decimal .

:Tendaguru a :FossilSite ;
    rdfs:label  "Tendaguru" ;
    :country    "Tanzanie" ;
    :eraStart   "-154"^^xsd:integer ;
    :eraEnd     "-150"^^xsd:integer ;
    :modernLat  "-9.5"^^xsd:decimal ;
    :modernLon  "35.3"^^xsd:decimal ;
    :pangaeaLat "-25.0"^^xsd:decimal ;
    :pangaeaLon "25.0"^^xsd:decimal .

:Djadokhta a :FossilSite ;
    rdfs:label  "Djadokhta" ;
    :country    "Mongolie" ;
    :eraStart   "-75"^^xsd:integer ;
    :eraEnd     "-71"^^xsd:integer ;
    :modernLat  "43.5"^^xsd:decimal ;
    :modernLon  "104.5"^^xsd:decimal ;
    :pangaeaLat "35.0"^^xsd:decimal ;
    :pangaeaLon "80.0"^^xsd:decimal .

:Solnhofen a :FossilSite ;
    rdfs:label  "Solnhofen" ;
    :country    "Allemagne" ;
    :eraStart   "-150"^^xsd:integer ;
    :eraEnd     "-148"^^xsd:integer ;
    :modernLat  "48.9"^^xsd:decimal ;
    :modernLon  "11.0"^^xsd:decimal ;
    :pangaeaLat "40.0"^^xsd:decimal ;
    :pangaeaLon "20.0"^^xsd:decimal .

:MorrisonFormation a :FossilSite ;
    rdfs:label  "Morrison Formation" ;
    :country    "USA" ;
    :eraStart   "-154"^^xsd:integer ;
    :eraEnd     "-152"^^xsd:integer ;
    :modernLat  "38.0"^^xsd:decimal ;
    :modernLon  "-108.0"^^xsd:decimal ;
    :pangaeaLat "35.0"^^xsd:decimal ;
    :pangaeaLon "-50.0"^^xsd:decimal .

:KemKemBeds a :FossilSite ;
    rdfs:label  "Kem Kem Beds" ;
    :country    "Maroc" ;
    :eraStart   "-112"^^xsd:integer ;
    :eraEnd     "-93"^^xsd:integer ;
    :modernLat  "30.5"^^xsd:decimal ;
    :modernLon  "-4.5"^^xsd:decimal ;
    :pangaeaLat "5.0"^^xsd:decimal ;
    :pangaeaLon "10.0"^^xsd:decimal .

:Bernissart a :FossilSite ;
    rdfs:label  "Bernissart" ;
    :country    "Belgique" ;
    :eraStart   "-140"^^xsd:integer ;
    :eraEnd     "-100"^^xsd:integer ;
    :modernLat  "50.5"^^xsd:decimal ;
    :modernLon  "3.7"^^xsd:decimal ;
    :pangaeaLat "42.0"^^xsd:decimal ;
    :pangaeaLon "15.0"^^xsd:decimal .

:Neuquen a :FossilSite ;
    rdfs:label  "Neuquén" ;
    :country    "Argentine" ;
    :eraStart   "-96"^^xsd:integer ;
    :eraEnd     "-69"^^xsd:integer ;
    :modernLat  "-38.9"^^xsd:decimal ;
    :modernLon  "-68.1"^^xsd:decimal ;
    :pangaeaLat "-45.0"^^xsd:decimal ;
    :pangaeaLon "-55.0"^^xsd:decimal .

:TwoMedicineFormation a :FossilSite ;
    rdfs:label  "Two Medicine Formation" ;
    :country    "USA" ;
    :eraStart   "-83"^^xsd:integer ;
    :eraEnd     "-70"^^xsd:integer ;
    :modernLat  "48.3"^^xsd:decimal ;
    :modernLon  "-112.5"^^xsd:decimal ;
    :pangaeaLat "36.0"^^xsd:decimal ;
    :pangaeaLon "-48.0"^^xsd:decimal .

# ── Individuals – Paleo-continents ──────────────────────────────────────────
:Pangee a :PaleoContinent ;
    rdfs:label  "Pangée"@fr ;
    :period     "Trias" ;
    :eraStart   "-335"^^xsd:integer ;
    :eraEnd     "-175"^^xsd:integer .

:Laurasia a :PaleoContinent ;
    rdfs:label      "Laurasia" ;
    :period         "Jurassique" ;
    :eraStart       "-175"^^xsd:integer ;
    :eraEnd         "-66"^^xsd:integer ;
    :subContinentOf :Pangee .

:Gondwana a :PaleoContinent ;
    rdfs:label      "Gondwana" ;
    :period         "Jurassique" ;
    :eraStart       "-175"^^xsd:integer ;
    :eraEnd         "-66"^^xsd:integer ;
    :subContinentOf :Pangee .

:AmeriqueduNord a :PaleoContinent ;
    rdfs:label      "Amérique du Nord"@fr ;
    :eraStart       "-66"^^xsd:integer ;
    :eraEnd         "0"^^xsd:integer ;
    :subContinentOf :Laurasia .

:Europe a :PaleoContinent ;
    rdfs:label      "Europe" ;
    :eraStart       "-66"^^xsd:integer ;
    :eraEnd         "0"^^xsd:integer ;
    :subContinentOf :Laurasia .

:Afrique a :PaleoContinent ;
    rdfs:label      "Afrique"@fr ;
    :eraStart       "-66"^^xsd:integer ;
    :eraEnd         "0"^^xsd:integer ;
    :subContinentOf :Gondwana .

:AmeriqueduSud a :PaleoContinent ;
    rdfs:label      "Amérique du Sud"@fr ;
    :eraStart       "-66"^^xsd:integer ;
    :eraEnd         "0"^^xsd:integer ;
    :subContinentOf :Gondwana .

:Asie a :PaleoContinent ;
    rdfs:label      "Asie"@fr ;
    :eraStart       "-66"^^xsd:integer ;
    :eraEnd         "0"^^xsd:integer ;
    :subContinentOf :Laurasia .
""",

    # ── Agent guidelines (theme-specific) ────────────────────────────────────
    neo4j_guidelines="""\
- For questions about fossil sites ("which sites contain fossils of X", "where \
were X fossils found"), predator/prey relationships ("what does X prey on", \
"what hunts X"), or species coexistence ("which species coexist with X"), \
always use `run_cypher_query` with a direct MATCH pattern.
- Entity names in the graph use no diacritics (e.g. 'Velociraptor', not \
'Vélociraptor', 'Tyrannosaurus rex' not 'T-rex'). Strip accents when writing \
Cypher string literals.
- When returning Site nodes, **always include site.lat and site.lon** in the \
Cypher RETURN clause and report them explicitly in your answer.
""",

    postgis_guidelines="""\
- The `fossil_sites.dinosaurs_found` column is a TEXT[] array; use \
`'Species name' = ANY(dinosaurs_found)` to filter by species name.
- Coordinates are stored in WGS-84 (EPSG:4326). Cast to `::geography` for \
metre-accurate ST_Distance / ST_DWithin results.
- `location_modern` holds the current GPS position; `location_pangaea` holds \
the reconstructed Pangaea-era position.
""",

    rdf_guidelines="""\
- Use PREFIX : <http://pangia.io/ontology#> in every query.
- Always scope patterns inside GRAPH <http://pangia.io/graphs/dinosaurs> { ... }.
- Key object properties: :preysOn, :coexistsWith, :foundAtSite, :locatedIn, \
:subContinentOf.
- Key data properties on :Dinosaur: :lengthM (decimal, metres), :weightKg \
(decimal), :diet (string), :period (string), :eraStart/:eraEnd (integer, Ma).
""",

    vector_guidelines="""\
- Documents cover: dinosaur species descriptions, fossil site descriptions, \
paleo-continent overviews, and food-chain summaries.
- Available metadata filters: `type` (dinosaur | site | continent | food_chain), \
`name`, `period`, `country`, `region`.
- Prefer semantic search for general questions; use metadata filters when the \
user specifies a particular type, time period, or geographic area.
""",

    # ── Suggestions UI ────────────────────────────────────────────────────────
    suggestions=[
        "Quels dinosaures vivaient en Asie ?",
        "Quels sites ont livré des fossiles de Vélociraptor ?",
        "Compare la taille du T-rex et du Vélociraptor.",
        "Montre les relations prédateur-proie du Jurassique.",
        "Quels sont les plus grands herbivores connus ?",
        "Où vivait le Spinosaurus et que mangeait-il ?",
        "Quels dinosaures coexistaient en Amérique du Nord ?",
        "Quel est le site fossilifère le plus riche d'Amérique du Sud ?",
    ],

    # ── ChromaDB – documents à vectoriser ────────────────────────────────────
    chroma_documents=[
        {
            "text": (
                "Le Velociraptor est un dinosaure carnivore du Crétacé supérieur "
                "(-75 à -71 Ma), mesurant environ 2 mètres pour 15 kg. "
                "Il vivait en Asie centrale. Des fossiles ont été découverts sur le "
                "site de Djadokhta, en Mongolie. Il coexistait avec le Tyrannosaurus "
                "rex et chassait notamment l'Archaeopteryx."
            ),
            "metadata": {"type": "dinosaur", "name": "Velociraptor", "period": "Crétacé supérieur"},
        },
        {
            "text": (
                "Le Tyrannosaurus rex est un dinosaure carnivore du Crétacé supérieur "
                "(-68 à -66 Ma), mesurant 12,3 mètres pour 8 000 kg. "
                "Il vivait en Amérique du Nord. Ses fossiles sont notamment connus du "
                "site de Hell Creek, aux États-Unis. Il coexistait avec le Velociraptor."
            ),
            "metadata": {"type": "dinosaur", "name": "Tyrannosaurus rex", "period": "Crétacé supérieur"},
        },
        {
            "text": (
                "Le Brachiosaurus est un dinosaure herbivore du Jurassique supérieur "
                "(-154 à -150 Ma), mesurant 22 mètres pour 56 000 kg. "
                "Il vivait sur le continent de Gondwana. Ses fossiles ont été découverts "
                "à Tendaguru, en Tanzanie. Il coexistait avec le Diplodocus."
            ),
            "metadata": {"type": "dinosaur", "name": "Brachiosaurus", "period": "Jurassique supérieur"},
        },
        {
            "text": (
                "L'Archaeopteryx est un dinosaure carnivore du Jurassique supérieur "
                "(-150 à -148 Ma), mesurant 50 cm pour 1 kg. "
                "Considéré comme un ancêtre des oiseaux modernes, il vivait en Europe. "
                "Ses fossiles proviennent du site de Solnhofen, en Allemagne."
            ),
            "metadata": {"type": "dinosaur", "name": "Archaeopteryx", "period": "Jurassique supérieur"},
        },
        {
            "text": (
                "Le Diplodocus est un dinosaure herbivore du Jurassique supérieur "
                "(-154 à -152 Ma), mesurant 27 mètres pour 15 000 kg. "
                "Il vivait en Amérique du Nord. Ses fossiles proviennent de la "
                "Morrison Formation, aux États-Unis. Il coexistait avec le Brachiosaurus."
            ),
            "metadata": {"type": "dinosaur", "name": "Diplodocus", "period": "Jurassique supérieur"},
        },
        {
            "text": (
                "Le site de Hell Creek (États-Unis) est un gisement fossilifère du "
                "Crétacé supérieur (-68 à -66 Ma) situé à 46.9°N, -101.5°E. "
                "On y a découvert des fossiles de Tyrannosaurus rex, Triceratops et Ankylosaurus."
            ),
            "metadata": {"type": "site", "name": "Hell Creek", "country": "USA"},
        },
        {
            "text": (
                "Le site de Djadokhta (Mongolie) est un gisement fossilifère du "
                "Crétacé supérieur (-75 à -71 Ma) situé à 43.5°N, 104.5°E. "
                "On y a découvert des fossiles de Velociraptor, Protoceratops et Oviraptor."
            ),
            "metadata": {"type": "site", "name": "Djadokhta", "country": "Mongolie"},
        },
        {
            "text": (
                "Le site de Tendaguru (Tanzanie) est un gisement fossilifère du "
                "Jurassique supérieur (-154 à -150 Ma) situé à -9.5°N, 35.3°E. "
                "On y a découvert des fossiles de Brachiosaurus, Giraffatitan et Kentrosaurus."
            ),
            "metadata": {"type": "site", "name": "Tendaguru", "country": "Tanzanie"},
        },
        {
            "text": (
                "Le site de Solnhofen (Allemagne) est un gisement fossilifère du "
                "Jurassique supérieur (-150 à -148 Ma) situé à 48.9°N, 11.0°E. "
                "On y a découvert des fossiles d'Archaeopteryx, Compsognathus et Pterodactylus."
            ),
            "metadata": {"type": "site", "name": "Solnhofen", "country": "Allemagne"},
        },
        {
            "text": (
                "La Pangée était le supercontinent qui existait pendant le Trias "
                "(-335 à -175 Ma). Elle s'est fragmentée en Laurasia (nord) et Gondwana (sud) "
                "au Jurassique. Tous les dinosaures connus vivaient sur ses fragments."
            ),
            "metadata": {"type": "continent", "name": "Pangée", "period": "Trias"},
        },
        {
            "text": (
                "L'Allosaurus est un dinosaure carnivore du Jurassique supérieur "
                "(-156 à -150 Ma), mesurant 9 mètres pour 2 300 kg. "
                "Prédateur dominant de son époque, il chassait le Stegosaurus, le Diplodocus "
                "et le Brachiosaurus. Ses fossiles proviennent de la Morrison Formation (USA). "
                "Il coexistait avec Stegosaurus, Diplodocus et Brachiosaurus."
            ),
            "metadata": {"type": "dinosaur", "name": "Allosaurus", "period": "Jurassique supérieur"},
        },
        {
            "text": (
                "Le Stegosaurus est un dinosaure herbivore du Jurassique supérieur "
                "(-156 à -150 Ma), mesurant 9 mètres pour 3 500 kg. "
                "Il est reconnaissable à ses grandes plaques dorsales et à son queue à pointes. "
                "Proie principale de l'Allosaurus, il vivait en Amérique du Nord. "
                "Ses fossiles viennent de la Morrison Formation (USA)."
            ),
            "metadata": {"type": "dinosaur", "name": "Stegosaurus", "period": "Jurassique supérieur"},
        },
        {
            "text": (
                "Le Triceratops est un dinosaure herbivore du Crétacé supérieur "
                "(-68 à -66 Ma), mesurant 9 mètres pour 12 000 kg. "
                "Doté de trois cornes et d'une large collerette osseuse, il était la proie "
                "principale du Tyrannosaurus rex. Il coexistait avec Ankylosaurus et "
                "Parasaurolophus sur le site de Hell Creek (USA)."
            ),
            "metadata": {"type": "dinosaur", "name": "Triceratops", "period": "Crétacé supérieur"},
        },
        {
            "text": (
                "L'Ankylosaurus est un dinosaure herbivore du Crétacé supérieur "
                "(-68 à -66 Ma), mesurant 6,25 mètres pour 6 000 kg. "
                "Son corps était recouvert d'une armure osseuse et sa queue se terminait "
                "par une massue. Il était chassé par le Tyrannosaurus rex. "
                "Ses fossiles proviennent du site de Hell Creek (USA)."
            ),
            "metadata": {"type": "dinosaur", "name": "Ankylosaurus", "period": "Crétacé supérieur"},
        },
        {
            "text": (
                "Le Spinosaurus est un dinosaure piscivore du Crétacé moyen "
                "(-112 à -93 Ma), mesurant 15 mètres pour 7 000 kg. "
                "C'est l'un des plus grands prédateurs terrestres connus. Il vivait en Afrique "
                "du Nord, principalement en bord de fleuves. Ses fossiles ont été découverts "
                "dans les Kem Kem Beds, au Maroc."
            ),
            "metadata": {"type": "dinosaur", "name": "Spinosaurus", "period": "Crétacé moyen"},
        },
        {
            "text": (
                "Le Protoceratops est un dinosaure herbivore du Crétacé supérieur "
                "(-83 à -70 Ma), mesurant 1,8 mètre pour 177 kg. "
                "Il vivait en Asie centrale et était la proie principale du Velociraptor. "
                "Le célèbre fossile des 'Dinosaures combattants' montre un Velociraptor "
                "et un Protoceratops figés en plein combat. Site : Djadokhta, Mongolie."
            ),
            "metadata": {"type": "dinosaur", "name": "Protoceratops", "period": "Crétacé supérieur"},
        },
        {
            "text": (
                "L'Iguanodon est un dinosaure herbivore du Crétacé inférieur "
                "(-140 à -100 Ma), mesurant 10 mètres pour 3 000 kg. "
                "Il est l'un des premiers dinosaures décrits scientifiquement. "
                "Il vivait en Europe. Ses fossiles les plus célèbres ont été découverts "
                "dans la mine de Bernissart, en Belgique."
            ),
            "metadata": {"type": "dinosaur", "name": "Iguanodon", "period": "Crétacé inférieur"},
        },
        {
            "text": (
                "Le Carnotaurus est un dinosaure carnivore du Crétacé supérieur "
                "(-72 à -69 Ma), mesurant 8 mètres pour 1 500 kg. "
                "Il est caractérisé par ses deux petites cornes au-dessus des yeux. "
                "Prédateur agile d'Amérique du Sud, il chassait notamment l'Argentinosaurus. "
                "Ses fossiles proviennent de la région de Neuquén, en Argentine."
            ),
            "metadata": {"type": "dinosaur", "name": "Carnotaurus", "period": "Crétacé supérieur"},
        },
        {
            "text": (
                "L'Argentinosaurus est un dinosaure herbivore du Crétacé supérieur "
                "(-96 à -90 Ma), mesurant 35 mètres pour 70 000 kg. "
                "C'est l'un des plus grands animaux terrestres ayant jamais existé. "
                "Il vivait en Amérique du Sud et était chassé par le Carnotaurus. "
                "Ses fossiles ont été découverts dans la région de Neuquén, en Argentine."
            ),
            "metadata": {"type": "dinosaur", "name": "Argentinosaurus", "period": "Crétacé supérieur"},
        },
        {
            "text": (
                "Le Parasaurolophus est un dinosaure herbivore du Crétacé supérieur "
                "(-76 à -73 Ma), mesurant 9,5 mètres pour 2 500 kg. "
                "Il est reconnaissable à sa longue crête creuse sur le crâne, utilisée "
                "pour communiquer par sons. Il coexistait avec Triceratops et Ankylosaurus "
                "en Amérique du Nord. Fossiles : Two Medicine Formation (USA)."
            ),
            "metadata": {"type": "dinosaur", "name": "Parasaurolophus", "period": "Crétacé supérieur"},
        },
        {
            "text": (
                "Le site des Kem Kem Beds (Maroc) est un gisement fossilifère du "
                "Crétacé moyen (-112 à -93 Ma) situé à 30.5°N, -4.5°E. "
                "On y a découvert des fossiles de Spinosaurus, Carcharodontosaurus et Deltadromeus. "
                "C'était un environnement fluvial avec une faune de prédateurs exceptionnelle."
            ),
            "metadata": {"type": "site", "name": "Kem Kem Beds", "country": "Maroc"},
        },
        {
            "text": (
                "Le site de Bernissart (Belgique) est un gisement fossilifère du "
                "Crétacé inférieur (-140 à -100 Ma) situé à 50.5°N, 3.7°E. "
                "En 1878, des mineurs y ont découvert 38 squelettes d'Iguanodon, "
                "constituant l'une des plus importantes découvertes paléontologiques d'Europe."
            ),
            "metadata": {"type": "site", "name": "Bernissart", "country": "Belgique"},
        },
        {
            "text": (
                "Le site de Neuquén (Argentine) est un gisement fossilifère du "
                "Crétacé supérieur (-96 à -69 Ma) situé à -38.9°N, -68.1°E. "
                "C'est l'un des sites les plus riches au monde, ayant livré des fossiles "
                "d'Argentinosaurus, Carnotaurus et Giganotosaurus."
            ),
            "metadata": {"type": "site", "name": "Neuquén", "country": "Argentine"},
        },
        {
            "text": (
                "La chaîne alimentaire du Crétacé supérieur en Amérique du Nord : "
                "le Tyrannosaurus rex était le super-prédateur dominant. "
                "Il chassait le Triceratops, l'Ankylosaurus et le Parasaurolophus. "
                "Ces herbivores coexistaient tous sur le site de Hell Creek (-68 à -66 Ma)."
            ),
            "metadata": {"type": "food_chain", "period": "Crétacé supérieur", "region": "Amérique du Nord"},
        },
        {
            "text": (
                "La chaîne alimentaire du Jurassique supérieur en Amérique du Nord : "
                "l'Allosaurus était le principal prédateur de la Morrison Formation. "
                "Il chassait le Stegosaurus, le Diplodocus et le Brachiosaurus. "
                "Ces espèces coexistaient toutes entre -156 et -150 Ma."
            ),
            "metadata": {"type": "food_chain", "period": "Jurassique supérieur", "region": "Amérique du Nord"},
        },
    ],
)
