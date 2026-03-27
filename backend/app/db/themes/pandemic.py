"""
Seed theme: pandemic.

Global pandemic and epidemic outbreak data covering COVID-19, Ebola, Spanish
Flu, HIV/AIDS, SARS, MERS, Cholera, the Black Death and other major disease
events, together with their geospatial footprint across Neo4j, PostGIS,
GraphDB (RDF) and ChromaDB.
"""
from app.db.themes import SeedTheme

theme = SeedTheme(
    name="pandemic",

    # ── Schema prompts ────────────────────────────────────────────────────────
    neo4j_schema_prompt="""\
Node labels:
- Pandemic   — properties: name, pathogen, pathogen_type, year_start, year_end,
               total_cases, total_deaths, case_fatality_rate, transmission_route,
               pandemic_status
- Country    — properties: name, iso2, continent, population
- Region     — properties: name, country_name
- ResearchInstitution — properties: name, country, focus_area

Relationship types:
- (Pandemic)-[:ORIGINATED_IN]->(Country)
- (Pandemic)-[:SPREAD_TO {year, peak_cases}]->(Country)
- (Pandemic)-[:CAUSED_BY {pathogen}]->(Pandemic)   # variant lineage
- (Pandemic)-[:RELATED_TO {reason}]->(Pandemic)    # same pathogen family
- (Pandemic)-[:STUDIED_BY]->(ResearchInstitution)
- (Pandemic)-[:CONTROLLED_BY {intervention}]->(Country)
""",

    postgis_schema_prompt="""\
Tables:
- outbreak_sites(id, pandemic_name, site_name, country, location GEOMETRY(POINT,4326),
                 year_detected INTEGER, cases INTEGER, deaths INTEGER, notes TEXT)
- affected_regions(id, pandemic_name, region_name, geometry GEOMETRY(POLYGON,4326),
                   severity VARCHAR, year_start INTEGER, year_end INTEGER)

Use PostGIS functions such as ST_Distance, ST_Contains, ST_Within, ST_Intersects,
ST_DWithin, ST_AsText, ST_X/ST_Y to answer spatial questions.
Distances are in metres (use /1000 to convert to km).
""",

    rdf_schema_prompt="""\
Prefix: PREFIX : <http://pangia.io/ontology/pandemic#>

Classes:
- :Pandemic            — rdfs:label (string)
- :OutbreakSite        — rdfs:label (string)
- :Country             — rdfs:label (string)
- :Pathogen            — rdfs:label (string)

Object properties:
- :originatedIn        (:Pandemic → :Country)
- :spreadTo            (:Pandemic → :Country)
- :causedBy            (:Pandemic → :Pathogen)
- :relatedTo           (:Pandemic → :Pandemic)
- :detectedAt          (:Pandemic → :OutbreakSite)

Data properties (all on :Pandemic unless noted):
- :yearStart, :yearEnd (xsd:integer)
- :totalCases, :totalDeaths (xsd:integer)
- :caseFatalityRate (xsd:decimal)
- :transmissionRoute, :pandemicStatus (xsd:string)
- :lat, :lon (xsd:decimal) — on :OutbreakSite
- :countryName (xsd:string) — on :OutbreakSite

Named graph: <http://pangia.io/graphs/pandemic>
Always add GRAPH <http://pangia.io/graphs/pandemic> { ... } in queries.
""",

    # ── Neo4j – Cypher statements ────────────────────────────────────────────
    neo4j_statements=[

        # ── Pandemic nodes ────────────────────────────────────────────────────
        """
        MERGE (p:Pandemic {name: 'COVID-19'})
        SET p.pathogen            = 'SARS-CoV-2',
            p.pathogen_type       = 'coronavirus',
            p.year_start          = 2019,
            p.year_end            = 2023,
            p.total_cases         = 770000000,
            p.total_deaths        = 7000000,
            p.case_fatality_rate  = 0.9,
            p.transmission_route  = 'respiratory droplets / aerosol',
            p.pandemic_status     = 'post-pandemic'
        """,
        """
        MERGE (p:Pandemic {name: 'Ebola 2014-2016'})
        SET p.pathogen            = 'Ebola virus (Zaire ebolavirus)',
            p.pathogen_type       = 'filovirus',
            p.year_start          = 2014,
            p.year_end            = 2016,
            p.total_cases         = 28652,
            p.total_deaths        = 11325,
            p.case_fatality_rate  = 39.5,
            p.transmission_route  = 'direct contact with bodily fluids',
            p.pandemic_status     = 'ended'
        """,
        """
        MERGE (p:Pandemic {name: 'Ebola DRC 2018-2020'})
        SET p.pathogen            = 'Ebola virus (Zaire ebolavirus)',
            p.pathogen_type       = 'filovirus',
            p.year_start          = 2018,
            p.year_end            = 2020,
            p.total_cases         = 3481,
            p.total_deaths        = 2299,
            p.case_fatality_rate  = 66.0,
            p.transmission_route  = 'direct contact with bodily fluids',
            p.pandemic_status     = 'ended'
        """,
        """
        MERGE (p:Pandemic {name: 'Spanish Flu'})
        SET p.pathogen            = 'Influenza A (H1N1)',
            p.pathogen_type       = 'influenza',
            p.year_start          = 1918,
            p.year_end            = 1919,
            p.total_cases         = 500000000,
            p.total_deaths        = 50000000,
            p.case_fatality_rate  = 10.0,
            p.transmission_route  = 'respiratory droplets',
            p.pandemic_status     = 'ended'
        """,
        """
        MERGE (p:Pandemic {name: 'HIV/AIDS'})
        SET p.pathogen            = 'Human Immunodeficiency Virus (HIV)',
            p.pathogen_type       = 'retrovirus',
            p.year_start          = 1981,
            p.year_end            = 9999,
            p.total_cases         = 84200000,
            p.total_deaths        = 40100000,
            p.case_fatality_rate  = 47.6,
            p.transmission_route  = 'blood / sexual contact / mother-to-child',
            p.pandemic_status     = 'ongoing'
        """,
        """
        MERGE (p:Pandemic {name: 'SARS 2002-2003'})
        SET p.pathogen            = 'SARS-CoV-1',
            p.pathogen_type       = 'coronavirus',
            p.year_start          = 2002,
            p.year_end            = 2003,
            p.total_cases         = 8098,
            p.total_deaths        = 774,
            p.case_fatality_rate  = 9.6,
            p.transmission_route  = 'respiratory droplets',
            p.pandemic_status     = 'ended'
        """,
        """
        MERGE (p:Pandemic {name: 'MERS'})
        SET p.pathogen            = 'MERS-CoV',
            p.pathogen_type       = 'coronavirus',
            p.year_start          = 2012,
            p.year_end            = 9999,
            p.total_cases         = 2600,
            p.total_deaths        = 935,
            p.case_fatality_rate  = 36.0,
            p.transmission_route  = 'close contact / camels',
            p.pandemic_status     = 'ongoing (sporadic)'
        """,
        """
        MERGE (p:Pandemic {name: 'H1N1 Swine Flu 2009'})
        SET p.pathogen            = 'Influenza A (H1N1)pdm09',
            p.pathogen_type       = 'influenza',
            p.year_start          = 2009,
            p.year_end            = 2010,
            p.total_cases         = 700000000,
            p.total_deaths        = 284000,
            p.case_fatality_rate  = 0.04,
            p.transmission_route  = 'respiratory droplets',
            p.pandemic_status     = 'ended'
        """,
        """
        MERGE (p:Pandemic {name: 'Black Death'})
        SET p.pathogen            = 'Yersinia pestis',
            p.pathogen_type       = 'bacteria',
            p.year_start          = 1347,
            p.year_end            = 1353,
            p.total_cases         = 75000000,
            p.total_deaths        = 50000000,
            p.case_fatality_rate  = 66.0,
            p.transmission_route  = 'flea bites / respiratory (pneumonic)',
            p.pandemic_status     = 'ended'
        """,
        """
        MERGE (p:Pandemic {name: 'Cholera 7th Pandemic'})
        SET p.pathogen            = 'Vibrio cholerae O1 El Tor',
            p.pathogen_type       = 'bacteria',
            p.year_start          = 1961,
            p.year_end            = 9999,
            p.total_cases         = 2900000,
            p.total_deaths        = 95000,
            p.case_fatality_rate  = 3.3,
            p.transmission_route  = 'contaminated water / food',
            p.pandemic_status     = 'ongoing'
        """,
        """
        MERGE (p:Pandemic {name: 'Smallpox'})
        SET p.pathogen            = 'Variola major / minor',
            p.pathogen_type       = 'poxvirus',
            p.year_start          = 1900,
            p.year_end            = 1980,
            p.total_cases         = 300000000,
            p.total_deaths        = 300000000,
            p.case_fatality_rate  = 30.0,
            p.transmission_route  = 'respiratory droplets / skin contact',
            p.pandemic_status     = 'eradicated'
        """,
        """
        MERGE (p:Pandemic {name: 'Mpox 2022'})
        SET p.pathogen            = 'Monkeypox virus (clade IIb)',
            p.pathogen_type       = 'poxvirus',
            p.year_start          = 2022,
            p.year_end            = 9999,
            p.total_cases         = 90000,
            p.total_deaths        = 150,
            p.case_fatality_rate  = 0.17,
            p.transmission_route  = 'close physical contact',
            p.pandemic_status     = 'ongoing'
        """,

        # ── Country nodes ─────────────────────────────────────────────────────
        """
        MERGE (c:Country {name: 'China'})
        SET c.iso2 = 'CN', c.continent = 'Asia', c.population = 1412000000
        """,
        """
        MERGE (c:Country {name: 'Guinea'})
        SET c.iso2 = 'GN', c.continent = 'Africa', c.population = 13531000
        """,
        """
        MERGE (c:Country {name: 'Sierra Leone'})
        SET c.iso2 = 'SL', c.continent = 'Africa', c.population = 8141000
        """,
        """
        MERGE (c:Country {name: 'Liberia'})
        SET c.iso2 = 'LR', c.continent = 'Africa', c.population = 5418000
        """,
        """
        MERGE (c:Country {name: 'Democratic Republic of the Congo'})
        SET c.iso2 = 'CD', c.continent = 'Africa', c.population = 100000000
        """,
        """
        MERGE (c:Country {name: 'USA'})
        SET c.iso2 = 'US', c.continent = 'North America', c.population = 331000000
        """,
        """
        MERGE (c:Country {name: 'Brazil'})
        SET c.iso2 = 'BR', c.continent = 'South America', c.population = 214000000
        """,
        """
        MERGE (c:Country {name: 'India'})
        SET c.iso2 = 'IN', c.continent = 'Asia', c.population = 1380000000
        """,
        """
        MERGE (c:Country {name: 'Saudi Arabia'})
        SET c.iso2 = 'SA', c.continent = 'Asia', c.population = 35000000
        """,
        """
        MERGE (c:Country {name: 'South Korea'})
        SET c.iso2 = 'KR', c.continent = 'Asia', c.population = 51700000
        """,
        """
        MERGE (c:Country {name: 'Italy'})
        SET c.iso2 = 'IT', c.continent = 'Europe', c.population = 60400000
        """,
        """
        MERGE (c:Country {name: 'France'})
        SET c.iso2 = 'FR', c.continent = 'Europe', c.population = 67400000
        """,
        """
        MERGE (c:Country {name: 'Spain'})
        SET c.iso2 = 'ES', c.continent = 'Europe', c.population = 47400000
        """,
        """
        MERGE (c:Country {name: 'United Kingdom'})
        SET c.iso2 = 'GB', c.continent = 'Europe', c.population = 67900000
        """,
        """
        MERGE (c:Country {name: 'South Africa'})
        SET c.iso2 = 'ZA', c.continent = 'Africa', c.population = 60000000
        """,
        """
        MERGE (c:Country {name: 'Mexico'})
        SET c.iso2 = 'MX', c.continent = 'North America', c.population = 126000000
        """,
        """
        MERGE (c:Country {name: 'Yemen'})
        SET c.iso2 = 'YE', c.continent = 'Asia', c.population = 33700000
        """,
        """
        MERGE (c:Country {name: 'Haiti'})
        SET c.iso2 = 'HT', c.continent = 'North America', c.population = 11400000
        """,

        # ── ResearchInstitution nodes ─────────────────────────────────────────
        """
        MERGE (r:ResearchInstitution {name: 'WHO'})
        SET r.country = 'Switzerland', r.focus_area = 'global health coordination'
        """,
        """
        MERGE (r:ResearchInstitution {name: 'CDC'})
        SET r.country = 'USA', r.focus_area = 'disease control and prevention'
        """,
        """
        MERGE (r:ResearchInstitution {name: 'Institut Pasteur'})
        SET r.country = 'France', r.focus_area = 'infectious disease research'
        """,
        """
        MERGE (r:ResearchInstitution {name: 'Wuhan Institute of Virology'})
        SET r.country = 'China', r.focus_area = 'virology / bat coronaviruses'
        """,
        """
        MERGE (r:ResearchInstitution {name: 'USAMRIID'})
        SET r.country = 'USA', r.focus_area = 'biodefense / hemorrhagic fever viruses'
        """,

        # ── ORIGINATED_IN relationships ───────────────────────────────────────
        """
        MATCH (p:Pandemic {name: 'COVID-19'}), (c:Country {name: 'China'})
        MERGE (p)-[:ORIGINATED_IN]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'Ebola 2014-2016'}), (c:Country {name: 'Guinea'})
        MERGE (p)-[:ORIGINATED_IN]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'Ebola DRC 2018-2020'}),
              (c:Country {name: 'Democratic Republic of the Congo'})
        MERGE (p)-[:ORIGINATED_IN]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'SARS 2002-2003'}), (c:Country {name: 'China'})
        MERGE (p)-[:ORIGINATED_IN]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'MERS'}), (c:Country {name: 'Saudi Arabia'})
        MERGE (p)-[:ORIGINATED_IN]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'H1N1 Swine Flu 2009'}), (c:Country {name: 'Mexico'})
        MERGE (p)-[:ORIGINATED_IN]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'HIV/AIDS'}),
              (c:Country {name: 'Democratic Republic of the Congo'})
        MERGE (p)-[:ORIGINATED_IN]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'Mpox 2022'}), (c:Country {name: 'Democratic Republic of the Congo'})
        MERGE (p)-[:ORIGINATED_IN]->(c)
        """,

        # ── SPREAD_TO relationships ───────────────────────────────────────────
        """
        MATCH (p:Pandemic {name: 'COVID-19'}), (c:Country {name: 'Italy'})
        MERGE (p)-[:SPREAD_TO {year: 2020, peak_cases: 4000000}]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'COVID-19'}), (c:Country {name: 'USA'})
        MERGE (p)-[:SPREAD_TO {year: 2020, peak_cases: 103802702}]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'COVID-19'}), (c:Country {name: 'Brazil'})
        MERGE (p)-[:SPREAD_TO {year: 2020, peak_cases: 37519960}]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'COVID-19'}), (c:Country {name: 'India'})
        MERGE (p)-[:SPREAD_TO {year: 2020, peak_cases: 44690000}]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'COVID-19'}), (c:Country {name: 'France'})
        MERGE (p)-[:SPREAD_TO {year: 2020, peak_cases: 38997490}]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'COVID-19'}), (c:Country {name: 'United Kingdom'})
        MERGE (p)-[:SPREAD_TO {year: 2020, peak_cases: 24648620}]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'Ebola 2014-2016'}), (c:Country {name: 'Sierra Leone'})
        MERGE (p)-[:SPREAD_TO {year: 2014, peak_cases: 14124}]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'Ebola 2014-2016'}), (c:Country {name: 'Liberia'})
        MERGE (p)-[:SPREAD_TO {year: 2014, peak_cases: 10675}]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'MERS'}), (c:Country {name: 'South Korea'})
        MERGE (p)-[:SPREAD_TO {year: 2015, peak_cases: 186}]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'Cholera 7th Pandemic'}), (c:Country {name: 'Yemen'})
        MERGE (p)-[:SPREAD_TO {year: 2016, peak_cases: 2500000}]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'Cholera 7th Pandemic'}), (c:Country {name: 'Haiti'})
        MERGE (p)-[:SPREAD_TO {year: 2010, peak_cases: 820000}]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'HIV/AIDS'}), (c:Country {name: 'South Africa'})
        MERGE (p)-[:SPREAD_TO {year: 1990, peak_cases: 8200000}]->(c)
        """,
        """
        MATCH (p:Pandemic {name: 'HIV/AIDS'}), (c:Country {name: 'USA'})
        MERGE (p)-[:SPREAD_TO {year: 1985, peak_cases: 1200000}]->(c)
        """,

        # ── RELATED_TO relationships (same pathogen family) ───────────────────
        """
        MATCH (a:Pandemic {name: 'COVID-19'}), (b:Pandemic {name: 'SARS 2002-2003'})
        MERGE (a)-[:RELATED_TO {reason: 'both caused by betacoronaviruses'}]->(b)
        """,
        """
        MATCH (a:Pandemic {name: 'COVID-19'}), (b:Pandemic {name: 'MERS'})
        MERGE (a)-[:RELATED_TO {reason: 'both caused by betacoronaviruses'}]->(b)
        """,
        """
        MATCH (a:Pandemic {name: 'Ebola 2014-2016'}),
              (b:Pandemic {name: 'Ebola DRC 2018-2020'})
        MERGE (a)-[:RELATED_TO {reason: 'same Zaire ebolavirus strain'}]->(b)
        """,
        """
        MATCH (a:Pandemic {name: 'Spanish Flu'}),
              (b:Pandemic {name: 'H1N1 Swine Flu 2009'})
        MERGE (a)-[:RELATED_TO {reason: 'both caused by H1N1 influenza A'}]->(b)
        """,
        """
        MATCH (a:Pandemic {name: 'Smallpox'}), (b:Pandemic {name: 'Mpox 2022'})
        MERGE (a)-[:RELATED_TO {reason: 'both caused by orthopoxviruses'}]->(b)
        """,

        # ── STUDIED_BY relationships ──────────────────────────────────────────
        """
        MATCH (p:Pandemic {name: 'COVID-19'}), (r:ResearchInstitution {name: 'WHO'})
        MERGE (p)-[:STUDIED_BY]->(r)
        """,
        """
        MATCH (p:Pandemic {name: 'COVID-19'}),
              (r:ResearchInstitution {name: 'Wuhan Institute of Virology'})
        MERGE (p)-[:STUDIED_BY]->(r)
        """,
        """
        MATCH (p:Pandemic {name: 'COVID-19'}), (r:ResearchInstitution {name: 'CDC'})
        MERGE (p)-[:STUDIED_BY]->(r)
        """,
        """
        MATCH (p:Pandemic {name: 'Ebola 2014-2016'}),
              (r:ResearchInstitution {name: 'WHO'})
        MERGE (p)-[:STUDIED_BY]->(r)
        """,
        """
        MATCH (p:Pandemic {name: 'Ebola 2014-2016'}),
              (r:ResearchInstitution {name: 'USAMRIID'})
        MERGE (p)-[:STUDIED_BY]->(r)
        """,
        """
        MATCH (p:Pandemic {name: 'HIV/AIDS'}),
              (r:ResearchInstitution {name: 'Institut Pasteur'})
        MERGE (p)-[:STUDIED_BY]->(r)
        """,
        """
        MATCH (p:Pandemic {name: 'SARS 2002-2003'}),
              (r:ResearchInstitution {name: 'WHO'})
        MERGE (p)-[:STUDIED_BY]->(r)
        """,
    ],

    # ── PostGIS – SQL statements ─────────────────────────────────────────────
    postgis_statements=[
        "CREATE EXTENSION IF NOT EXISTS postgis",

        # outbreak_sites table
        """
        CREATE TABLE IF NOT EXISTS outbreak_sites (
            id            SERIAL PRIMARY KEY,
            pandemic_name VARCHAR(100),
            site_name     VARCHAR(150),
            country       VARCHAR(100),
            location      GEOMETRY(POINT, 4326),
            year_detected INTEGER,
            cases         INTEGER,
            deaths        INTEGER,
            notes         TEXT
        )
        """,

        # affected_regions table
        """
        CREATE TABLE IF NOT EXISTS affected_regions (
            id            SERIAL PRIMARY KEY,
            pandemic_name VARCHAR(100),
            region_name   VARCHAR(150) UNIQUE,
            geometry      GEOMETRY(POLYGON, 4326),
            severity      VARCHAR(20),
            year_start    INTEGER,
            year_end      INTEGER
        )
        """,

        # ── COVID-19 origin & major hotspot sites ─────────────────────────────
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('COVID-19', 'Wuhan', 'China',
             ST_SetSRID(ST_MakePoint(114.305, 30.593), 4326),
             2019, 50340, 3869,
             'First cluster of pneumonia cases linked to Huanan Seafood Market')
        ON CONFLICT DO NOTHING
        """,
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('COVID-19', 'New York City', 'USA',
             ST_SetSRID(ST_MakePoint(-74.006, 40.713), 4326),
             2020, 3000000, 43000,
             'Major early hotspot in the US; high excess mortality in spring 2020')
        ON CONFLICT DO NOTHING
        """,
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('COVID-19', 'Bergamo', 'Italy',
             ST_SetSRID(ST_MakePoint(9.670, 45.695), 4326),
             2020, 113000, 6200,
             'Lombardy province; overwhelmed ICU capacity in March 2020')
        ON CONFLICT DO NOTHING
        """,
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('COVID-19', 'Manaus', 'Brazil',
             ST_SetSRID(ST_MakePoint(-60.025, -3.119), 4326),
             2020, 300000, 14000,
             'Amazon city overwhelmed twice (2020 and Gamma variant 2021)')
        ON CONFLICT DO NOTHING
        """,
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('COVID-19', 'Mumbai', 'India',
             ST_SetSRID(ST_MakePoint(72.878, 19.076), 4326),
             2020, 1100000, 19600,
             'Largest city cluster during India Delta-wave 2021')
        ON CONFLICT DO NOTHING
        """,

        # ── Ebola 2014-2016 West Africa sites ────────────────────────────────
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('Ebola 2014-2016', 'Guéckédou', 'Guinea',
             ST_SetSRID(ST_MakePoint(-10.132, 8.570), 4326),
             2014, 2000, 1200,
             'Index community; first confirmed Ebola cases December 2013')
        ON CONFLICT DO NOTHING
        """,
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('Ebola 2014-2016', 'Freetown', 'Sierra Leone',
             ST_SetSRID(ST_MakePoint(-13.234, 8.484), 4326),
             2014, 8704, 3956,
             'Capital city; worst national toll of 2014-2016 epidemic')
        ON CONFLICT DO NOTHING
        """,
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('Ebola 2014-2016', 'Monrovia', 'Liberia',
             ST_SetSRID(ST_MakePoint(-10.800, 6.300), 4326),
             2014, 10672, 4808,
             'Capital of Liberia; second highest national death toll')
        ON CONFLICT DO NOTHING
        """,

        # ── Ebola DRC 2018-2020 sites ─────────────────────────────────────────
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('Ebola DRC 2018-2020', 'Beni', 'Democratic Republic of the Congo',
             ST_SetSRID(ST_MakePoint(29.474, 0.492), 4326),
             2018, 1200, 850,
             'Second-largest Ebola outbreak in history; active conflict zone')
        ON CONFLICT DO NOTHING
        """,
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('Ebola DRC 2018-2020', 'Butembo', 'Democratic Republic of the Congo',
             ST_SetSRID(ST_MakePoint(29.289, 0.143), 4326),
             2018, 900, 620,
             'Major urban centre affected during DRC 2018-2020 outbreak')
        ON CONFLICT DO NOTHING
        """,

        # ── SARS 2002-2003 sites ──────────────────────────────────────────────
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('SARS 2002-2003', 'Guangdong', 'China',
             ST_SetSRID(ST_MakePoint(113.266, 23.133), 4326),
             2002, 1512, 57,
             'First cluster of atypical pneumonia; November 2002')
        ON CONFLICT DO NOTHING
        """,
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('SARS 2002-2003', 'Hong Kong', 'China',
             ST_SetSRID(ST_MakePoint(114.177, 22.303), 4326),
             2003, 1755, 299,
             'Metropole Hotel superspreader event seeded global spread')
        ON CONFLICT DO NOTHING
        """,
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('SARS 2002-2003', 'Toronto', 'Canada',
             ST_SetSRID(ST_MakePoint(-79.383, 43.653), 4326),
             2003, 251, 43,
             'Largest SARS outbreak outside Asia')
        ON CONFLICT DO NOTHING
        """,

        # ── MERS sites ────────────────────────────────────────────────────────
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('MERS', 'Jeddah', 'Saudi Arabia',
             ST_SetSRID(ST_MakePoint(39.174, 21.521), 4326),
             2012, 340, 120,
             'Largest single-country MERS cluster; hospital nosocomial spread')
        ON CONFLICT DO NOTHING
        """,
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('MERS', 'Seoul', 'South Korea',
             ST_SetSRID(ST_MakePoint(126.978, 37.566), 4326),
             2015, 186, 38,
             'Largest MERS outbreak outside Middle East; single index patient')
        ON CONFLICT DO NOTHING
        """,

        # ── Spanish Flu sites ────────────────────────────────────────────────
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('Spanish Flu', 'Camp Funston', 'USA',
             ST_SetSRID(ST_MakePoint(-96.810, 39.520), 4326),
             1918, 500, 48,
             'Early amplification site; US Army base in Kansas')
        ON CONFLICT DO NOTHING
        """,
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('Spanish Flu', 'Philadelphia', 'USA',
             ST_SetSRID(ST_MakePoint(-75.165, 39.952), 4326),
             1918, 200000, 12000,
             'Liberty Loan parade October 1918 triggered mass spread')
        ON CONFLICT DO NOTHING
        """,

        # ── HIV/AIDS sites ────────────────────────────────────────────────────
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('HIV/AIDS', 'Kinshasa', 'Democratic Republic of the Congo',
             ST_SetSRID(ST_MakePoint(15.322, -4.322), 4326),
             1960, 1200000, 700000,
             'Genetic evidence points to Kinshasa as the origin of HIV-1 group M')
        ON CONFLICT DO NOTHING
        """,
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('HIV/AIDS', 'San Francisco', 'USA',
             ST_SetSRID(ST_MakePoint(-122.419, 37.774), 4326),
             1981, 22000, 20000,
             'First clinical reports of AIDS in gay men; 1981 MMWR report')
        ON CONFLICT DO NOTHING
        """,

        # ── Cholera 7th Pandemic sites ────────────────────────────────────────
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('Cholera 7th Pandemic', 'Sanaa', 'Yemen',
             ST_SetSRID(ST_MakePoint(44.205, 15.355), 4326),
             2016, 2500000, 3800,
             'Largest modern cholera crisis; armed conflict destroyed water systems')
        ON CONFLICT DO NOTHING
        """,
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('Cholera 7th Pandemic', 'Port-au-Prince', 'Haiti',
             ST_SetSRID(ST_MakePoint(-72.338, 18.543), 4326),
             2010, 820000, 9792,
             'Post-earthquake cholera introduction linked to UN peacekeepers')
        ON CONFLICT DO NOTHING
        """,

        # ── Black Death site ──────────────────────────────────────────────────
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('Black Death', 'Caffa (Feodosia)', 'Ukraine',
             ST_SetSRID(ST_MakePoint(35.383, 45.049), 4326),
             1346, NULL, NULL,
             'Crimean port city; Mongol siege; plague spread by fleeing Genoese ships to Mediterranean')
        ON CONFLICT DO NOTHING
        """,
        """
        INSERT INTO outbreak_sites
            (pandemic_name, site_name, country, location, year_detected, cases, deaths, notes)
        VALUES
            ('Black Death', 'Florence', 'Italy',
             ST_SetSRID(ST_MakePoint(11.255, 43.769), 4326),
             1348, NULL, 45000,
             'Lost ~60% of its population; documented by Boccaccio in the Decameron')
        ON CONFLICT DO NOTHING
        """,

        # ── Affected region polygons ──────────────────────────────────────────
        """
        INSERT INTO affected_regions (pandemic_name, region_name, geometry, severity, year_start, year_end)
        VALUES (
            'COVID-19', 'East Asia initial wave',
            ST_GeomFromText(
                'POLYGON((97 18, 145 18, 145 55, 97 55, 97 18))',
                4326),
            'high', 2019, 2020)
        ON CONFLICT (region_name) DO NOTHING
        """,
        """
        INSERT INTO affected_regions (pandemic_name, region_name, geometry, severity, year_start, year_end)
        VALUES (
            'COVID-19', 'Western Europe COVID-19',
            ST_GeomFromText(
                'POLYGON((-10 35, 25 35, 25 60, -10 60, -10 35))',
                4326),
            'high', 2020, 2022)
        ON CONFLICT (region_name) DO NOTHING
        """,
        """
        INSERT INTO affected_regions (pandemic_name, region_name, geometry, severity, year_start, year_end)
        VALUES (
            'Ebola 2014-2016', 'West Africa Ebola belt',
            ST_GeomFromText(
                'POLYGON((-16 4, -7 4, -7 15, -16 15, -16 4))',
                4326),
            'critical', 2014, 2016)
        ON CONFLICT (region_name) DO NOTHING
        """,
        """
        INSERT INTO affected_regions (pandemic_name, region_name, geometry, severity, year_start, year_end)
        VALUES (
            'HIV/AIDS', 'Sub-Saharan Africa HIV belt',
            ST_GeomFromText(
                'POLYGON((-20 -35, 52 -35, 52 15, -20 15, -20 -35))',
                4326),
            'critical', 1980, 9999)
        ON CONFLICT (region_name) DO NOTHING
        """,
        """
        INSERT INTO affected_regions (pandemic_name, region_name, geometry, severity, year_start, year_end)
        VALUES (
            'Black Death', 'Europe Black Death extent',
            ST_GeomFromText(
                'POLYGON((-10 35, 35 35, 35 60, -10 60, -10 35))',
                4326),
            'critical', 1347, 1353)
        ON CONFLICT (region_name) DO NOTHING
        """,

        # ── Spatial helper: nearest outbreak sites ────────────────────────────
        """
        CREATE OR REPLACE FUNCTION find_outbreak_sites_within_radius(
            center_lon FLOAT,
            center_lat FLOAT,
            radius_km  FLOAT
        )
        RETURNS TABLE(site_name VARCHAR, pandemic_name VARCHAR, distance_km FLOAT) AS $$
        BEGIN
            RETURN QUERY
            SELECT os.site_name,
                   os.pandemic_name,
                   ST_Distance(
                       os.location::geography,
                       ST_SetSRID(ST_MakePoint(center_lon, center_lat), 4326)::geography
                   ) / 1000 AS distance_km
            FROM outbreak_sites os
            WHERE ST_DWithin(
                os.location::geography,
                ST_SetSRID(ST_MakePoint(center_lon, center_lat), 4326)::geography,
                radius_km * 1000
            )
            ORDER BY distance_km;
        END;
        $$ LANGUAGE plpgsql
        """,
    ],

    # ── GraphDB – RDF/Turtle ─────────────────────────────────────────────────
    graphdb_named_graph="http://pangia.io/graphs/pandemic",
    graphdb_turtle="""\
@prefix :       <http://pangia.io/ontology/pandemic#> .
@prefix rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:   <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:    <http://www.w3.org/2002/07/owl#> .
@prefix xsd:    <http://www.w3.org/2001/XMLSchema#> .
@prefix geo:    <http://www.w3.org/2003/01/geo/wgs84_pos#> .

# ── Ontology declaration ────────────────────────────────────────────────────
<http://pangia.io/ontology/pandemic> a owl:Ontology ;
    rdfs:label "PangIA Épidémiologie Ontologie"@fr ;
    rdfs:label "PangIA Epidemiology Ontology"@en .

# ── Classes ─────────────────────────────────────────────────────────────────
:Pandemic a owl:Class ;
    rdfs:label "Pandémie / Épidémie"@fr ;
    rdfs:label "Pandemic / Epidemic"@en .

:OutbreakSite a owl:Class ;
    rdfs:label "Site de l'épidémie"@fr ;
    rdfs:label "Outbreak Site"@en .

:Country a owl:Class ;
    rdfs:label "Pays"@fr ;
    rdfs:label "Country"@en .

:Pathogen a owl:Class ;
    rdfs:label "Agent pathogène"@fr ;
    rdfs:label "Pathogen"@en .

# ── Object properties ───────────────────────────────────────────────────────
:originatedIn a owl:ObjectProperty ;
    rdfs:domain :Pandemic ;
    rdfs:range  :Country ;
    rdfs:label  "est apparu dans"@fr ;
    rdfs:label  "originated in"@en .

:spreadTo a owl:ObjectProperty ;
    rdfs:domain :Pandemic ;
    rdfs:range  :Country ;
    rdfs:label  "s'est propagé à"@fr ;
    rdfs:label  "spread to"@en .

:causedBy a owl:ObjectProperty ;
    rdfs:domain :Pandemic ;
    rdfs:range  :Pathogen ;
    rdfs:label  "causé par"@fr ;
    rdfs:label  "caused by"@en .

:relatedTo a owl:ObjectProperty ;
    rdfs:domain :Pandemic ;
    rdfs:range  :Pandemic ;
    rdfs:label  "lié à"@fr ;
    rdfs:label  "related to"@en .

:detectedAt a owl:ObjectProperty ;
    rdfs:domain :Pandemic ;
    rdfs:range  :OutbreakSite ;
    rdfs:label  "détecté à"@fr ;
    rdfs:label  "detected at"@en .

# ── Data properties ─────────────────────────────────────────────────────────
:yearStart          a owl:DatatypeProperty ; rdfs:range xsd:integer ; rdfs:label "année de début"@fr .
:yearEnd            a owl:DatatypeProperty ; rdfs:range xsd:integer ; rdfs:label "année de fin"@fr .
:totalCases         a owl:DatatypeProperty ; rdfs:range xsd:integer ; rdfs:label "cas totaux"@fr .
:totalDeaths        a owl:DatatypeProperty ; rdfs:range xsd:integer ; rdfs:label "décès totaux"@fr .
:caseFatalityRate   a owl:DatatypeProperty ; rdfs:range xsd:decimal ; rdfs:label "taux de létalité (%)"@fr .
:transmissionRoute  a owl:DatatypeProperty ; rdfs:range xsd:string  ; rdfs:label "voie de transmission"@fr .
:pandemicStatus     a owl:DatatypeProperty ; rdfs:range xsd:string  ; rdfs:label "statut"@fr .
:pathogenType       a owl:DatatypeProperty ; rdfs:range xsd:string  ; rdfs:label "type de pathogène"@fr .
:countryName        a owl:DatatypeProperty ; rdfs:range xsd:string  ; rdfs:label "pays"@fr .
:lat                a owl:DatatypeProperty ; rdfs:range xsd:decimal ; rdfs:label "latitude"@fr .
:lon                a owl:DatatypeProperty ; rdfs:range xsd:decimal ; rdfs:label "longitude"@fr .

# ── Pathogens ────────────────────────────────────────────────────────────────
:SARSCoV2 a :Pathogen ;
    rdfs:label "SARS-CoV-2" ;
    :pathogenType "coronavirus" .

:SARSCoV1 a :Pathogen ;
    rdfs:label "SARS-CoV-1" ;
    :pathogenType "coronavirus" .

:MERSCoV a :Pathogen ;
    rdfs:label "MERS-CoV" ;
    :pathogenType "coronavirus" .

:EbolaVirus a :Pathogen ;
    rdfs:label "Ebola virus (Zaire ebolavirus)" ;
    :pathogenType "filovirus" .

:HIV a :Pathogen ;
    rdfs:label "Human Immunodeficiency Virus (HIV)" ;
    :pathogenType "retrovirus" .

:InfluenzaH1N1 a :Pathogen ;
    rdfs:label "Influenza A (H1N1)" ;
    :pathogenType "influenza" .

:YersiniaPestis a :Pathogen ;
    rdfs:label "Yersinia pestis" ;
    :pathogenType "bacteria" .

:VariolaMajor a :Pathogen ;
    rdfs:label "Variola major / minor" ;
    :pathogenType "poxvirus" .

:MonkeypoxVirus a :Pathogen ;
    rdfs:label "Monkeypox virus (clade IIb)" ;
    :pathogenType "poxvirus" .

:VibrioCholera a :Pathogen ;
    rdfs:label "Vibrio cholerae O1 El Tor" ;
    :pathogenType "bacteria" .

# ── Individuals – Pandemics ──────────────────────────────────────────────────
:COVID19 a :Pandemic ;
    rdfs:label "COVID-19" ;
    :yearStart         "2019"^^xsd:integer ;
    :yearEnd           "2023"^^xsd:integer ;
    :totalCases        "770000000"^^xsd:integer ;
    :totalDeaths       "7000000"^^xsd:integer ;
    :caseFatalityRate  "0.9"^^xsd:decimal ;
    :transmissionRoute "respiratory droplets / aerosol" ;
    :pandemicStatus    "post-pandemic" ;
    :causedBy          :SARSCoV2 ;
    :originatedIn      :China ;
    :spreadTo          :Italy, :USA, :Brazil, :India, :France, :UnitedKingdom ;
    :detectedAt        :Wuhan ;
    :relatedTo         :SARS2002, :MERS .

:SARS2002 a :Pandemic ;
    rdfs:label "SARS 2002-2003" ;
    :yearStart         "2002"^^xsd:integer ;
    :yearEnd           "2003"^^xsd:integer ;
    :totalCases        "8098"^^xsd:integer ;
    :totalDeaths       "774"^^xsd:integer ;
    :caseFatalityRate  "9.6"^^xsd:decimal ;
    :transmissionRoute "respiratory droplets" ;
    :pandemicStatus    "ended" ;
    :causedBy          :SARSCoV1 ;
    :originatedIn      :China ;
    :detectedAt        :Guangdong ;
    :relatedTo         :COVID19, :MERS .

:MERS a :Pandemic ;
    rdfs:label "MERS" ;
    :yearStart         "2012"^^xsd:integer ;
    :totalCases        "2600"^^xsd:integer ;
    :totalDeaths       "935"^^xsd:integer ;
    :caseFatalityRate  "36.0"^^xsd:decimal ;
    :transmissionRoute "close contact / camels" ;
    :pandemicStatus    "ongoing (sporadic)" ;
    :causedBy          :MERSCoV ;
    :originatedIn      :SaudiArabia ;
    :spreadTo          :SouthKorea ;
    :detectedAt        :Jeddah ;
    :relatedTo         :COVID19, :SARS2002 .

:Ebola20142016 a :Pandemic ;
    rdfs:label "Ebola 2014-2016" ;
    :yearStart         "2014"^^xsd:integer ;
    :yearEnd           "2016"^^xsd:integer ;
    :totalCases        "28652"^^xsd:integer ;
    :totalDeaths       "11325"^^xsd:integer ;
    :caseFatalityRate  "39.5"^^xsd:decimal ;
    :transmissionRoute "direct contact with bodily fluids" ;
    :pandemicStatus    "ended" ;
    :causedBy          :EbolaVirus ;
    :originatedIn      :Guinea ;
    :spreadTo          :SierraLeone, :Liberia ;
    :detectedAt        :Gueckédou ;
    :relatedTo         :EbolaDRC20182020 .

:EbolaDRC20182020 a :Pandemic ;
    rdfs:label "Ebola DRC 2018-2020" ;
    :yearStart         "2018"^^xsd:integer ;
    :yearEnd           "2020"^^xsd:integer ;
    :totalCases        "3481"^^xsd:integer ;
    :totalDeaths       "2299"^^xsd:integer ;
    :caseFatalityRate  "66.0"^^xsd:decimal ;
    :transmissionRoute "direct contact with bodily fluids" ;
    :pandemicStatus    "ended" ;
    :causedBy          :EbolaVirus ;
    :originatedIn      :DRC ;
    :detectedAt        :Beni ;
    :relatedTo         :Ebola20142016 .

:HIVAIDS a :Pandemic ;
    rdfs:label "HIV/AIDS" ;
    :yearStart         "1981"^^xsd:integer ;
    :totalCases        "84200000"^^xsd:integer ;
    :totalDeaths       "40100000"^^xsd:integer ;
    :caseFatalityRate  "47.6"^^xsd:decimal ;
    :transmissionRoute "blood / sexual contact / mother-to-child" ;
    :pandemicStatus    "ongoing" ;
    :causedBy          :HIV ;
    :originatedIn      :DRC ;
    :spreadTo          :SouthAfrica, :USA ;
    :detectedAt        :Kinshasa .

:SpanishFlu a :Pandemic ;
    rdfs:label "Spanish Flu" ;
    :yearStart         "1918"^^xsd:integer ;
    :yearEnd           "1919"^^xsd:integer ;
    :totalCases        "500000000"^^xsd:integer ;
    :totalDeaths       "50000000"^^xsd:integer ;
    :caseFatalityRate  "10.0"^^xsd:decimal ;
    :transmissionRoute "respiratory droplets" ;
    :pandemicStatus    "ended" ;
    :causedBy          :InfluenzaH1N1 ;
    :detectedAt        :CampFunston ;
    :relatedTo         :H1N1SwineFlu2009 .

:H1N1SwineFlu2009 a :Pandemic ;
    rdfs:label "H1N1 Swine Flu 2009" ;
    :yearStart         "2009"^^xsd:integer ;
    :yearEnd           "2010"^^xsd:integer ;
    :totalCases        "700000000"^^xsd:integer ;
    :totalDeaths       "284000"^^xsd:integer ;
    :caseFatalityRate  "0.04"^^xsd:decimal ;
    :transmissionRoute "respiratory droplets" ;
    :pandemicStatus    "ended" ;
    :causedBy          :InfluenzaH1N1 ;
    :originatedIn      :Mexico ;
    :relatedTo         :SpanishFlu .

:BlackDeath a :Pandemic ;
    rdfs:label "Black Death" ;
    :yearStart         "1347"^^xsd:integer ;
    :yearEnd           "1353"^^xsd:integer ;
    :totalCases        "75000000"^^xsd:integer ;
    :totalDeaths       "50000000"^^xsd:integer ;
    :caseFatalityRate  "66.0"^^xsd:decimal ;
    :transmissionRoute "flea bites / respiratory (pneumonic)" ;
    :pandemicStatus    "ended" ;
    :causedBy          :YersiniaPestis ;
    :detectedAt        :Caffa .

:Smallpox a :Pandemic ;
    rdfs:label "Smallpox" ;
    :yearStart         "1900"^^xsd:integer ;
    :yearEnd           "1980"^^xsd:integer ;
    :totalCases        "300000000"^^xsd:integer ;
    :totalDeaths       "300000000"^^xsd:integer ;
    :caseFatalityRate  "30.0"^^xsd:decimal ;
    :transmissionRoute "respiratory droplets / skin contact" ;
    :pandemicStatus    "eradicated" ;
    :causedBy          :VariolaMajor ;
    :relatedTo         :Mpox2022 .

:Mpox2022 a :Pandemic ;
    rdfs:label "Mpox 2022" ;
    :yearStart         "2022"^^xsd:integer ;
    :totalCases        "90000"^^xsd:integer ;
    :totalDeaths       "150"^^xsd:integer ;
    :caseFatalityRate  "0.17"^^xsd:decimal ;
    :transmissionRoute "close physical contact" ;
    :pandemicStatus    "ongoing" ;
    :causedBy          :MonkeypoxVirus ;
    :originatedIn      :DRC ;
    :relatedTo         :Smallpox .

:Cholera7th a :Pandemic ;
    rdfs:label "Cholera 7th Pandemic" ;
    :yearStart         "1961"^^xsd:integer ;
    :totalCases        "2900000"^^xsd:integer ;
    :totalDeaths       "95000"^^xsd:integer ;
    :caseFatalityRate  "3.3"^^xsd:decimal ;
    :transmissionRoute "contaminated water / food" ;
    :pandemicStatus    "ongoing" ;
    :causedBy          :VibrioCholera ;
    :spreadTo          :Yemen, :Haiti .

# ── Individuals – Countries ──────────────────────────────────────────────────
:China a :Country ; rdfs:label "China"@en .
:Guinea a :Country ; rdfs:label "Guinea"@en .
:SierraLeone a :Country ; rdfs:label "Sierra Leone"@en .
:Liberia a :Country ; rdfs:label "Liberia"@en .
:DRC a :Country ; rdfs:label "Democratic Republic of the Congo"@en .
:USA a :Country ; rdfs:label "USA"@en .
:Brazil a :Country ; rdfs:label "Brazil"@en .
:India a :Country ; rdfs:label "India"@en .
:SaudiArabia a :Country ; rdfs:label "Saudi Arabia"@en .
:SouthKorea a :Country ; rdfs:label "South Korea"@en .
:Italy a :Country ; rdfs:label "Italy"@en .
:France a :Country ; rdfs:label "France"@en .
:UnitedKingdom a :Country ; rdfs:label "United Kingdom"@en .
:SouthAfrica a :Country ; rdfs:label "South Africa"@en .
:Mexico a :Country ; rdfs:label "Mexico"@en .
:Yemen a :Country ; rdfs:label "Yemen"@en .
:Haiti a :Country ; rdfs:label "Haiti"@en .

# ── Individuals – Outbreak Sites ─────────────────────────────────────────────
:Wuhan a :OutbreakSite ;
    rdfs:label "Wuhan" ;
    :countryName "China" ;
    :lat "30.593"^^xsd:decimal ;
    :lon "114.305"^^xsd:decimal .

:Gueckédou a :OutbreakSite ;
    rdfs:label "Guéckédou" ;
    :countryName "Guinea" ;
    :lat "8.570"^^xsd:decimal ;
    :lon "-10.132"^^xsd:decimal .

:Kinshasa a :OutbreakSite ;
    rdfs:label "Kinshasa" ;
    :countryName "Democratic Republic of the Congo" ;
    :lat "-4.322"^^xsd:decimal ;
    :lon "15.322"^^xsd:decimal .

:Beni a :OutbreakSite ;
    rdfs:label "Beni" ;
    :countryName "Democratic Republic of the Congo" ;
    :lat "0.492"^^xsd:decimal ;
    :lon "29.474"^^xsd:decimal .

:Guangdong a :OutbreakSite ;
    rdfs:label "Guangdong" ;
    :countryName "China" ;
    :lat "23.133"^^xsd:decimal ;
    :lon "113.266"^^xsd:decimal .

:Jeddah a :OutbreakSite ;
    rdfs:label "Jeddah" ;
    :countryName "Saudi Arabia" ;
    :lat "21.521"^^xsd:decimal ;
    :lon "39.174"^^xsd:decimal .

:CampFunston a :OutbreakSite ;
    rdfs:label "Camp Funston" ;
    :countryName "USA" ;
    :lat "39.520"^^xsd:decimal ;
    :lon "-96.810"^^xsd:decimal .

:Caffa a :OutbreakSite ;
    rdfs:label "Caffa (Feodosia)" ;
    :countryName "Ukraine" ;
    :lat "45.049"^^xsd:decimal ;
    :lon "35.383"^^xsd:decimal .
""",

    # ── Agent guidelines (theme-specific) ─────────────────────────────────────
    neo4j_guidelines="""\
- For questions about pandemic origins use MATCH (p:Pandemic)-[:ORIGINATED_IN]->(c:Country).
- Use SPREAD_TO relationships to find affected countries and peak case counts.
- Use RELATED_TO to discover pandemics caused by the same pathogen family.
- Pandemic names in the graph match exactly the English names with dates where applicable
  (e.g. 'COVID-19', 'Ebola 2014-2016', 'SARS 2002-2003'). Use exact strings.
- year_end = 9999 means the pandemic is still ongoing.
- When returning Country nodes, include country.iso2 and country.continent.
""",

    postgis_guidelines="""\
- outbreak_sites.location is a GEOMETRY(POINT,4326) in WGS-84.
  Cast to ::geography for metre-accurate ST_Distance / ST_DWithin results.
- affected_regions.geometry is a GEOMETRY(POLYGON,4326) representing the
  approximate geographic extent of the outbreak.
- Use ST_Contains(region.geometry, site.location) to find which region a site falls in.
- affected_regions.severity is one of: 'critical', 'high', 'moderate', 'low'.
- year_end = 9999 means the outbreak is still ongoing.
""",

    rdf_guidelines="""\
- Use PREFIX : <http://pangia.io/ontology/pandemic#> in every query.
- Always scope patterns inside GRAPH <http://pangia.io/graphs/pandemic> { ... }.
- Key object properties: :originatedIn, :spreadTo, :causedBy, :relatedTo, :detectedAt.
- Key data properties on :Pandemic: :yearStart, :yearEnd (xsd:integer),
  :totalCases, :totalDeaths (xsd:integer), :caseFatalityRate (xsd:decimal),
  :transmissionRoute, :pandemicStatus (xsd:string).
- :OutbreakSite has :lat and :lon (xsd:decimal) for geospatial queries.
- yearEnd = 9999 represents an ongoing pandemic; filter with FILTER(?yearEnd = 9999) for ongoing ones.
""",

    vector_guidelines="""\
- Documents cover: pandemic overviews, individual outbreak site descriptions,
  pathogen profiles, key timeline events, and epidemiological summaries.
- Available metadata filters: `type` (pandemic | site | pathogen | event | region),
  `name`, `year_start`, `country`, `pathogen_type`, `pandemic_status`.
- Prefer semantic search for narrative questions; use metadata filters when the
  user specifies a disease name, country, year range, or pathogen type.
""",

    # ── UI suggestions ────────────────────────────────────────────────────────
    suggestions=[
        "Where did COVID-19 originate and how did it spread globally?",
        "Which countries were most affected by the 2014-2016 Ebola outbreak?",
        "Compare the mortality rates of COVID-19, Ebola, and the Spanish Flu.",
        "Show all pandemic outbreak sites within 2000 km of Paris.",
        "Which pandemics are caused by coronaviruses?",
        "What is the geospatial extent of the HIV/AIDS epidemic in Africa?",
        "List all ongoing pandemics and their current death tolls.",
        "Which outbreak sites are located in the Democratic Republic of the Congo?",
    ],

    # ── ChromaDB documents ────────────────────────────────────────────────────
    chroma_documents=[
        {
            "text": (
                "COVID-19 is a respiratory disease caused by SARS-CoV-2, a novel "
                "betacoronavirus first identified in Wuhan, China in December 2019. "
                "The WHO declared it a pandemic on 11 March 2020. By the end of 2023 "
                "over 770 million cases and 7 million deaths had been confirmed "
                "worldwide. The virus spreads mainly through respiratory droplets and "
                "aerosols. Key early hotspots included Wuhan, northern Italy (Bergamo), "
                "New York City, and later Manaus (Brazil) and Mumbai (India). Multiple "
                "variants of concern emerged: Alpha, Beta, Delta, and Omicron."
            ),
            "metadata": {
                "type": "pandemic",
                "name": "COVID-19",
                "year_start": 2019,
                "pathogen_type": "coronavirus",
                "pandemic_status": "post-pandemic",
            },
        },
        {
            "text": (
                "The 2014-2016 West Africa Ebola epidemic was the largest Ebola "
                "outbreak in history, affecting Guinea, Sierra Leone, and Liberia. "
                "The index community was Guéckédou, Guinea, where the first cases "
                "appeared in December 2013. The outbreak killed 11,325 of 28,652 "
                "confirmed cases (case fatality rate ~40%). The epidemic overwhelmed "
                "fragile health systems, caused massive socioeconomic disruption, and "
                "was declared a Public Health Emergency of International Concern by WHO. "
                "The rVSV-ZEBOV vaccine (Ervebo) was developed and validated during this outbreak."
            ),
            "metadata": {
                "type": "pandemic",
                "name": "Ebola 2014-2016",
                "year_start": 2014,
                "pathogen_type": "filovirus",
                "pandemic_status": "ended",
                "country": "Guinea, Sierra Leone, Liberia",
            },
        },
        {
            "text": (
                "The Ebola outbreak in the Democratic Republic of the Congo (2018-2020) "
                "was the second largest in history, centred in North Kivu and Ituri "
                "provinces. The outbreak registered 3,481 cases and 2,299 deaths "
                "(case fatality rate ~66%). Response was severely hampered by active "
                "armed conflict; health workers were repeatedly attacked. The rVSV-ZEBOV "
                "vaccine was widely deployed for the first time during this outbreak. "
                "Major affected cities included Beni and Butembo."
            ),
            "metadata": {
                "type": "pandemic",
                "name": "Ebola DRC 2018-2020",
                "year_start": 2018,
                "pathogen_type": "filovirus",
                "pandemic_status": "ended",
                "country": "Democratic Republic of the Congo",
            },
        },
        {
            "text": (
                "The Spanish Flu (1918-1919) was caused by an H1N1 influenza A virus "
                "and is the deadliest pandemic in recorded history, infecting an "
                "estimated 500 million people (~27% of the world's population at the "
                "time) and killing 50-100 million. It struck in three waves (spring 1918, "
                "autumn 1918, winter 1918-19). The second wave was the deadliest. "
                "Unusually, it had high mortality in young adults (20-40 years). "
                "Early amplification occurred at US Army base Camp Funston (Kansas). "
                "Philadelphia's Liberty Loan parade in October 1918 caused massive spread. "
                "The 2009 H1N1 'Swine Flu' pandemic was caused by a descendant of this virus."
            ),
            "metadata": {
                "type": "pandemic",
                "name": "Spanish Flu",
                "year_start": 1918,
                "pathogen_type": "influenza",
                "pandemic_status": "ended",
            },
        },
        {
            "text": (
                "HIV/AIDS is an ongoing pandemic caused by the Human Immunodeficiency "
                "Virus (HIV). Genetic evidence traces the origin of HIV-1 group M to "
                "Kinshasa, DRC, around 1920. The epidemic was first recognised clinically "
                "in 1981 in San Francisco and New York among gay men. Since then, an "
                "estimated 84 million people have been infected and 40 million have died. "
                "Sub-Saharan Africa remains the most affected region (~67% of all cases). "
                "South Africa has the world's largest HIV epidemic (8.2 million people). "
                "Antiretroviral therapy (ART) has transformed HIV from a death sentence "
                "into a manageable chronic condition."
            ),
            "metadata": {
                "type": "pandemic",
                "name": "HIV/AIDS",
                "year_start": 1981,
                "pathogen_type": "retrovirus",
                "pandemic_status": "ongoing",
                "country": "global, sub-Saharan Africa",
            },
        },
        {
            "text": (
                "SARS (Severe Acute Respiratory Syndrome) was caused by SARS-CoV-1, a "
                "betacoronavirus that emerged in Guangdong, China in November 2002. It "
                "spread to 29 countries, infecting 8,098 people and killing 774 "
                "(CFR ~10%). A superspreader event at the Metropole Hotel in Hong Kong "
                "seeded outbreaks in Toronto, Singapore, and Vietnam. The outbreak was "
                "contained by July 2003. SARS-CoV-1 is closely related to SARS-CoV-2, "
                "the cause of COVID-19."
            ),
            "metadata": {
                "type": "pandemic",
                "name": "SARS 2002-2003",
                "year_start": 2002,
                "pathogen_type": "coronavirus",
                "pandemic_status": "ended",
                "country": "China, Hong Kong, Canada, Singapore",
            },
        },
        {
            "text": (
                "MERS (Middle East Respiratory Syndrome) is caused by MERS-CoV, a "
                "betacoronavirus first identified in Saudi Arabia in 2012. Dromedary "
                "camels are the animal reservoir. As of 2024, 2,600 cases and 935 deaths "
                "(CFR ~36%) have been reported. Most cases originate in the Arabian "
                "Peninsula. The largest outbreak outside the Middle East occurred in "
                "South Korea in 2015, where a single infected traveller caused 186 cases "
                "through hospital amplification. MERS-CoV shares the same betacoronavirus "
                "genus as SARS-CoV-1 and SARS-CoV-2."
            ),
            "metadata": {
                "type": "pandemic",
                "name": "MERS",
                "year_start": 2012,
                "pathogen_type": "coronavirus",
                "pandemic_status": "ongoing (sporadic)",
                "country": "Saudi Arabia, South Korea",
            },
        },
        {
            "text": (
                "The Black Death (1347-1353) was a catastrophic pandemic caused by "
                "Yersinia pestis, the plague bacterium. It killed an estimated "
                "75-200 million people in Eurasia, wiping out 30-60% of Europe's "
                "population. It originated in Central Asia and reached the Crimean port "
                "of Caffa in 1346. Genoese ships fleeing the siege of Caffa brought the "
                "disease to Sicily and then across Europe. Florence lost approximately "
                "60% of its population. The Black Death triggered profound demographic, "
                "economic, and cultural transformations, including the end of feudalism "
                "in much of Europe."
            ),
            "metadata": {
                "type": "pandemic",
                "name": "Black Death",
                "year_start": 1347,
                "pathogen_type": "bacteria",
                "pandemic_status": "ended",
                "country": "Europe, Asia",
            },
        },
        {
            "text": (
                "Wuhan (武汉) is a city of 11 million people in Hubei province, central "
                "China (30.59°N, 114.31°E). In December 2019 a cluster of pneumonia "
                "cases of unknown aetiology was linked to the Huanan Seafood Wholesale "
                "Market. This was later identified as the first known cluster of "
                "COVID-19. Wuhan was placed under a strict lockdown from 23 January "
                "to 8 April 2020. The city reported 50,340 confirmed cases and "
                "3,869 deaths during the initial outbreak. Wuhan Institute of Virology "
                "(WIV) is a major bat coronavirus research centre located in the city."
            ),
            "metadata": {
                "type": "site",
                "name": "Wuhan",
                "pandemic_name": "COVID-19",
                "country": "China",
                "year_start": 2019,
            },
        },
        {
            "text": (
                "Guéckédou is a prefecture in the Forest Guinea region of Guinea "
                "(8.57°N, 10.13°W), near the borders with Sierra Leone and Liberia. "
                "In December 2013 the first Ebola cases of the 2014-2016 West Africa "
                "epidemic emerged here. The forested landscape, cross-border mobility, "
                "and traditional burial practices facilitated early spread. The "
                "proximity to international borders allowed rapid amplification across "
                "three countries. Guéckédou became the epidemiological index community "
                "for the deadliest Ebola epidemic in history."
            ),
            "metadata": {
                "type": "site",
                "name": "Guéckédou",
                "pandemic_name": "Ebola 2014-2016",
                "country": "Guinea",
                "year_start": 2013,
            },
        },
        {
            "text": (
                "Kinshasa (capital of the DRC, 4.32°S, 15.32°E) is the city where "
                "genetic analyses trace the origin of HIV-1 group M to around 1920. "
                "The virus likely evolved from a chimpanzee SIV (simian immunodeficiency "
                "virus) in the Cameroon-DRC region and then spread via the railway "
                "network through Kinshasa. The city has one of the oldest known HIV "
                "samples (preserved blood from 1959). Kinshasa has also experienced "
                "multiple Ebola outbreaks throughout the 1970s-2020s. It is a critical "
                "hub for understanding the emergence and spread of several zoonotic diseases."
            ),
            "metadata": {
                "type": "site",
                "name": "Kinshasa",
                "pandemic_name": "HIV/AIDS",
                "country": "Democratic Republic of the Congo",
                "year_start": 1920,
            },
        },
        {
            "text": (
                "The H1N1 Swine Flu pandemic of 2009 was caused by a novel influenza "
                "A(H1N1)pdm09 virus that emerged in Mexico in early 2009 and spread "
                "globally. WHO declared it a pandemic in June 2009. Estimated 700 "
                "million to 1.4 billion people were infected; the best estimate for "
                "deaths is 284,000 (range 151,700-575,400). Although less lethal than "
                "feared, it disproportionately affected young adults and pregnant women. "
                "The virus was a reassortant combining human, avian, and swine influenza "
                "gene segments. It is related to the 1918 Spanish Flu H1N1 virus."
            ),
            "metadata": {
                "type": "pandemic",
                "name": "H1N1 Swine Flu 2009",
                "year_start": 2009,
                "pathogen_type": "influenza",
                "pandemic_status": "ended",
                "country": "global",
            },
        },
        {
            "text": (
                "Smallpox was caused by the Variola major and Variola minor viruses "
                "(orthopoxviruses). In the 20th century alone it killed an estimated "
                "300 million people. It was the target of the first vaccine (Edward "
                "Jenner, 1796) and the only human disease to be globally eradicated, "
                "certified by WHO in 1980. The last natural case was in Somalia in "
                "1977. Stocks of the virus are maintained at only two WHO-approved "
                "laboratories (CDC Atlanta and VECTOR Novosibirsk). Mpox (monkeypox) "
                "is caused by a related orthopoxvirus and has expanded globally since 2022."
            ),
            "metadata": {
                "type": "pandemic",
                "name": "Smallpox",
                "year_start": 1900,
                "pathogen_type": "poxvirus",
                "pandemic_status": "eradicated",
            },
        },
        {
            "text": (
                "The Cholera 7th pandemic began in Indonesia in 1961 and is still "
                "ongoing, caused by Vibrio cholerae O1 El Tor biotype. Cholera spreads "
                "through contaminated water and food. Major 21st-century crises include "
                "Yemen (2016-present; 2.5 million cases, 3,800 deaths) and Haiti "
                "(2010-2019; 820,000 cases, 9,792 deaths). The Yemen crisis is the "
                "largest in modern history, fuelled by conflict and destroyed water "
                "infrastructure. The Haiti outbreak followed the 2010 earthquake and "
                "was linked to UN peacekeepers from Nepal."
            ),
            "metadata": {
                "type": "pandemic",
                "name": "Cholera 7th Pandemic",
                "year_start": 1961,
                "pathogen_type": "bacteria",
                "pandemic_status": "ongoing",
                "country": "global, Yemen, Haiti",
            },
        },
    ],
)
