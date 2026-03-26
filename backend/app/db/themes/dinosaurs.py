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
Tables:
- fossil_sites(id, name, country, era, location_modern GEOMETRY(POINT,4326),
               location_pangaea GEOMETRY(POINT,4326), dinosaurs_found TEXT[],
               period_start INTEGER, period_end INTEGER)
- paleo_continents(id, name, period, geometry GEOMETRY(POLYGON,4326),
                   parent_continent VARCHAR)

Use PostGIS functions such as ST_Distance, ST_Contains, ST_Within, ST_Intersects,
ST_DWithin, ST_AsText, ST_X/ST_Y to answer spatial questions.
Distances are in metres (use /1000 to convert to km).
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
    ],

    # ── PostGIS – SQL statements ─────────────────────────────────────────────
    postgis_statements=[
        # Ensure the PostGIS extension is available
        "CREATE EXTENSION IF NOT EXISTS postgis",

        # fossil_sites table
        """
        CREATE TABLE IF NOT EXISTS fossil_sites (
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
        CREATE TABLE IF NOT EXISTS paleo_continents (
            id               SERIAL PRIMARY KEY,
            name             VARCHAR(50) UNIQUE,
            period           VARCHAR(50),
            geometry         GEOMETRY(POLYGON, 4326),
            parent_continent VARCHAR(50)
        )
        """,

        # fossil_sites rows
        """
        INSERT INTO fossil_sites
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
        INSERT INTO fossil_sites
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
        INSERT INTO fossil_sites
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
        INSERT INTO fossil_sites
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
        INSERT INTO fossil_sites
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

        # paleo_continents rows
        """
        INSERT INTO paleo_continents (name, period, geometry, parent_continent)
        VALUES
            ('Pangée', 'Trias',
             ST_GeomFromText(
                 'POLYGON(( -80 80, -40 80, 20 60, 40 20, 30 -40, 0 -60, -40 -50, -60 -20, -80 80 ))',
                 4326),
             NULL)
        ON CONFLICT (name) DO NOTHING
        """,
        """
        INSERT INTO paleo_continents (name, period, geometry, parent_continent)
        VALUES
            ('Laurasia', 'Jurassique',
             ST_GeomFromText(
                 'POLYGON(( -80 80, -40 80, 20 60, 10 30, -20 30, -60 40, -80 80 ))',
                 4326),
             'Pangée')
        ON CONFLICT (name) DO NOTHING
        """,
        """
        INSERT INTO paleo_continents (name, period, geometry, parent_continent)
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
    rdfs:label "Pangia Paléogéographie Ontologie"@fr .

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
    :foundAtSite :HellCreek .

:Brachiosaurus a :Dinosaur ;
    rdfs:label   "Brachiosaurus" ;
    :period      "Jurassique supérieur" ;
    :diet        "herbivore" ;
    :lengthM     "22"^^xsd:decimal ;
    :weightKg    "56000"^^xsd:decimal ;
    :eraStart    "-154"^^xsd:integer ;
    :eraEnd      "-150"^^xsd:integer ;
    :locatedIn   :Gondwana ;
    :foundAtSite :Tendaguru .

:Velociraptor a :Dinosaur ;
    rdfs:label   "Velociraptor" ;
    :period      "Crétacé supérieur" ;
    :diet        "carnivore" ;
    :lengthM     "2"^^xsd:decimal ;
    :weightKg    "15"^^xsd:decimal ;
    :eraStart    "-75"^^xsd:integer ;
    :eraEnd      "-71"^^xsd:integer ;
    :locatedIn   :Asie ;
    :foundAtSite :Djadokhta .

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
    :foundAtSite :MorrisonFormation .

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
)
