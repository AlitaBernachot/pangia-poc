# Corpus folder

Place the files you want to ingest here. The ingest tool supports:

| Extension | Description |
|-----------|-------------|
| `.pdf`    | Text is extracted page-by-page (requires `pdfplumber`). |
| `.csv`    | Tabular data; rows with lat/lon columns are routed to PostGIS. |
| `.json`   | Arbitrary JSON; top-level arrays of objects become graph nodes. |
| `.geojson`| GeoJSON FeatureCollections are routed to PostGIS + Neo4j. |

Sub-directories are scanned recursively.

## Quick start

1. Drop your files here (or in sub-folders).
2. Open `backend/tools/ingest_corpus.ipynb` in Jupyter.
3. Set `CORPUS_PATH`, `THEME_NAME` and `OPENAI_API_KEY` in **cell 1**.
4. Run all cells.
5. The generated seed file will be written to
   `backend/app/db/themes/<theme_name>.py`.
6. Add `SEED_DB=true` and `SEED_THEME=<theme_name>` to your `.env` and
   restart the backend to populate the databases.
