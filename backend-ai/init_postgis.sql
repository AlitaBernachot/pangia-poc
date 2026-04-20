-- SPDX-FileCopyrightText: 2026 AlitaBernachot
--
-- SPDX-License-Identifier: MIT

-- =============================================================================
-- PangIA — PostGIS demo database
-- Initialised automatically on first container start.
-- Contains three example tables covering the main PostGIS use-cases:
--   • lieux_interet   — point-geometry POIs (cafés, museums, hospitals, …)
--   • communes        — polygon-geometry municipalities
--   • zones_risque    — polygon-geometry risk / special zones
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------------------------
-- 1. lieux_interet — Points of interest (POINT geometry, SRID 4326)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lieux_interet (
    id          SERIAL PRIMARY KEY,
    nom         TEXT        NOT NULL,
    categorie   TEXT        NOT NULL,   -- musee, hopital, parc, restaurant, …
    adresse     TEXT,
    ville       TEXT        NOT NULL,
    code_postal TEXT,
    geom        GEOMETRY(Point, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lieux_geom   ON lieux_interet USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_lieux_cat    ON lieux_interet (categorie);
CREATE INDEX IF NOT EXISTS idx_lieux_ville  ON lieux_interet (ville);

INSERT INTO lieux_interet (nom, categorie, adresse, ville, code_postal, geom) VALUES
  ('Musée du Louvre',           'musee',      '75001 Rue de Rivoli',         'Paris',        '75001', ST_SetSRID(ST_MakePoint(2.3376,   48.8606),  4326)),
  ('Musée d''Orsay',            'musee',      '1 Rue de la Légion d''Honneur','Paris',        '75007', ST_SetSRID(ST_MakePoint(2.3266,   48.8600),  4326)),
  ('Centre Pompidou',           'musee',      'Place Georges-Pompidou',      'Paris',        '75004', ST_SetSRID(ST_MakePoint(2.3522,   48.8607),  4326)),
  ('Hôpital Pitié-Salpêtrière', 'hopital',    '47-83 Bd de l''Hôpital',      'Paris',        '75013', ST_SetSRID(ST_MakePoint(2.3598,   48.8383),  4326)),
  ('Hôpital Lariboisière',      'hopital',    '2 Rue Ambroise Paré',         'Paris',        '75010', ST_SetSRID(ST_MakePoint(2.3553,   48.8796),  4326)),
  ('Jardin du Luxembourg',      'parc',       'Rue de Médicis',              'Paris',        '75006', ST_SetSRID(ST_MakePoint(2.3372,   48.8462),  4326)),
  ('Parc de la Tête d''Or',     'parc',       'Blvd des Belges',             'Lyon',         '69006', ST_SetSRID(ST_MakePoint(4.8567,   45.7784),  4326)),
  ('Vieux-Port de Marseille',   'monument',   'Quai du Port',                'Marseille',    '13002', ST_SetSRID(ST_MakePoint(5.3698,   43.2965),  4326)),
  ('Place du Capitole',         'monument',   'Place du Capitole',           'Toulouse',     '31000', ST_SetSRID(ST_MakePoint(1.4442,   43.6047),  4326)),
  ('Cathédrale Notre-Dame',     'monument',   'Place de la Cathédrale',      'Strasbourg',   '67000', ST_SetSRID(ST_MakePoint(7.7521,   48.5814),  4326)),
  ('Château des Ducs de Bretagne','monument', '4 Place Marc Elder',          'Nantes',       '44000', ST_SetSRID(ST_MakePoint(-1.5496,  47.2163),  4326)),
  ('Palais des Arts',           'musee',      'Place de Gaulle',             'Lille',        '59000', ST_SetSRID(ST_MakePoint(3.0615,   50.6292),  4326)),
  ('Clinique Saint-Luc',        'hopital',    '1 Rue Saint-Luc',             'Bordeaux',     '33000', ST_SetSRID(ST_MakePoint(-0.5792,  44.8378),  4326)),
  ('Jardin des Plantes',        'parc',       'Bd Daviers',                  'Montpellier',  '34000', ST_SetSRID(ST_MakePoint(3.8768,   43.6119),  4326)),
  ('Opéra de Nice',             'monument',   '4 Rue Saint-François de Paule','Nice',        '06300', ST_SetSRID(ST_MakePoint(7.2747,   43.6954),  4326))
ON CONFLICT DO NOTHING;


-- ---------------------------------------------------------------------------
-- 2. communes — French municipalities (simplified POLYGON geometry, SRID 4326)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS communes (
    id            SERIAL PRIMARY KEY,
    code_insee    TEXT        NOT NULL UNIQUE,
    nom           TEXT        NOT NULL,
    departement   TEXT        NOT NULL,
    region        TEXT        NOT NULL,
    population    INTEGER,
    superficie_km2 NUMERIC(10,2),
    geom          GEOMETRY(MultiPolygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_communes_geom      ON communes USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_communes_insee     ON communes (code_insee);
CREATE INDEX IF NOT EXISTS idx_communes_dept      ON communes (departement);

-- Simplified bounding-box polygons for demo purposes
-- (replace with real IGN / OpenStreetMap data in production)
INSERT INTO communes (code_insee, nom, departement, region, population, superficie_km2, geom) VALUES
  ('75056', 'Paris',       '75 – Paris',             'Île-de-France',     2161000, 105.40,
    ST_Multi(ST_MakeEnvelope(2.2241, 48.8156, 2.4699, 48.9022, 4326))),
  ('69123', 'Lyon',        '69 – Rhône',             'Auvergne-Rhône-Alpes', 522228, 47.87,
    ST_Multi(ST_MakeEnvelope(4.7721, 45.7074, 4.8979, 45.8081, 4326))),
  ('13055', 'Marseille',   '13 – Bouches-du-Rhône',  'Provence-Alpes-Côte d''Azur', 868277, 240.62,
    ST_Multi(ST_MakeEnvelope(5.2290, 43.1706, 5.5310, 43.3919, 4326))),
  ('31555', 'Toulouse',    '31 – Haute-Garonne',     'Occitanie',         486828, 118.30,
    ST_Multi(ST_MakeEnvelope(1.3480, 43.5312, 1.5036, 43.6680, 4326))),
  ('06088', 'Nice',        '06 – Alpes-Maritimes',   'Provence-Alpes-Côte d''Azur', 342669, 71.92,
    ST_Multi(ST_MakeEnvelope(7.1883, 43.6452, 7.3221, 43.7674, 4326))),
  ('67482', 'Strasbourg',  '67 – Bas-Rhin',          'Grand Est',         287228, 78.26,
    ST_Multi(ST_MakeEnvelope(7.6968, 48.5289, 7.8101, 48.6308, 4326))),
  ('33063', 'Bordeaux',    '33 – Gironde',           'Nouvelle-Aquitaine', 257068, 49.36,
    ST_Multi(ST_MakeEnvelope(-0.6302, 44.7866, -0.5285, 44.8963, 4326))),
  ('59350', 'Lille',       '59 – Nord',              'Hauts-de-France',   236234, 34.86,
    ST_Multi(ST_MakeEnvelope(2.9982, 50.5970, 3.1200, 50.6753, 4326))),
  ('34172', 'Montpellier', '34 – Hérault',           'Occitanie',         295542, 56.88,
    ST_Multi(ST_MakeEnvelope(3.7927, 43.5735, 3.9430, 43.6633, 4326))),
  ('44109', 'Nantes',      '44 – Loire-Atlantique',  'Pays de la Loire',  320732, 65.19,
    ST_Multi(ST_MakeEnvelope(-1.6338, 47.1766, -1.4751, 47.2895, 4326)))
ON CONFLICT DO NOTHING;


-- ---------------------------------------------------------------------------
-- 3. zones_risque — Risk / special zones (POLYGON geometry, SRID 4326)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS zones_risque (
    id          SERIAL PRIMARY KEY,
    code        TEXT        NOT NULL UNIQUE,
    nom         TEXT        NOT NULL,
    type_risque TEXT        NOT NULL,  -- inondation, incendie, sismique, pollution, …
    niveau      TEXT        NOT NULL,  -- faible, modere, eleve, critique
    commune     TEXT,
    departement TEXT,
    geom        GEOMETRY(Polygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_zones_geom  ON zones_risque USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_zones_type  ON zones_risque (type_risque);
CREATE INDEX IF NOT EXISTS idx_zones_niv   ON zones_risque (niveau);

INSERT INTO zones_risque (code, nom, type_risque, niveau, commune, departement, geom) VALUES
  ('Z-IND-75-001', 'Zone inondable Seine rive gauche',    'inondation', 'eleve',
    'Paris', '75',
    ST_MakeEnvelope(2.3400, 48.8480, 2.3700, 48.8580, 4326)),
  ('Z-IND-75-002', 'Zone inondable Seine rive droite',    'inondation', 'modere',
    'Paris', '75',
    ST_MakeEnvelope(2.3300, 48.8600, 2.3650, 48.8700, 4326)),
  ('Z-IND-69-001', 'Zone inondable Saône Lyon',           'inondation', 'modere',
    'Lyon', '69',
    ST_MakeEnvelope(4.8100, 45.7600, 4.8400, 45.7900, 4326)),
  ('Z-INC-13-001', 'Zone à risque incendie Marseille est','incendie',  'eleve',
    'Marseille', '13',
    ST_MakeEnvelope(5.4200, 43.3000, 5.5000, 43.3700, 4326)),
  ('Z-SIS-06-001', 'Zone sismique Nice littoral',         'sismique',  'faible',
    'Nice', '06',
    ST_MakeEnvelope(7.2000, 43.6800, 7.3000, 43.7500, 4326)),
  ('Z-POL-67-001', 'Zone pollution industrielle Strasbourg','pollution','modere',
    'Strasbourg', '67',
    ST_MakeEnvelope(7.7200, 48.5600, 7.7800, 48.6000, 4326)),
  ('Z-IND-44-001', 'Zone inondable Loire Nantes',         'inondation', 'critique',
    'Nantes', '44',
    ST_MakeEnvelope(-1.6000, 47.1900, -1.5000, 47.2400, 4326)),
  ('Z-INC-33-001', 'Zone risque incendie forêt Bordeaux', 'incendie',  'eleve',
    'Bordeaux', '33',
    ST_MakeEnvelope(-0.6100, 44.7900, -0.5400, 44.8600, 4326))
ON CONFLICT DO NOTHING;
