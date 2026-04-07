"""
Corpus Ingestion Tool for PangIA.

Reads files from a *corpus* directory (PDF, CSV, GeoJSON, JSON), extracts
structured knowledge with an LLM, and produces a PangIA seed-theme Python
module that can be used to populate **Neo4j**, **PostGIS**, **RDF / GraphDB**
and **ChromaDB** databases.

Standalone CLI usage
--------------------
Run from the ``backend/`` directory::

    python -m tools.ingest_corpus \\
        --corpus /corpus \\
        --theme  my_theme \\
        --output app/db/themes/my_theme.py

Notebook usage (see ``ingest_corpus.ipynb``)
--------------------------------------------
::

    import sys
    sys.path.insert(0, "/path/to/backend")

    from tools.ingest_corpus import CorpusIngestor

    ingestor = CorpusIngestor(
        corpus_path="/corpus",
        theme_name="my_theme",
        openai_api_key="sk-...",
    )
    result  = ingestor.ingest()
    outfile = ingestor.save_seed_file(result)
    print("Seed written to", outfile)
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
import re
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional PDF dependency
# ---------------------------------------------------------------------------
try:
    import pdfplumber  # type: ignore

    _PDF_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PDF_AVAILABLE = False
    logger.debug(
        "pdfplumber not installed – PDF ingestion disabled. "
        "Install with: pip install pdfplumber"
    )

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class FileContent:
    """Parsed content extracted from a single corpus file."""

    path: str
    file_type: str  # "pdf" | "csv" | "geojson" | "json"
    raw_text: str
    structured_data: Any = None  # parsed dict/list for JSON/GeoJSON/CSV rows


@dataclass
class IngestionResult:
    """Complete result produced by :class:`CorpusIngestor.ingest`."""

    theme_name: str
    files_processed: list[str] = field(default_factory=list)
    # Neo4j
    neo4j_statements: list[str] = field(default_factory=list)
    neo4j_schema_prompt: str = ""
    neo4j_guidelines: str = ""
    # PostGIS
    postgis_statements: list[str] = field(default_factory=list)
    postgis_schema_prompt: str = ""
    postgis_guidelines: str = ""
    # GraphDB / RDF
    graphdb_named_graph: str = ""
    graphdb_turtle: str = ""
    rdf_schema_prompt: str = ""
    rdf_guidelines: str = ""
    # ChromaDB
    chroma_documents: list[dict] = field(default_factory=list)
    vector_guidelines: str = ""
    # UI
    suggestions: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class CorpusIngestor:
    """
    Reads files from a corpus directory, extracts knowledge with an LLM, and
    produces a PangIA seed theme Python module.

    Parameters
    ----------
    corpus_path:
        Directory that contains the files to ingest (default ``/corpus``).
    theme_name:
        Short identifier for the generated theme module, e.g. ``"climate"``.
    output_dir:
        Where to write the generated seed file.  Defaults to the
        ``app/db/themes/`` directory relative to this file's location.
    openai_api_key:
        OpenAI API key.  Falls back to the ``OPENAI_API_KEY`` env variable.
    openai_model:
        Chat-completion model to use (default ``"gpt-4o-mini"``).
    temperature:
        LLM sampling temperature (default ``0.0``).
    max_content_chars:
        Maximum characters of corpus text forwarded to each LLM call.
        Increase for richer models, decrease to stay within token limits.
    """

    SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
        {".pdf", ".csv", ".json", ".geojson"}
    )

    def __init__(
        self,
        corpus_path: str | Path = "/corpus",
        theme_name: str = "custom",
        output_dir: str | Path | None = None,
        openai_api_key: str | None = None,
        openai_model: str = "gpt-4o-mini",
        temperature: float = 0.0,
        max_content_chars: int = 16_000,
    ) -> None:
        self.corpus_path = Path(corpus_path)
        self.theme_name = theme_name
        self.output_dir = (
            Path(output_dir)
            if output_dir is not None
            else Path(__file__).parent.parent / "app" / "db" / "themes"
        )
        self._openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        self._openai_model = openai_model
        self._temperature = temperature
        self.max_content_chars = max_content_chars
        self._llm: Any = None

    # ------------------------------------------------------------------
    # LLM accessor (lazy init)
    # ------------------------------------------------------------------

    @property
    def llm(self) -> Any:
        """Return (lazily constructed) ChatOpenAI instance."""
        if self._llm is None:
            try:
                from langchain_openai import ChatOpenAI  # type: ignore
            except ImportError as exc:
                raise RuntimeError(
                    "langchain-openai is required. "
                    "Install with: pip install langchain-openai"
                ) from exc
            self._llm = ChatOpenAI(
                api_key=self._openai_api_key,
                model=self._openai_model,
                temperature=self._temperature,
            )
        return self._llm

    # ------------------------------------------------------------------
    # File discovery
    # ------------------------------------------------------------------

    def discover_files(self) -> list[Path]:
        """Return all supported files under *corpus_path* (recursive)."""
        if not self.corpus_path.exists():
            raise FileNotFoundError(
                f"Corpus directory not found: {self.corpus_path}"
            )
        files: list[Path] = []
        for ext in self.SUPPORTED_EXTENSIONS:
            files.extend(self.corpus_path.rglob(f"*{ext}"))
        files.sort()
        return files

    # ------------------------------------------------------------------
    # File readers
    # ------------------------------------------------------------------

    def read_file(self, path: Path) -> FileContent:
        """Read *path* and return a :class:`FileContent` object."""
        ext = path.suffix.lower()
        if ext == ".pdf":
            return self._read_pdf(path)
        if ext == ".csv":
            return self._read_csv(path)
        if ext in (".json", ".geojson"):
            return self._read_json(path)
        raise ValueError(f"Unsupported extension: {ext}")

    def _read_pdf(self, path: Path) -> FileContent:
        if not _PDF_AVAILABLE:
            logger.warning(
                "Skipping %s – pdfplumber not installed. "
                "Run: pip install pdfplumber",
                path.name,
            )
            return FileContent(path=str(path), file_type="pdf", raw_text="")

        import pdfplumber  # type: ignore

        pages: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(text)
        raw = "\n\n".join(pages)
        return FileContent(path=str(path), file_type="pdf", raw_text=raw)

    def _read_csv(self, path: Path) -> FileContent:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)

        buf = io.StringIO()
        if rows:
            headers = list(rows[0].keys())
            buf.write(f"CSV: {path.name}\nColumns: {', '.join(headers)}\n")
            buf.write(f"Total rows: {len(rows)}\n\n")
            sample = rows[:20]
            writer = csv.DictWriter(buf, fieldnames=headers)
            writer.writeheader()
            writer.writerows(sample)
            if len(rows) > 20:
                buf.write(f"\n… ({len(rows) - 20} more rows)\n")
        return FileContent(
            path=str(path),
            file_type="csv",
            raw_text=buf.getvalue(),
            structured_data=rows,
        )

    def _read_json(self, path: Path) -> FileContent:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)

        _GEO_TYPES = frozenset(
            {
                "FeatureCollection",
                "Feature",
                "GeometryCollection",
                "Point",
                "MultiPoint",
                "LineString",
                "MultiLineString",
                "Polygon",
                "MultiPolygon",
            }
        )
        is_geo = path.suffix.lower() == ".geojson" or (
            isinstance(data, dict) and data.get("type") in _GEO_TYPES
        )
        file_type = "geojson" if is_geo else "json"
        label = "GeoJSON" if is_geo else "JSON"

        raw = f"{label}: {path.name}\n"
        raw += json.dumps(data, indent=2, ensure_ascii=False)[:10_000]
        return FileContent(
            path=str(path),
            file_type=file_type,
            raw_text=raw,
            structured_data=data,
        )

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------

    def _call_llm(self, system_prompt: str, user_content: str) -> str:
        """Invoke the LLM and return the response as a string."""
        from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore

        response = self.llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content),
            ]
        )
        return str(response.content).strip()

    @staticmethod
    def _extract_json(text: str) -> Any:
        """Extract and parse a JSON value from *text* (handles fenced blocks)."""
        # Try to strip a ```json … ``` block first
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL | re.IGNORECASE)
        candidate = match.group(1).strip() if match else text.strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        # Fallback: grab the first [ ... ] or { ... }
        for pattern in (r"(\[.*\])", r"(\{.*\})"):
            m = re.search(pattern, candidate, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    continue
        return None

    def _summarize_contents(
        self, contents: list[FileContent], max_chars: int | None = None
    ) -> str:
        """Concatenate file contents into a single string, capped at *max_chars*."""
        limit = max_chars if max_chars is not None else self.max_content_chars
        parts: list[str] = []
        remaining = limit
        for fc in contents:
            if remaining <= 0:
                break
            header = f"\n--- {Path(fc.path).name} ({fc.file_type}) ---\n"
            text = fc.raw_text
            available = remaining - len(header)
            if available <= 0:
                break
            if len(text) > available:
                text = text[:available] + "\n[… truncated]"
            parts.append(header + text)
            remaining -= len(header) + len(text)
        return "\n".join(parts)

    @staticmethod
    def _has_geo_columns(fc: FileContent) -> bool:
        """Return True if a CSV :class:`FileContent` has lat/lon columns."""
        if fc.file_type != "csv" or not fc.structured_data:
            return False
        first_row = fc.structured_data[0] if fc.structured_data else {}
        headers = {k.lower() for k in first_row.keys()}
        geo_kw = {"lat", "lon", "lng", "latitude", "longitude",
                  "geometry", "geom", "location", "coordinates"}
        return bool(headers & geo_kw)

    # ------------------------------------------------------------------
    # LLM-based data generators
    # ------------------------------------------------------------------

    def _generate_neo4j_data(
        self, contents: list[FileContent]
    ) -> tuple[list[str], str, str]:
        """Return (cypher_statements, schema_prompt, guidelines)."""
        combined = self._summarize_contents(contents)
        system = textwrap.dedent(f"""
            You are a graph-database expert.
            Given the input data, generate:
            1. A list of idempotent Cypher MERGE statements that create nodes and
               relationships in Neo4j.  Each statement must be complete, executable
               on its own, and use MERGE (not CREATE).
            2. A schema description listing node labels, their properties and
               relationship types.
            3. Brief agent guidelines for querying this graph.

            Theme name: {self.theme_name!r}

            Return **only** a JSON object (no prose, no code fences) with this
            exact structure:
            {{
              "statements": ["MERGE ...", ...],
              "schema_prompt": "Node labels:\\n- ...",
              "guidelines": "..."
            }}
        """).strip()

        raw = self._call_llm(system, f"Data to analyse:\n\n{combined}")
        data = self._extract_json(raw)
        if not isinstance(data, dict):
            logger.warning("Neo4j LLM response could not be parsed as JSON.")
            return [], "", ""
        statements = [s for s in data.get("statements", []) if isinstance(s, str)]
        return (
            statements,
            str(data.get("schema_prompt", "")),
            str(data.get("guidelines", "")),
        )

    def _generate_postgis_data(
        self, contents: list[FileContent]
    ) -> tuple[list[str], str, str]:
        """Return (sql_statements, schema_prompt, guidelines).

        Only called when at least one geospatial source is present.
        """
        geo = [
            fc for fc in contents
            if fc.file_type == "geojson" or self._has_geo_columns(fc)
        ]
        if not geo:
            logger.info("No geospatial data found – skipping PostGIS generation.")
            return [], "", ""

        combined = self._summarize_contents(geo)
        system = textwrap.dedent(f"""
            You are a PostGIS expert.
            Given the geospatial data below, generate:
            1. SQL DDL (CREATE TABLE IF NOT EXISTS) and DML (INSERT INTO … ON CONFLICT
               DO NOTHING) statements.
               Use GEOMETRY(POINT,4326) for point locations and
               GEOMETRY(POLYGON,4326) for area geometries.
               Coordinate pairs must be (longitude, latitude).
            2. A schema description of the tables.
            3. Brief agent guidelines for writing spatial queries.

            Theme name: {self.theme_name!r}

            Return **only** a JSON object:
            {{
              "statements": ["CREATE TABLE ...", "INSERT INTO ...", ...],
              "schema_prompt": "Tables:\\n- ...",
              "guidelines": "..."
            }}
        """).strip()

        raw = self._call_llm(system, f"Geospatial data:\n\n{combined}")
        data = self._extract_json(raw)
        if not isinstance(data, dict):
            logger.warning("PostGIS LLM response could not be parsed as JSON.")
            return [], "", ""
        statements = [s for s in data.get("statements", []) if isinstance(s, str)]
        return (
            statements,
            str(data.get("schema_prompt", "")),
            str(data.get("guidelines", "")),
        )

    def _generate_rdf_data(
        self, contents: list[FileContent]
    ) -> tuple[str, str, str, str]:
        """Return (turtle_rdf, named_graph_uri, schema_prompt, guidelines)."""
        combined = self._summarize_contents(contents)
        base_uri = f"http://pangia.io/ontology/{self.theme_name}#"
        graph_uri = f"http://pangia.io/graphs/{self.theme_name}"
        system = textwrap.dedent(f"""
            You are an RDF / OWL ontology expert.
            Given the input data, generate:
            1. A Turtle-formatted RDF document with appropriate prefixes, classes,
               individuals, object properties and data properties.
            2. A SPARQL schema description (prefixes, classes, properties).
            3. Brief agent guidelines for SPARQL querying.

            Use base URI: {base_uri}
            Named graph:  {graph_uri}

            Theme name: {self.theme_name!r}

            Return **only** a JSON object:
            {{
              "turtle": "@prefix : <{base_uri}> .\\n...",
              "named_graph": "{graph_uri}",
              "schema_prompt": "PREFIX : <{base_uri}>\\n\\nClasses:\\n...",
              "guidelines": "..."
            }}
        """).strip()

        raw = self._call_llm(system, f"Data to analyse:\n\n{combined}")
        data = self._extract_json(raw)
        if not isinstance(data, dict):
            logger.warning("RDF LLM response could not be parsed as JSON.")
            return "", graph_uri, "", ""
        return (
            str(data.get("turtle", "")),
            str(data.get("named_graph", graph_uri)),
            str(data.get("schema_prompt", "")),
            str(data.get("guidelines", "")),
        )

    def _generate_chroma_documents(
        self, contents: list[FileContent]
    ) -> tuple[list[dict], str]:
        """Return (chroma_docs, vector_guidelines)."""
        combined = self._summarize_contents(contents, max_chars=12_000)
        system = textwrap.dedent("""
            You are a text analysis and retrieval expert.
            Split the input data into meaningful chunks suitable for semantic
            similarity search and embedding into a vector store.
            Each chunk should be a self-contained, informative paragraph
            (2–5 sentences).  Include relevant metadata.

            Create between 5 and 30 documents.

            Return **only** a JSON array (no prose, no code fences):
            [
              {"text": "...", "metadata": {"category": "...", "source": "..."}},
              ...
            ]
        """).strip()

        raw = self._call_llm(system, f"Data:\n\n{combined}")
        docs = self._extract_json(raw)
        if not isinstance(docs, list):
            logger.warning("ChromaDB LLM response could not be parsed as JSON list.")
            docs = []

        valid: list[dict] = []
        for doc in docs:
            if isinstance(doc, dict) and isinstance(doc.get("text"), str):
                valid.append(
                    {
                        "text": doc["text"],
                        "metadata": (
                            doc.get("metadata", {})
                            if isinstance(doc.get("metadata"), dict)
                            else {}
                        ),
                    }
                )

        guidelines = (
            f"The vector store contains embedded documents about {self.theme_name}. "
            "Use semantic similarity search to find relevant context. "
            "Combine vector results with structured database queries for "
            "comprehensive answers."
        )
        return valid, guidelines

    def _generate_suggestions(self, contents: list[FileContent]) -> list[str]:
        """Return a list of example UI query suggestions."""
        combined = self._summarize_contents(contents, max_chars=4_000)
        system = textwrap.dedent("""
            Given the data summary below, generate 8–12 natural-language questions
            a user might ask about this dataset.  Mix simple and complex questions
            covering different aspects (spatial, relationships, statistics).

            Return **only** a JSON array of strings:
            ["Question 1?", "Question 2?", ...]
        """).strip()

        raw = self._call_llm(system, f"Data:\n\n{combined}")
        suggestions = self._extract_json(raw)
        if not isinstance(suggestions, list):
            return []
        return [str(s) for s in suggestions[:12] if s]

    # ------------------------------------------------------------------
    # Main ingestion pipeline
    # ------------------------------------------------------------------

    def ingest(self) -> IngestionResult:
        """
        Discover files in *corpus_path*, read them, then call the LLM to
        generate seed data for each database backend.

        Returns
        -------
        IngestionResult
            A dataclass with all generated statements, Turtle RDF, vector
            documents, suggestions, schema prompts and guidelines.

        Raises
        ------
        FileNotFoundError
            If *corpus_path* does not exist or contains no supported files.
        RuntimeError
            If every discovered file fails to read.
        """
        logger.info("Starting corpus ingestion from: %s", self.corpus_path)

        # ── 1. Discover & read files ──────────────────────────────────────
        file_paths = self.discover_files()
        if not file_paths:
            raise FileNotFoundError(
                f"No supported files found in {self.corpus_path}. "
                f"Supported types: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}"
            )
        logger.info(
            "Found %d file(s): %s",
            len(file_paths),
            [p.name for p in file_paths],
        )

        contents: list[FileContent] = []
        for fp in file_paths:
            try:
                fc = self.read_file(fp)
                if fc.raw_text.strip():
                    contents.append(fc)
                    logger.info(
                        "Read %-40s  (%s, %d chars)",
                        fp.name,
                        fc.file_type,
                        len(fc.raw_text),
                    )
                else:
                    logger.warning("Skipping %s – no text extracted.", fp.name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not read %s: %s", fp, exc)

        if not contents:
            raise RuntimeError(
                "All files failed to produce readable content. "
                "Check the logs above for details."
            )

        result = IngestionResult(
            theme_name=self.theme_name,
            files_processed=[str(p) for p in file_paths],
        )

        # ── 2. Neo4j ──────────────────────────────────────────────────────
        logger.info("Generating Neo4j Cypher statements …")
        (
            result.neo4j_statements,
            result.neo4j_schema_prompt,
            result.neo4j_guidelines,
        ) = self._generate_neo4j_data(contents)
        logger.info("  → %d statements.", len(result.neo4j_statements))

        # ── 3. PostGIS ────────────────────────────────────────────────────
        logger.info("Generating PostGIS SQL statements …")
        (
            result.postgis_statements,
            result.postgis_schema_prompt,
            result.postgis_guidelines,
        ) = self._generate_postgis_data(contents)
        logger.info("  → %d statements.", len(result.postgis_statements))

        # ── 4. RDF / GraphDB ──────────────────────────────────────────────
        logger.info("Generating RDF Turtle …")
        (
            result.graphdb_turtle,
            result.graphdb_named_graph,
            result.rdf_schema_prompt,
            result.rdf_guidelines,
        ) = self._generate_rdf_data(contents)
        logger.info("  → %d chars of Turtle.", len(result.graphdb_turtle))

        # ── 5. ChromaDB ───────────────────────────────────────────────────
        logger.info("Generating vector documents …")
        result.chroma_documents, result.vector_guidelines = (
            self._generate_chroma_documents(contents)
        )
        logger.info("  → %d documents.", len(result.chroma_documents))

        # ── 6. Suggestions ────────────────────────────────────────────────
        logger.info("Generating UI suggestions …")
        result.suggestions = self._generate_suggestions(contents)
        logger.info("  → %d suggestions.", len(result.suggestions))

        logger.info("Ingestion complete for theme %r.", self.theme_name)
        return result

    # ------------------------------------------------------------------
    # Seed file output
    # ------------------------------------------------------------------

    def save_seed_file(
        self,
        result: IngestionResult,
        output_path: str | Path | None = None,
    ) -> Path:
        """
        Render *result* as a Python module and write it to *output_path*.

        If *output_path* is omitted the file is written to
        ``<output_dir>/<theme_name>.py`` (defaults to
        ``backend/app/db/themes/<theme_name>.py``).

        Returns the path of the written file.
        """
        if output_path is None:
            output_path = self.output_dir / f"{result.theme_name}.py"
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        code = render_seed_module(result)
        out.write_text(code, encoding="utf-8")
        logger.info("Seed file written to: %s", out)
        return out

    def to_seed_theme(self, result: IngestionResult) -> Any:
        """
        Convert *result* to a live :class:`~app.db.themes.SeedTheme` object.

        Requires ``backend/`` to be on ``sys.path``.
        """
        try:
            from app.db.themes import SeedTheme  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "Cannot import app.db.themes. "
                "Make sure the backend/ directory is on sys.path."
            ) from exc

        return SeedTheme(
            name=result.theme_name,
            neo4j_statements=result.neo4j_statements,
            neo4j_schema_prompt=result.neo4j_schema_prompt,
            neo4j_guidelines=result.neo4j_guidelines,
            postgis_statements=result.postgis_statements,
            postgis_schema_prompt=result.postgis_schema_prompt,
            postgis_guidelines=result.postgis_guidelines,
            graphdb_named_graph=result.graphdb_named_graph,
            graphdb_turtle=result.graphdb_turtle,
            rdf_schema_prompt=result.rdf_schema_prompt,
            rdf_guidelines=result.rdf_guidelines,
            chroma_documents=result.chroma_documents,
            vector_guidelines=result.vector_guidelines,
            suggestions=result.suggestions,
        )


# ---------------------------------------------------------------------------
# Seed-module renderer
# ---------------------------------------------------------------------------


def render_seed_module(result: IngestionResult) -> str:
    """
    Render an :class:`IngestionResult` as a valid PangIA seed-theme Python
    module string.

    The output follows the same structure as the hand-crafted theme files in
    ``app/db/themes/`` and can be imported directly by
    :func:`app.db.seed.seed_all`.
    """
    lines: list[str] = []

    # ── Module docstring ──────────────────────────────────────────────────
    sources = "\n".join(f"  - {Path(f).name}" for f in result.files_processed)
    lines.append(
        '"""\n'
        f"Seed theme: {result.theme_name}.\n\n"
        "Auto-generated by ``tools/ingest_corpus.py`` from:\n"
        f"{sources}\n\n"
        "To regenerate run the ``tools/ingest_corpus.ipynb`` notebook.\n"
        '"""'
    )
    lines.append("from app.db.themes import SeedTheme")
    lines.append("")
    lines.append("theme = SeedTheme(")
    lines.append(f"    name={result.theme_name!r},")
    lines.append("")

    # ── Schema prompts ─────────────────────────────────────────────────────
    lines.append("    # ── Schema prompts ─────────────────────────────────────────────")
    for attr in ("neo4j_schema_prompt", "postgis_schema_prompt", "rdf_schema_prompt"):
        lines.append(f"    {attr}={getattr(result, attr)!r},")
        lines.append("")

    # ── Guidelines ──────────────────────────────────────────────────────────
    lines.append("    # ── Guidelines ─────────────────────────────────────────────────")
    for attr in (
        "neo4j_guidelines",
        "postgis_guidelines",
        "rdf_guidelines",
        "vector_guidelines",
    ):
        lines.append(f"    {attr}={getattr(result, attr)!r},")
        lines.append("")

    # ── Neo4j statements ────────────────────────────────────────────────────
    lines.append("    # ── Neo4j – Cypher statements ────────────────────────────────")
    lines.append("    neo4j_statements=[")
    for stmt in result.neo4j_statements:
        lines.append(f"        {stmt!r},")
    lines.append("    ],")
    lines.append("")

    # ── PostGIS statements ──────────────────────────────────────────────────
    lines.append("    # ── PostGIS – SQL statements ─────────────────────────────────")
    lines.append("    postgis_statements=[")
    for stmt in result.postgis_statements:
        lines.append(f"        {stmt!r},")
    lines.append("    ],")
    lines.append("")

    # ── GraphDB / RDF ────────────────────────────────────────────────────────
    lines.append("    # ── GraphDB / RDF ─────────────────────────────────────────────")
    lines.append(f"    graphdb_named_graph={result.graphdb_named_graph!r},")
    lines.append("")
    lines.append(f"    graphdb_turtle={result.graphdb_turtle!r},")
    lines.append("")

    # ── ChromaDB documents ──────────────────────────────────────────────────
    lines.append("    # ── ChromaDB documents ────────────────────────────────────────")
    lines.append("    chroma_documents=[")
    for doc in result.chroma_documents:
        lines.append(f"        {doc!r},")
    lines.append("    ],")
    lines.append("")

    # ── Suggestions ─────────────────────────────────────────────────────────
    lines.append("    # ── UI suggestions ────────────────────────────────────────────")
    lines.append("    suggestions=[")
    for s in result.suggestions:
        lines.append(f"        {s!r},")
    lines.append("    ],")

    lines.append(")")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.ingest_corpus",
        description=(
            "Analyse files in a corpus folder (PDF, CSV, GeoJSON, JSON) and "
            "generate a PangIA seed theme Python module."
        ),
    )
    parser.add_argument(
        "--corpus",
        default="/corpus",
        metavar="PATH",
        help="Path to the corpus folder (default: /corpus).",
    )
    parser.add_argument(
        "--theme",
        default="custom",
        metavar="NAME",
        help="Short theme name used as the module filename (default: custom).",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="FILE",
        help=(
            "Output path for the generated seed file.  "
            "Defaults to backend/app/db/themes/<theme>.py relative to the "
            "repository root."
        ),
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        metavar="MODEL",
        help="OpenAI model to use (default: gpt-4o-mini).",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=16_000,
        metavar="N",
        help="Max corpus characters forwarded per LLM call (default: 16000).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)-8s %(message)s",
        stream=sys.stdout,
    )
    args = _build_parser().parse_args(argv)

    ingestor = CorpusIngestor(
        corpus_path=args.corpus,
        theme_name=args.theme,
        openai_model=args.model,
        max_content_chars=args.max_chars,
    )

    result = ingestor.ingest()
    out = ingestor.save_seed_file(result, output_path=args.output)
    print(f"\n✓  Seed file written to: {out}")
    print(f"   Add SEED_THEME={result.theme_name!r} to your .env and restart the app.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
